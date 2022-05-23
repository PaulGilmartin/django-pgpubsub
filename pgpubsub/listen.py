import logging
import multiprocessing
import select
from typing import List, Union

from django.db import connection, transaction
from psycopg2._psycopg import Notify

from pgpubsub.channel import (
    BaseChannel,
    Channel,
    ChannelNotFound,
    locate_channel,
    registry,
)
from pgpubsub.models import Notification


def listen(channels: Union[List[BaseChannel], List[str]]=None):
    pg_connection = listen_to_channels(channels)
    while True:
        if select.select([pg_connection], [], [], 1) == ([], [], []):
            print('Listening for notifications...\n')
        else:
            try:
                process_notifications(pg_connection)
            except Exception as e:
                print(f'Encountered exception {e}')
                print('Restarting process')
                process = multiprocessing.Process(
                    target=listen, args=(channels,))
                process.start()
                raise


def listen_to_channels(channels: Union[List[BaseChannel], List[str]]=None):
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
        print(f'Listening on {channel.name()}')
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
        self.channel_cls, self.callbacks = Channel.get(
            notification.channel)
        self.pg_connection = pg_connection
        self.validate()

    def validate(self):
        if self.channel_cls.lock_notifications:
            raise InvalidNotificationProcessor

    def process(self):
        print(
            f'Processing notification for {self.channel_cls.name()}')
        return self._execute()

    def _execute(self):
        channel = self.channel_cls.build_from_payload(
            self.notification.payload, self.callbacks)
        channel.execute_callbacks()
        print('\n')
        self.pg_connection.poll()


class LockableNotificationProcessor(NotificationProcessor):

    def validate(self):
        if self.notification.payload == 'null':
            raise InvalidNotificationProcessor

    def process(self):
        print(
            f'Processing notification for {self.channel_cls.name()}')
        notification = (
            Notification.objects.select_for_update(
                skip_locked=True).filter(
                channel=self.notification.channel,
                payload=self.notification.payload,
            ).first()
        )
        if notification is None:
            print(f'Could not obtain a lock on notification '
                  f'{self.notification.pid}')
            print('\n')
        else:
            print(f'Obtained lock on {notification}')
            self.notification = notification
            self._execute()

    def _execute(self):
        super()._execute()
        self.notification.delete()


class NotificationRecoveryProcessor(LockableNotificationProcessor):

    def validate(self):
        if self.notification.payload != 'null':
            raise InvalidNotificationProcessor

    def process(self):
        print('Received null payload. Processing all notifications for channel')
        notifications = (
            Notification.objects.select_for_update(
                skip_locked=True).filter(channel=self.notification.channel)
        )
        for notification in notifications:
            self.notification = notification
            self._execute()


class InvalidNotificationProcessor(Exception):
    pass
