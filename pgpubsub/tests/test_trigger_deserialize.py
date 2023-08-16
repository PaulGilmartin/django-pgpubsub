import datetime
import json
from dataclasses import dataclass
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from pgpubsub import TriggerChannel
from pgpubsub.models import Notification
from pgpubsub.tests.channels import (
    AuthorTriggerChannel,
    ChildTriggerChannel,
    ChildOfAbstractTriggerChannel,
    MediaTriggerChannel,
    PostTriggerChannel,
)
from pgpubsub.tests.models import Post, Author, Child, ChildOfAbstract, Media


def test_deserialize_post_trigger_channel():
    @dataclass
    class MyChannel(TriggerChannel):
        model: Post

    some_datetime = datetime.datetime.utcnow()
    post = Post(content='some-content', date=some_datetime, pk=1, rating=Decimal("1.1"))

    deserialized = MyChannel.deserialize(
        json.dumps(
            {
                'app': 'tests',
                'model': 'Post',
                'old': None,
                'new': {
                    'content': 'some-content',
                    'date': some_datetime.isoformat(),
                    'id': post.pk,
                    # See https://github.com/Opus10/django-pgpubsub/issues/29
                    'old_field': 'foo',
                    'rating': Decimal("1.1"),
                },
            },
            cls=DjangoJSONEncoder,
        )
    )
    assert deserialized['new'].date == some_datetime
    assert deserialized['new'].content == post.content
    assert deserialized['new'].rating == post.rating
    assert deserialized['new'].author == post.author


@pytest.mark.django_db(transaction=True)
def test_deserialize_insert_payload():
    user = User.objects.create(username='Billy')
    media = Media.objects.create(
        name='avatar.jpg',
        content_type='image/png',
        size=15000,
    )
    author = Author.objects.create(
        name='Billy',
        user=user,
        alternative_name='Jimmy',
        profile_picture=media,
    )
    # Notification comes from the AuthorTriggerChannel
    # and contains a serialized version of the author
    # object in the payload attribute.
    insert_notification = Notification.from_channel(
        channel=AuthorTriggerChannel).get()
    deserialized = AuthorTriggerChannel.deserialize(
        insert_notification.payload)

    assert deserialized['new'].name == author.name
    assert deserialized['new'].alternative_name == author.alternative_name
    assert deserialized['new'].id == author.pk
    assert deserialized['new'].user == author.user
    assert deserialized['new'].profile_picture == author.profile_picture


@pytest.mark.django_db(transaction=True)
def test_deserialize_edit_payload():
    media = Media.objects.create(
        name='avatar.jpg',
        content_type='image/png',
        size=15000,
        store_id="some-value",
    )
    assert 1 == Notification.objects.all().count()
    insert_notification = Notification.from_channel(
        channel=MediaTriggerChannel).last()

    deserialized = MediaTriggerChannel.deserialize(
        insert_notification.payload)

    assert media.name == deserialized['new'].name
    assert media.pk == deserialized['new'].pk
    assert media.key == deserialized['new'].key
    assert media.size == deserialized['new'].size
    assert media.store_id == deserialized['new'].store_id

    media.name = 'avatar_2.jpg'
    media.save()

    assert 2 == Notification.objects.all().count()
    edit_notification = Notification.from_channel(
        channel=MediaTriggerChannel).last()

    deserialized = MediaTriggerChannel.deserialize(
        edit_notification.payload)

    assert deserialized['new'].name == media.name
    assert deserialized['new'].pk == media.pk
    assert deserialized['new'].key == media.key
    assert deserialized['new'].size == media.size
    assert media.store_id == deserialized['new'].store_id


@pytest.mark.django_db(transaction=True)
def test_deserialize_delete_payload():
    user = User.objects.create(username='Billy')
    author = Author.objects.create(name='Billy', user=user)

    post = Post.objects.create(
        author=author,
        content='my post',
        date=timezone.now(),
    )
    original_id = post.pk

    # When we delete a post, a notification is sent via
    # PostTriggerChannel
    post.delete()
    delete_notification = Notification.from_channel(
        channel=PostTriggerChannel).get()
    deserialized = PostTriggerChannel.deserialize(
        delete_notification.payload)

    assert deserialized['old'].author == post.author
    assert deserialized['old'].date.date() == post.date.date()
    assert deserialized['old'].date.time() == post.date.time()
    assert deserialized['old'].id == original_id
    assert deserialized['new'] is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "cls,trigger_channel_cls",
    [
        (Child, ChildTriggerChannel),
        (ChildOfAbstract, ChildOfAbstractTriggerChannel)
    ]
)
def test_deserialize_child_payload(cls, trigger_channel_cls):
    child = cls.objects.create()

    assert 1 == Notification.objects.all().count()
    insert_notification = Notification.from_channel(channel=trigger_channel_cls).last()

    deserialized = trigger_channel_cls.deserialize(insert_notification.payload)

    assert child.pk == deserialized['new'].pk
    assert child.key == deserialized['new'].key
