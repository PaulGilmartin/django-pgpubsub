import logging
from typing import Type, Union

from django.db import connection
from django.db.transaction import atomic

from pgpubsub.channel import locate_channel, Channel, registry


logger = logging.getLogger(__name__)


@atomic
def notify(channel: Union[Type[Channel], str], **kwargs):
    channel_cls = locate_channel(channel)
    channel = channel_cls(**kwargs)
    serialized = channel.serialize()
    with connection.cursor() as cursor:
        name = channel_cls.name()
        logger.info(f'Notifying channel {name} with payload {serialized}')
        cursor.execute(
            f"select pg_notify('{channel_cls.listen_safe_name()}', '{serialized}');")
        if channel_cls.lock_notifications:
            from pgpubsub.models import Notification
            Notification.objects.create(
                channel=name,
                payload=serialized,
            )
    return serialized


def process_stored_notifications(channels=None):
    """Have processes listening to channels process current stored notifications.

    This function sends a notification with an 'null' payload to all listening channels.
    The result of this is to have the channels process all notifications
    currently in the database. This can be useful if for some reason
    a Notification object was not correctly processed after it initially
    attempted to notify a listener (e.g. if all listeners happened to be
    down at that point).
    """
    if channels is None:
        channels = registry
    else:
        channels = [locate_channel(channel) for channel in channels]
        channels = {
            channel: callbacks
            for channel, callbacks in registry.items()
            if issubclass(channel, tuple(channels))
        }
    with connection.cursor() as cursor:
        lock_channels = [c for c in channels if c.lock_notifications]
        for channel_cls in lock_channels:
            payload = 'null'
            logger.info(
                f'Notifying channel {channel_cls.name()} to recover '
                f'previously stored notifications.\n')
            cursor.execute(
                f"select pg_notify('{channel_cls.listen_safe_name()}', '{payload}');")


