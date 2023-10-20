from functools import wraps
from typing import Union, Type

import pgtrigger
from pgtrigger import Trigger, registered

from pgpubsub.channel import (
    locate_channel,
    Channel,
    TriggerChannel,
)


def listener(channel: Union[Type[Channel], str]):
    channel = locate_channel(channel)
    def _listen(callback):
        channel.register(callback)
        @wraps(callback)
        def wrapper(*args, **kwargs):
            return callback(*args, **kwargs)
        return wrapper
    return _listen


def pre_save_listener(channel: Union[Type[TriggerChannel], str]):
    return _trigger_action_listener(
        channel,
        pgtrigger.Before,
        pgtrigger.Update | pgtrigger.Insert,
        )


def post_save_listener(channel: Union[Type[TriggerChannel], str]):
    return _trigger_action_listener(
        channel,
        pgtrigger.After,
        pgtrigger.Update | pgtrigger.Insert,
        )


def pre_update_listener(channel: Union[Type[TriggerChannel], str]):
    return _trigger_action_listener(
        channel, pgtrigger.Before, pgtrigger.Update)


def post_update_listener(channel: Union[Type[TriggerChannel], str]):
    return _trigger_action_listener(
        channel, pgtrigger.After, pgtrigger.Update)


def pre_insert_listener(channel: Union[Type[TriggerChannel], str]):
    return _trigger_action_listener(
        channel, pgtrigger.Before, pgtrigger.Insert)


def post_insert_listener(channel: Union[Type[TriggerChannel], str]):
    return _trigger_action_listener(
        channel, pgtrigger.After, pgtrigger.Insert)


def pre_delete_listener(channel: Union[Type[TriggerChannel], str]):
    return _trigger_action_listener(
        channel, pgtrigger.Before, pgtrigger.Delete)


def post_delete_listener(channel: Union[Type[TriggerChannel], str]):
    return _trigger_action_listener(
        channel, pgtrigger.After, pgtrigger.Delete)


def _trigger_action_listener(channel, when, operation):
    from pgpubsub.triggers import LockableNotify, Notify
    notify_cls = (
        LockableNotify if channel.lock_notifications else Notify)
    return trigger_listener(
        channel,
        trigger=notify_cls(
            name=channel.listen_safe_name(),
            when=when,
            operation=operation,
        ),
    )


def trigger_listener(channel: Union[Type[Channel], str], trigger: Trigger):
    channel = locate_channel(channel)
    def _trig_listener(callback):
        triggers_already_registered = registered()
        model_to_trigger_name = [(model, trig.name) for (model, trig) in triggers_already_registered]

        if (channel.model, trigger.name) not in model_to_trigger_name:
            # This can happen when the same channel/trigger is used
            # for multiple listeners
            pgtrigger.register(trigger)(channel.model)

        channel.register(callback)

        @wraps(callback)
        def wrapper(*args, **kwargs):
            return callback(*args, **kwargs)
        return wrapper
    return _trig_listener
