import json
from typing import Type

from django.db import models, connection

from pgpubsub.channel import BaseChannel, registry

MAX_POSTGRES_CHANNEL_LENGTH = 63


class Notification(models.Model):
    channel = models.CharField(
        max_length=MAX_POSTGRES_CHANNEL_LENGTH)
    payload = models.JSONField()

    def __repr__(self):
        return (
            f'Notification('
            f'  channel={self.channel},'
            f'  payload={self.payload}'
            f')')

    @classmethod
    def from_channel(cls, channel: Type[BaseChannel]):
        return cls.objects.filter(channel=channel.listen_safe_name())

    @classmethod
    def process_stored_notifications(cls):
        """Have processes listening to channels process current stored notifications.

        This function send a notification with an empty to all listening channels.
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
