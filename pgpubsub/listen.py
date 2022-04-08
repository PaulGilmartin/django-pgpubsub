import multiprocessing
import select

from django.db import connection, transaction

from pgpubsub.channel import (
    Channel,
    ChannelNotFound,
    locate_channel,
    registry,
)
from pgpubsub.models import Notification


def listen(channels=None):
    pg_connection = listen_to_channels(channels)
    while True:
        if select.select([pg_connection], [], [], 1) == ([], [], []):
            print('Timeout\n')
        else:
            try:
                process_notifications(pg_connection)
            except Exception:
                print('Encountered exception')
                print('Restarting process')
                process = multiprocessing.Process(
                    target=listen, args=(channels,))
                process.start()
                raise


def listen_to_channels(channels=None):
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
        channel_cls, callbacks = Channel.get(notification.channel)
        print(
            f'Received notification on {channel_cls.name()}')
        with transaction.atomic():
            if channel_cls.lock_notifications:
                channel_name = notification.channel
                notification = (
                    Notification.objects.select_for_update(
                        skip_locked=True).filter(
                        channel=channel_name,
                        payload=notification.payload,
                    ).first()
                )
                if notification is None:
                    print(f'Could not obtain a lock on notification'
                          f'{notification} sent to channel {channel_name}')
                    print('\n')
                    continue
                else:
                    print(f'Obtained lock on {notification}')
            channel = channel_cls.build_from_payload(
                notification.payload, callbacks)
            channel.execute_callbacks()
            if channel_cls.lock_notifications:
                notification.delete()
            print('\n')
            pg_connection.poll()
