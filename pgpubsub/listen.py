from functools import wraps
import select

from django.db import connection
import pgtrigger

from pgpubsub.channel import Channel, ChannelNotFound, locate_channel, registry
from pgpubsub.notify import Notify


def listen(channels=None):
    pg_connection = listen_to_channels(channels)
    while True:
        if select.select([pg_connection], [], [], 5) == ([], [], []):
            print('Timeout')
        else:
            process_notifications(pg_connection)


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
        name = channel.name()
        print(f'Listening on {name}')
        cursor.execute(f'LISTEN {name};')
    return connection.connection


def process_notifications(pg_connection):
    pg_connection.poll()
    while pg_connection.notifies:
        notification = pg_connection.notifies.pop(0)
        channel_name = notification.channel
        print(f'Received notification on {channel_name}')
        channel_cls, callbacks = Channel.get(channel_name)
        channel = channel_cls.build_from_payload(notification.payload, callbacks)
        channel.execute_callbacks()


def listener(channel):
    channel = locate_channel(channel)

    def _listen(callback):
        channel.register(callback)

        @wraps(callback)
        def wrapper(*args, **kwargs):
            return callback(*args, **kwargs)

        return wrapper

    return _listen


def post_insert_listener(channel):
    return trigger_listener(
        channel,
        trigger=Notify(
            name=channel.name(),
            when=pgtrigger.After,
            operation=pgtrigger.Insert,
        ),
    )


def post_delete_listener(channel):
    return trigger_listener(
        channel,
        trigger=Notify(
            name=channel.name(),
            when=pgtrigger.After,
            operation=pgtrigger.Delete,
        ),
    )


def trigger_listener(channel, trigger):
    channel = locate_channel(channel)

    def _trig_listener(callback):
        channel.register(callback)
        pgtrigger.register(trigger)(channel.model)

        @wraps(callback)
        def wrapper(*args, **kwargs):
            return callback(*args, **kwargs)

        return wrapper

    return _trig_listener
