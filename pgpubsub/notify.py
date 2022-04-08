from typing import Type, Union

from django.db import connection
from django.db.transaction import atomic

from pgpubsub.channel import locate_channel, Channel, registry


@atomic
def notify(channel: Union[Type[Channel], str], **kwargs):
    channel_cls = locate_channel(channel)
    channel = channel_cls(**kwargs)
    serialized = channel.serialize()
    with connection.cursor() as cursor:
        name = channel_cls.name()
        print(f'Notifying channel {name} with payload {serialized}')
        cursor.execute(
            f"select pg_notify('{channel_cls.listen_safe_name()}', '{serialized}');")
        if channel_cls.lock_notifications:
            from pgpubsub.models import Notification
            Notification.objects.create(
                channel=name,
                payload=serialized,
            )
    return serialized


def process_stored_notifications():
    """Have processes listening to channels process current stored notifications.

    This function sends a notification with an 'null' payload to all listening channels.
    The result of this is to have the channels process all notifications
    currently in the database. This can be useful if for some reason
    a Notification object was not correctly processed after it initially
    attempted to notify a listener (e.g. if all listeners happened to be
    down at that point).
    """
    with connection.cursor() as cursor:
        lock_channels = [c for c in registry if c.lock_notifications]
        for channel_cls in lock_channels:
            payload = 'null'
            print(f'Notifying channel {channel_cls.name()} with payload {payload}')
            cursor.execute(
                f"select pg_notify('{channel_cls.listen_safe_name()}', '{payload}');")
