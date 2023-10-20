import datetime
import json
from unittest.mock import patch

from django.db import connection
from django.db.transaction import atomic
from django.db.migrations.recorder import MigrationRecorder
import pytest

from pgpubsub.listen import (
    listen_to_channels,
    process_notifications,
    listen,
)
from pgpubsub.models import Notification
from pgpubsub.notify import process_stored_notifications
from pgpubsub.tests.channels import (
    AuthorTriggerChannel,
    MediaTriggerChannel,
)
from pgpubsub.tests.listeners import post_reads_per_date_cache
from pgpubsub.tests.models import Author, Media, Post


@pytest.fixture()
def pg_connection():
    return listen_to_channels()


@pytest.mark.django_db(transaction=True)
def test_post_fetch_notify(pg_connection):
    author = Author.objects.create(name='Billy')
    Notification.from_channel(channel=AuthorTriggerChannel).get()
    assert 1 == len(pg_connection.notifies)
    today = datetime.date.today()
    post = Post.objects.create(
        author=author, content='first post', date=today)
    assert post_reads_per_date_cache[today] == {}
    Post.fetch(post.pk)
    assert 1 == Notification.objects.count()
    pg_connection.poll()
    assert 2 == len(pg_connection.notifies)
    process_notifications(pg_connection)
    assert post_reads_per_date_cache[today] == {post.pk: 1}
    assert 0 == Notification.objects.count()


@pytest.mark.django_db(transaction=True)
def test_author_insert_notify(pg_connection):
    author = Author.objects.create(name='Billy')
    assert 1 == len(pg_connection.notifies)
    stored_notification = Notification.from_channel(
        channel=AuthorTriggerChannel).get()
    assert 'old' in stored_notification.payload
    assert 'new' in stored_notification.payload
    assert not Post.objects.exists()
    process_notifications(pg_connection)
    assert 1 == Post.objects.count()
    post = Post.objects.last()
    assert post.author == author


@pytest.mark.django_db(transaction=True)
def test_author_insert_notify_in_transaction(pg_connection):
    with atomic():
        author = Author.objects.create(name='Billy')
    pg_connection.poll()
    assert 1 == len(pg_connection.notifies)
    assert not Post.objects.exists()
    process_notifications(pg_connection)
    assert 1 == Post.objects.count()
    post = Post.objects.last()
    assert post.author == author


@pytest.mark.django_db(transaction=True)
def test_author_insert_notify_transaction_rollback(pg_connection):
    class TestException(Exception):
        pass

    try:
        with atomic():
            Author.objects.create(name='Billy')
            raise TestException
    except TestException:
        pass

    # Notifications are only sent when the transaction commits
    pg_connection.poll()
    assert not pg_connection.notifies
    assert not Author.objects.exists()
    assert not Post.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_author_bulk_insert_notify(pg_connection):
    authors = [Author(name='Billy'), Author(name='Craig')]
    with atomic():
        authors = Author.objects.bulk_create(authors)

    # TODO: Understand why pg_connection.poll() is only
    # necessary when we invoke a notification inside
    # a transaction (which happens in a bulk_create).
    pg_connection.poll()
    assert 2 == len(pg_connection.notifies)
    assert not Post.objects.exists()
    process_notifications(pg_connection)
    assert 2 == Post.objects.count()
    post_authors = Post.objects.values_list('author_id', flat=True)
    assert [author.pk for author in authors] == list(post_authors)


def _simulate_listener_does_not_receive_notifications(pg_connection):
    pg_connection.notifies = []
    pg_connection.poll()
    assert 0 == len(pg_connection.notifies)


@pytest.mark.django_db(transaction=True)
def test_process_stored_notifications(pg_connection):
    Author.objects.create(name='Billy')
    Author.objects.create(name='Billy2')
    assert 2 == len(pg_connection.notifies)
    assert 2 == Notification.objects.count()
    assert 0 == Post.objects.count()
    _simulate_listener_does_not_receive_notifications(pg_connection)
    process_stored_notifications()
    pg_connection.poll()
    # One notification for each lockable channel
    assert 5 == len(pg_connection.notifies)
    process_notifications(pg_connection)
    assert 0 == Notification.objects.count()
    assert 2 == Post.objects.count()


@pytest.mark.django_db(transaction=True)
def test_recover_notifications(pg_connection):
    Author.objects.create(name='Billy')
    Author.objects.create(name='Billy2')
    pg_connection.poll()
    assert 2 == len(pg_connection.notifies)
    assert 2 == Notification.objects.count()
    assert 0 == Post.objects.count()
    _simulate_listener_does_not_receive_notifications(pg_connection)
    with patch('pgpubsub.listen.POLL', False):
        listen(recover=True)
    pg_connection.poll()
    assert 0 == Notification.objects.count()
    assert 2 == Post.objects.count()

