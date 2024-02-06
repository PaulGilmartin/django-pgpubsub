import logging
import multiprocessing
import select
import sys
from typing import List, Optional, Union

from django.core.management import execute_from_command_line
from django.db import connection, transaction
from psycopg2._psycopg import Notify

from pgpubsub import process_stored_notifications
from pgpubsub.channel import (
    BaseChannel,
    Channel,
    ChannelNotFound,
    locate_channel,
    registry,
)
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
        channels = [c if isinstance(str, c) else c.name() for c in channels]
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
    pg_connection = listen_to_channels(channels)

    if recover:
        process_stored_notifications(channels)
        process_notifications(pg_connection)

    logger.info('Listening for notifications... \n')
    while POLL:
        if select.select([pg_connection], [], [], 1) == ([], [], []):
            pass
        else:
            try:
                process_notifications(pg_connection)
            except Exception as e:
                logger.error(f'Encountered exception {e}', exc_info=e)
                if autorestart_on_failure:
                    start_listen_in_a_process(
                        channels, recover, autorestart_on_failure, start_method
                    )
                raise


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
    for channel in channels:
        logger.info(f'Listening on {channel.name()}\n')
        cursor.execute(f'LISTEN {channel.listen_safe_name()};')
    return connection.connection


def process_notifications(pg_connection):
    pg_connection.poll()
    while pg_connection.notifies:
        notification = pg_connection.notifies.pop(0)
        with transaction.atomic():
            for processor in [
                NotificationProcessor,
                LockableNotificationProcessor,
                NotificationRecoveryProcessor,
            ]:
                try:
                    processor = processor(notification, pg_connection)
                except InvalidNotificationProcessor:
                    continue
                else:
                    processor.process()
                    break


class NotificationProcessor:
    def __init__(self, notification: Notify, pg_connection):
        self.notification = notification
        self.channel_cls, self.callbacks = Channel.get(notification.channel)
        self.pg_connection = pg_connection
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
        self.pg_connection.poll()


class LockableNotificationProcessor(NotificationProcessor):

    def validate(self):
        if self.notification.payload == 'null':
            raise InvalidNotificationProcessor

    def process(self):
        logger.info(
            f'Processing notification for {self.channel_cls.name()}')
        notification = (
            Notification.objects.select_for_update(
                skip_locked=True).filter(
                channel=self.notification.channel,
                payload=self.notification.payload,
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
        if self.notification.payload != 'null':
            raise InvalidNotificationProcessor

    def process(self):
        logger.info(f'Processing all notifications for channel {self.channel_cls.name()} \n')
        notifications = (
            Notification.objects.select_for_update(
                skip_locked=True).filter(channel=self.notification.channel).iterator()
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
