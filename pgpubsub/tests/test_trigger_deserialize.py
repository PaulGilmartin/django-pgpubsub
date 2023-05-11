import datetime
import json
from dataclasses import dataclass
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from pgpubsub import TriggerChannel
from pgpubsub.models import Notification
from pgpubsub.tests.channels import (
    AuthorTriggerChannel,
    MediaTriggerChannel,
    PostTriggerChannel,
)
from pgpubsub.tests.models import Post, Author, Media


@pytest.mark.django_db
def test_deserialize_post_trigger_channel_of_current_version():
    last_migration = MigrationRecorder.Migration.objects.latest('id')

    some_datetime = datetime.datetime.utcnow()
    original_content = 'original-content'
    post = Post.objects.create(
        content=original_content, date=some_datetime, pk=1, rating=Decimal("1.1")
    )
    post.content = 'updated-content'
    post.save()

    deserialized = PostTriggerChannel.deserialize(
        json.dumps(
            {
                'app': 'tests',
                'model': 'Post',
                'old': None,
                'new': {
                    'content': original_content,
                    'date': some_datetime.isoformat(),
                    'id': post.pk,
                    # See https://github.com/Opus10/django-pgpubsub/issues/29
                    'old_field': 'foo',
                    'rating': Decimal("1.1"),
                },
                'db_version': last_migration.id,
            },
            cls=DjangoJSONEncoder,
        )
    )
    assert deserialized['new'].date == some_datetime
    assert deserialized['new'].content == original_content
    assert deserialized['new'].rating == post.rating
    assert deserialized['new'].author == post.author


@pytest.mark.django_db
def test_deserialize_post_trigger_channel_of_the_serialized_form_without_db_version():
    last_migration = MigrationRecorder.Migration.objects.latest('id')

    some_datetime = datetime.datetime.utcnow()
    original_content = 'original-content'
    post = Post.objects.create(content=original_content, date=some_datetime, pk=1)
    post.content = 'updated-content'
    post.save()

    deserialized = PostTriggerChannel.deserialize(
        json.dumps(
            {
                'app': 'tests',
                'model': 'Post',
                'old': None,
                'new': {
                    'content': original_content,
                    'date': some_datetime.isoformat(),
                    'id': post.pk,
                },
            },
        )
    )
    assert deserialized['new'].date == some_datetime
    assert deserialized['new'].content == original_content


@pytest.mark.django_db
def test_deserialize_post_trigger_channel_of_outdated_version():
    not_last_migration = MigrationRecorder.Migration.objects.all().order_by('-id')[1]

    latest_post = Post.objects.create(
        content='some-content', date=datetime.datetime.utcnow()
    )

    deserialized = PostTriggerChannel.deserialize(
        json.dumps(
            {
                'app': 'tests',
                'model': 'Post',
                'old': None,
                'new': {
                    'content': 'outdated-content',
                    'id': latest_post.pk,
                    'old_field': 'foo',
                },
                'db_version': not_last_migration.id,
            },
            cls=DjangoJSONEncoder,
        )
    )
    assert deserialized['new'].date == latest_post.date
    assert deserialized['new'].content == latest_post.content
    assert deserialized['old'] is None


@pytest.mark.django_db
def test_deserialize_post_trigger_channel_of_outdated_version_when_obj_is_deleted():
    not_last_migration = MigrationRecorder.Migration.objects.all().order_by('-id')[1]

    latest_post = Post.objects.create(content='some-content', date=datetime.datetime.utcnow())
    latest_post.delete()

    deserialized = PostTriggerChannel.deserialize(
        json.dumps(
            {
                'app': 'tests',
                'model': 'Post',
                'old': None,
                'new': {
                    'content': 'outdated-content',
                    'id': latest_post.pk,
                    'old_field': 'foo',
                },
                'db_version': not_last_migration.id,
            },
        )
    )
    assert deserialized['old'] is None
    assert deserialized['new'] is None


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
    )
    assert 1 == Notification.objects.all().count()
    insert_notification = Notification.from_channel(
        channel=MediaTriggerChannel).last()

    deserialized = MediaTriggerChannel.deserialize(
        insert_notification.payload)

    assert media.name == deserialized['new'].name
    assert media.pk == deserialized['new'].id
    assert media.size == deserialized['new'].size

    media.name = 'avatar_2.jpg'
    media.save()

    assert 2 == Notification.objects.all().count()
    edit_notification = Notification.from_channel(
        channel=MediaTriggerChannel).last()

    deserialized = MediaTriggerChannel.deserialize(
        edit_notification.payload)

    assert deserialized['new'].name == media.name
    assert deserialized['new'].id == media.pk
    assert deserialized['new'].size == media.size


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