@pytest.mark.django_db(transaction=True)
def test_recover_multiple_notifications(pg_connection):
    ENTITIES_COUNT = 5
    for i in range(ENTITIES_COUNT):
        Author.objects.create(name=f'Billy{i}')
    pg_connection.poll()
    assert ENTITIES_COUNT == len(pg_connection.notifies)
    assert ENTITIES_COUNT == Notification.objects.count()
    assert 0 == Post.objects.count()
    _simulate_listener_does_not_receive_notifications(pg_connection)
    with patch('pgpubsub.listen.POLL', False):
        listen(recover=True)
    pg_connection.poll()
    assert 0 == Notification.objects.count()
    assert ENTITIES_COUNT == Post.objects.count()


def _create_notification_that_cannot_be_processed():
    notification = Notification.objects.last()
    payload = json.loads(notification.payload)
    payload.pop('app', None)
    notification.payload = json.dumps(payload)
    notification.pk = None
    notification.save()


@pytest.mark.django_db(transaction=True)
def test_recover_notifications_after_exception(pg_connection):
    author = Author.objects.create(name='Billy')
    _create_notification_that_cannot_be_processed()
    Author.objects.create(name='Billy2')

    pg_connection.poll()
    assert 2 == len(pg_connection.notifies)

    assert 3 == Notification.objects.count()
    assert 0 == Post.objects.count()

    _simulate_listener_does_not_receive_notifications(pg_connection)
    with patch('pgpubsub.listen.POLL', False):
        listen(recover=True)
    pg_connection.poll()
    assert 1 == Notification.objects.count()
    assert 2 == Post.objects.count()

@pytest.mark.django_db(transaction=True)
def test_recover_multiple_notifications_after_exception(pg_connection):
    Author.objects.create(name=f'Billy_1')
    Author.objects.create(name=f'Billy_2')
    _create_notification_that_cannot_be_processed()
    Author.objects.create(name=f'Billy_3')
    _create_notification_that_cannot_be_processed()
    _create_notification_that_cannot_be_processed()
    _create_notification_that_cannot_be_processed()
    Author.objects.create(name=f'Billy_4')
    Author.objects.create(name=f'Billy_5')

    GOOD_COUNT = 5
    BROKEN_COUNT = 4

    pg_connection.poll()
    assert GOOD_COUNT == len(pg_connection.notifies)
    assert GOOD_COUNT + BROKEN_COUNT == Notification.objects.count()
    assert 0 == Post.objects.count()

    _simulate_listener_does_not_receive_notifications(pg_connection)
    with patch('pgpubsub.listen.POLL', False):
        listen(recover=True)
    pg_connection.poll()
    assert BROKEN_COUNT == Notification.objects.count()
    assert GOOD_COUNT == Post.objects.count()


@pytest.mark.django_db(transaction=True)
def test_media_insert_notify(pg_connection):
    Media.objects.create(name='avatar.jpg', content_type='image/png', size=15000)
    assert 1 == len(pg_connection.notifies)
    stored_notification = Notification.from_channel(channel=MediaTriggerChannel).get()
    assert 'old' in stored_notification.payload
    assert 'new' in stored_notification.payload


@pytest.fixture
def tx_start_time(django_db_setup):
    with connection.cursor() as cursor:
        cursor.execute("SELECT now();")
        return cursor.fetchone()[0]


@pytest.mark.django_db(transaction=True)
def test_persistent_notification_has_a_creation_timestamp(pg_connection, tx_start_time):
    Media.objects.create(name='avatar.jpg', content_type='image/png', size=15000)
    assert 1 == len(pg_connection.notifies)
    stored_notification = Notification.from_channel(channel=MediaTriggerChannel).get()
    assert stored_notification.created_at >= tx_start_time


@pytest.mark.django_db(transaction=True)
def test_persistent_notification_has_a_db_version(pg_connection, tx_start_time):
    latest_app_migration = MigrationRecorder.Migration.objects.filter(app='tests').latest('id')
    Media.objects.create(name='avatar.jpg', content_type='image/png', size=15000)
    assert 1 == len(pg_connection.notifies)
    stored_notification = Notification.from_channel(channel=MediaTriggerChannel).get()
    assert stored_notification.db_version == latest_app_migration.id
