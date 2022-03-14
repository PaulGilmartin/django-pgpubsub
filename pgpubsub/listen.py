import json
from functools import wraps
import select

from django.db import connection, transaction
import pgtrigger
from pgtrigger import Q

from pgpubsub.channel import (
    Channel,
    ChannelNotFound,
    locate_channel,
    registry,
)
from pgpubsub.models import Notification
from pgpubsub.notify import Notify, ProcessOnceNotify


def listen(channels=None):
    pg_connection = listen_to_channels(channels)
    while True:
        if select.select([pg_connection], [], [], 1) == ([], [], []):
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
        print(
            f'Received notification on {notification.channel}')
        with transaction.atomic():
            payload = json.loads(notification.payload)
            uuid = payload['pgpubsub_notification_uuid']
            channel_cls, callbacks = Channel.get(notification.channel)
            if channel_cls.process_once:
                try:
                    notification = (
                        Notification.objects.select_for_update(
                            skip_locked=True).get(
                                uuid=uuid, channel=notification.channel)
                    )
                except Notification.DoesNotExist:
                    print(f'Could not obtain a lock on {uuid}')
                    print('\n')
                    continue
                else:
                    print(f'Obtained lock on {notification}')
            channel = channel_cls.build_from_payload(payload, callbacks)
            channel.execute_callbacks()
            if channel_cls.process_once:
                notification.delete()
            print('\n')
            pg_connection.poll()


def listener(channel):
    channel = locate_channel(channel)
    def _listen(callback):
        channel.register(callback)
        @wraps(callback)
        def wrapper(*args, **kwargs):
            return callback(*args, **kwargs)
        return wrapper
    return _listen


def pre_save_listener(channel):
    return _trigger_action_listener(
        channel,
        pgtrigger.Before,
        Q(pgtrigger.Update) | Q(pgtrigger.Insert),
    )

def post_save_listener(channel):
    return _trigger_action_listener(
        channel,
        pgtrigger.After,
        Q(pgtrigger.Update) | Q(pgtrigger.Insert),
    )

def pre_update_listener(channel):
    return _trigger_action_listener(
        channel, pgtrigger.Before, pgtrigger.Update)

def post_update_listener(channel):
    return _trigger_action_listener(
        channel, pgtrigger.After, pgtrigger.Update)

def pre_insert_listener(channel):
    return _trigger_action_listener(
        channel, pgtrigger.Before, pgtrigger.Insert)

def post_insert_listener(channel):
    return _trigger_action_listener(
        channel, pgtrigger.After, pgtrigger.Insert)

def pre_delete_listener(channel):
    return _trigger_action_listener(
        channel, pgtrigger.Before, pgtrigger.Delete)

def post_delete_listener(channel):
    return _trigger_action_listener(
        channel, pgtrigger.After, pgtrigger.Delete)


def _trigger_action_listener(channel, when, operation):
    notify_cls = ProcessOnceNotify if channel.process_once else Notify
    return trigger_listener(
        channel,
        trigger=notify_cls(
            name=channel.name(),
            when=when,
            operation=operation,
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
