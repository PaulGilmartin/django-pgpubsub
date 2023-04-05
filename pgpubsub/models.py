from typing import Type

from django.db import models

try:
    from django.db.models import JSONField
except:
    from django.contrib.postgres.fields import JSONField

from pgpubsub.channel import BaseChannel

MAX_POSTGRES_CHANNEL_LENGTH = 63


class Notification(models.Model):
    channel = models.CharField(max_length=MAX_POSTGRES_CHANNEL_LENGTH)
    payload = JSONField()

    def __repr__(self):
        return (
            f'Notification('
            f'  channel={self.channel},'
            f'  payload={self.payload}'
            f')')

    @classmethod
    def from_channel(cls, channel: Type[BaseChannel]):
        return cls.objects.filter(channel=channel.listen_safe_name())
