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
    # The field is made nullable to make sure the addiion of the new field is backward
    # compatible. From the version this change is release the field is effectively non
    # nullable as in it always gets a value.
    # After some time the field should be made non nullable here.
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __repr__(self):
        return (
            f'Notification('
            f'channel={self.channel},'
            f' payload={self.payload},'
            f' created_at={self.created_at}'
            f')'
        )

    @classmethod
    def from_channel(cls, channel: Type[BaseChannel]):
        return cls.objects.filter(channel=channel.listen_safe_name())
