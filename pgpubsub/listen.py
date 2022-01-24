from functools import wraps

import pgtrigger

from pgpubsub.channel import CustomPayloadChannel, TriggerPayloadChannel
from pgpubsub.notify import Notify


def listen(channel_name: str=None):
    def _listen(callback):
        CustomPayloadChannel.register(callback, channel_name)
        @wraps(callback)
        def wrapper(*args, **kwargs):
            return callback(*args, **kwargs)
        return wrapper
    return _listen


def post_insert_listen(model, channel_name=None):
    return trigger_listen(
        model,
        trigger=Notify(
            name=channel_name,
            when=pgtrigger.After,
            operation=pgtrigger.Insert,
        ),
        channel_name=channel_name,
    )


def trigger_listen(
    model,
    trigger,
    channel_name: str=None,
):
    def _trig_listen(callback):
        TriggerPayloadChannel.register(callback, channel_name)
        trigger.install(model)
        @wraps(callback)
        def wrapper(*args, **kwargs):
            return callback(*args, **kwargs)
        return wrapper
    return _trig_listen
