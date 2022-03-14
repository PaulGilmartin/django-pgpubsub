from __future__ import unicode_literals

from django.db import models


MAX_POSTGRES_CHANNEL_LENGTH = 63

class Notification(models.Model):
    creation_datetime = models.DateTimeField(auto_now_add=True)
    channel = models.CharField(
        db_index=True,
        max_length=MAX_POSTGRES_CHANNEL_LENGTH,
    )
    payload = models.JSONField()
    uuid = models.UUIDField(db_index=True)

    def __repr__(self):
        return (
            f'Notification('
            f' channel={self.channel},'
            f' uuid={self.uuid},'
            f' payload={self.payload}'
            f')'
        )
