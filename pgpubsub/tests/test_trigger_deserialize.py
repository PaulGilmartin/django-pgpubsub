import datetime
import json
from dataclasses import dataclass

import pytest
from django.contrib.auth.models import User

from pgpubsub import TriggerChannel
from pgpubsub.models import Notification
from pgpubsub.tests.channels import AuthorTriggerChannel
from pgpubsub.tests.models import Post, Author


def test_deserialize_post_trigger_channel():
    @dataclass
    class MyChannel(TriggerChannel):
        model: Post

    some_datetime = datetime.datetime.utcnow()
    post = Post(content='some-content', date=some_datetime, pk=1)

    deserialized = MyChannel.deserialize(
        json.dumps(
            {
                'app': 'tests',
                'model': 'Post',
                'old': None,
                'new': {
                    'content': 'some-content',
                    'date': some_datetime.isoformat(),
                    'pk': 1,
                },
            }
        )
    )
    assert deserialized['new'].date == some_datetime
    assert deserialized['new'].content == post.content
    assert deserialized['new'].rating == post.rating
    assert deserialized['new'].author == post.author


@pytest.mark.django_db(transaction=True)
def test_deserialize_author_trigger_channel():
    user = User.objects.create(username='Billy')
    author = Author.objects.create(name='Billy', user=user)

    assert 1 == Notification.objects.all().count()

    notification = Notification.objects.last()
    deserialized = AuthorTriggerChannel.deserialize(notification.payload)

    assert author.name == deserialized['new'].name
    assert author.pk == deserialized['new'].id
    assert author.user == deserialized['new'].user
