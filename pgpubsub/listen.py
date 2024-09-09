import importlib
import logging
import multiprocessing
import select
import sys
from typing import List, Optional, Union

from django.conf import settings
from django.core.management import execute_from_command_line
from django.db import connection, transaction
from django.db.models import Func, Value, Q

from pgpubsub import process_stored_notifications
from pgpubsub.channel import (
    BaseChannel,
    Channel,
    ChannelNotFound,
    locate_channel,
    registry,
)
from pgpubsub.compatibility import ConnectionWrapper, Notify
from pgpubsub.listeners import ListenerFilterProvider
from pgpubsub.models import Notification

logger = logging.getLogger(__name__)

POLL = True


def start_listen_in_a_process(
    channels: Union[List[BaseChannel], List[str]] = None,
    recover: bool = False,
    autorestart_on_failure: bool = True,
    start_method: str = 'spawn',
    name: Optional[str] = None,
) -> multiprocessing.Process:
    connection.close()
    multiprocessing.set_start_method(start_method, force=True)
    logger.info('Restarting process')
    if channels:
        channels = [c if isinstance(c, str) else c.name() for c in channels]
    if start_method == 'fork':
        logger.debug('  using fork')
        process = multiprocessing.Process(
            name=name,
            target=listen,
            args=(channels, recover, autorestart_on_failure, 'fork'),
        )
    elif start_method == 'spawn':
        args = [sys.argv[0], 'listen', '--worker', '--worker-start-method', 'spawn']
        if recover:
            args.append('--recover')
        if not autorestart_on_failure:
            args.append('--no-restart-on-failure')
        if channels:
            args.append('--channels')
            args.extend(channels)
        logger.debug(f'  with {args=}')
        process = multiprocessing.Process(
            name=name, target=execute_from_command_line, args=(args, )
        )
    else:
        raise ValueError(f'Unsupported start method {start_method}')

    process.start()
    return process



def listen(
    channels: Union[List[BaseChannel], List[str]] = None,
    recover: bool = False,
    autorestart_on_failure: bool = True,
    start_method: str = 'spawn',
):
    connection_wrapper = listen_to_channels(channels)

    try:
        if recover:
            process_stored_notifications(channels)
            process_notifications(connection_wrapper)

        logger.info('Listening for notifications... \n')
        while POLL:
            if select.select([connection_wrapper.connection], [], [], 1) == ([], [], []):
                pass
            else:
                try:
                    process_notifications(connection_wrapper)
                except Exception as e:
                    logger.error(f'Encountered exception {e}', exc_info=e)
                    if autorestart_on_failure:
                        start_listen_in_a_process(
                            channels, recover, autorestart_on_failure, start_method
                        )
                    raise
    finally:
        connection_wrapper.stop()


def listen_to_channels(channels: Union[List[BaseChannel], List[str]] = None):
    if channels is None:
        channels = registry
    else:
        channels = [locate_channel(channel) for channel in channels]
        channels = {
            channel: callbacks
            for channel, callbacks in registry.items()
            if issubclass(channel, tuple(channels))
        }
    if not channels:
        raise ChannelNotFound()
    cursor = connection.cursor()
    # Notifications are started to being delivered only after the transaction commits.
    # Check LISTEN documentation for detailed description.
    with transaction.atomic():
        for channel in channels:
            logger.info(f'Listening on {channel.name()}\n')
            cursor.execute(f'LISTEN {channel.listen_safe_name()};')
    return ConnectionWrapper(connection.connection)


def process_notifications(connection_wrapper):
    connection_wrapper.poll()
    while connection_wrapper.notifies:
        notification = connection_wrapper.notifies.pop(0)
        with transaction.atomic():
            for processor in [
                NotificationProcessor,
                LockableNotificationProcessor,
                NotificationRecoveryProcessor,
            ]:
                try:
                    processor = processor(notification, connection_wrapper)
                except InvalidNotificationProcessor:
                    continue
                else:
                    processor.process()
                    break


class NotificationProcessor:
    def __init__(self, notification: Notify, connection_wrapper):
        self.notification = notification
        self.channel_cls, self.callbacks = Channel.get(notification.channel)
        self.connection_wrapper = connection_wrapper
        self.validate()

    def validate(self):
        if self.channel_cls.lock_notifications:
            raise InvalidNotificationProcessor

    def process(self):
        logger.info(f'Processing notification for {self.channel_cls.name()}\n')
        return self._execute()

    def _execute(self):
        channel = self.channel_cls.build_from_payload(
            self.notification.payload, self.callbacks)
        channel.execute_callbacks()
        self.connection_wrapper.poll()


class CastToJSONB(Func):
    template = '((%(expressions)s)::jsonb)'


def get_extra_filter() -> Q:
    extra_filter_provider_fq_name = getattr(settings, 'PGPUBSUB_LISTENER_FILTER', None)
    if extra_filter_provider_fq_name:
        module = importlib.import_module(
            '.'.join(extra_filter_provider_fq_name.split('.')[:-1])
        )
        clazz = getattr(module, extra_filter_provider_fq_name.split('.')[-1])
        extra_filter_provider: ListenerFilterProvider = clazz()
        return extra_filter_provider.get_filter()
    else:
        return Q()

class LockableNotificationProcessor(NotificationProcessor):

    def validate(self):
        if self.notification.payload == '':
            raise InvalidNotificationProcessor

    def process(self):
        logger.info(
            f'Processing notification for {self.channel_cls.name()}')
        payload_filter = (
            Q(payload=CastToJSONB(Value(self.notification.payload))) |
            Q(payload=self.notification.payload)
        )
        payload_filter &= get_extra_filter()
        notification = (
            Notification.objects.select_for_update(
                skip_locked=True).filter(
                    payload_filter,
                    channel=self.notification.channel,
            ).first()
        )
        if notification is None:
            logger.info(f'Could not obtain a lock on notification '
                        f'{self.notification.pid}\n')
        else:
            logger.info(f'Obtained lock on {notification}')
            self.notification = notification
            self._execute()
            self.notification.delete()


class NotificationRecoveryProcessor(LockableNotificationProcessor):

    def validate(self):
        if self.notification.payload != '':
            raise InvalidNotificationProcessor

    def process(self):
        logger.info(f'Processing all notifications for channel {self.channel_cls.name()} \n')
        payload_filter = Q(channel=self.notification.channel) & get_extra_filter()
        notifications = (
            Notification.objects.select_for_update(
                skip_locked=True).filter(payload_filter).iterator()
        )
        logger.info(f'Found notifications: {notifications}')
        for notification in notifications:
            self.notification = notification
            try:
                with transaction.atomic():
                    self._execute()
            except Exception as e:
                logger.error(
                    f'Encountered {e} exception when processing notification {notification}',
                    exc_info=e
                )
            else:
                logger.info(f'Successfully processed notification {notification}')
                self.notification.delete()


class InvalidNotificationProcessor(Exception):
    pass
