from __future__ import unicode_literals

from django.db import models


MAX_POSTGRES_CHANNEL_LENGTH = 63

class Notification(models.Model):
    channel = models.CharField(max_length=MAX_POSTGRES_CHANNEL_LENGTH)
    payload = models.JSONField()

    def __repr__(self):
        return f'Notification(channel={self.channel}, payload={self.payload})'

