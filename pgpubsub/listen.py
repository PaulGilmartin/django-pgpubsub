import select
from functools import wraps

import pgtrigger
from django.db import connection

from pgpubsub.channel import (
    CustomPayloadChannel,
    TriggerPayloadChannel,
    Channel,
)
from pgpubsub.notify import Notify


def listen(channel_names=None):
    if channel_names is None:
        channels = Channel.registry
    else:
        channels = {name: Channel.get(name) for name in channel_names}
    cursor = connection.cursor() # set isolation
    for channel_name in channels:
        print(f'Listening on {channel_name}')
        cursor.execute('LISTEN {};'.format(channel_name))
    pg_connection = connection.connection
    while True:
        if select.select([pg_connection], [], [], 5) == ([], [], []):
            print('Timeout')
        else:
            pg_connection.poll()
            while pg_connection.notifies:
                notification = pg_connection.notifies.pop(0)
                channel_name = notification.channel
                channel = channels.get(channel_name)
                deserialized = channel.deserialize(notification.payload)
                channel.callback(**deserialized)


def listener(channel_name: str=None):
    def _listen(callback):
        CustomPayloadChannel.register(callback, channel_name)
        @wraps(callback)
        def wrapper(*args, **kwargs):
            return callback(*args, **kwargs)
        return wrapper
    return _listen


def post_insert_listener(model, channel_name=None):
    return trigger_listener(
        model,
        trigger=Notify(
            name=channel_name,
            when=pgtrigger.After,
            operation=pgtrigger.Insert,
        ),
        channel_name=channel_name,
    )


def trigger_listener(
    model,
    trigger,
    channel_name: str=None,
):
    def _trig_listener(callback):
        TriggerPayloadChannel.register(callback, channel_name)
        trigger.register(model)
        trigger.install(model)
        @wraps(callback)
        def wrapper(*args, **kwargs):
            return callback(*args, **kwargs)
        return wrapper
    return _trig_listener
