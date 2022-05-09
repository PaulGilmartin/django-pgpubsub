from __future__ import unicode_literals

import datetime

from django.contrib.auth.models import User
from django.db import models

from pgpubsub.notify import notify


class Media(models.Model):
    name = models.TextField()
    content_type = models.TextField(null=True)
    size = models.BigIntegerField(null=True)


class Author(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    name = models.TextField()
    age = models.IntegerField(null=True)
    active = models.BooleanField(default=True)
    profile_picture = models.ForeignKey(Media, null=True, on_delete=models.PROTECT)


class Post(models.Model):
    content = models.TextField()
    date = models.DateTimeField()
    author = models.ForeignKey(
        Author, null=True, on_delete=models.SET_NULL, related_name='entries'
    )
    files = models.ManyToManyField('Media')
    rating = models.DecimalField(null=True, decimal_places=20, max_digits=40)

    @classmethod
    def fetch(cls, post_id):
        post = cls.objects.get(pk=post_id)
        notify(
            'pgpubsub.tests.channels.PostReads',
            model_id=post_id,
            date=datetime.date.today(),
        )
        return post
