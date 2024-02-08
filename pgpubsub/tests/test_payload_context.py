import json
import os

import pytest

import pgpubsub
from django.db import connection, connections
from django.db.models import Q
from django.db.transaction import atomic
from pgpubsub.listen import process_notifications
from pgpubsub.listeners import ListenerFilterProvider
from pgpubsub.models import Notification
from pgpubsub.notify import process_stored_notifications
from pgpubsub.tests.channels import (
    MediaTriggerChannel,
)
from pgpubsub.tests.connection import simulate_listener_does_not_receive_notifications
from pgpubsub.tests.models import Author, Media, Post


@pytest.mark.django_db(transaction=True)
def test_empty_notification_context_is_stored_in_payload_by_default(pg_connection):
    Media.objects.create(name='avatar.jpg', content_type='image/png', size=15000)
    stored_notification = Notification.from_channel(channel=MediaTriggerChannel).get()
    assert stored_notification.payload['context'] == {}

    pg_connection.poll()
    assert 1 == len(pg_connection.notifies)


@pytest.mark.parametrize("db", [None, "default"])
@pytest.mark.django_db(transaction=True)
def test_notification_context_is_stored_in_payload(pg_connection, db):
    with atomic():
        pgpubsub.set_notification_context({'test_key': 'test-value'}, using=db)
        Media.objects.create(name='avatar.jpg', content_type='image/png', size=15000)

    stored_notification = Notification.from_channel(channel=MediaTriggerChannel).get()
    assert stored_notification.payload['context'] == {'test_key': 'test-value'}

    pg_connection.poll()
    assert 1 == len(pg_connection.notifies)


def test_set_notification_context_is_noop_if_transaction_needs_rollback(db):
    with atomic():
        try:
            with connection.cursor() as cur:
                cur.execute("invalid sql")
        except Exception:
            pass
        pgpubsub.set_notification_context({'test_key': 'test-value'})
        connection.set_rollback(True)


@pytest.mark.parametrize("db", [None, "default"])
@pytest.mark.django_db(transaction=True)
def test_notification_context_is_cleared_after_transaction_end(pg_connection, db):
    with atomic():
        pgpubsub.set_notification_context({'test_key': 'test-value'}, using=db)

    Media.objects.create(name='avatar.jpg', content_type='image/png', size=15000)

    stored_notification = Notification.from_channel(channel=MediaTriggerChannel).get()
    assert stored_notification.payload['context'] == {}

    pg_connection.poll()
    assert 1 == len(pg_connection.notifies)


@pytest.mark.django_db(transaction=True)
def test_process_notifications_gets_all_notifications_by_default(pg_connection):
    Author.objects.create(name='no-filter')
    assert not Post.objects.exists()
    process_notifications(pg_connection)
    assert 1 == Post.objects.filter(author__name='no-filter').count()


class TestListenerFilterProvider(ListenerFilterProvider):
    __test__ = False
    def get_filter(self) -> Q:
        return Q(payload__context__test_key='test-value')


@pytest.mark.django_db(transaction=True)
def test_process_notifications_filters_out_nonmatching_notifications(
    pg_connection, settings
):
    Author.objects.create(name='nonmatching')
    with atomic():
        pgpubsub.set_notification_context({'test_key': 'test-value'})
        Author.objects.create(name='matching')

    settings.PGPUBSUB_LISTENER_FILTER = 'pgpubsub.tests.test_payload_context.TestListenerFilterProvider'
    assert not Post.objects.exists()
    process_notifications(pg_connection)
    assert 1 == Post.objects.filter(author__name='matching').count()
    assert 0 == Post.objects.filter(author__name='nonmatching').count()


@pytest.mark.django_db(transaction=True)
def test_process_notifications_recovery_filters_out_nonmatching_notifications(
    pg_connection, settings
):
    Author.objects.create(name='nonmatching')
    with atomic():
        pgpubsub.set_notification_context({'test_key': 'test-value'})
        Author.objects.create(name='matching')

    settings.PGPUBSUB_LISTENER_FILTER = 'pgpubsub.tests.test_payload_context.TestListenerFilterProvider'
    assert not Post.objects.exists()

    simulate_listener_does_not_receive_notifications(pg_connection)
    process_stored_notifications()
    process_notifications(pg_connection)
    assert 1 == Post.objects.filter(author__name='matching').count()
    assert 0 == Post.objects.filter(author__name='nonmatching').count()


@pytest.mark.django_db(transaction=True)
def test_payload_context_may_be_passed_to_listener_callback(
        pg_connection, settings
):
    settings.PGPUBSUB_PASS_CONTEXT_TO_LISTENERS = True
    with atomic():
        pgpubsub.set_notification_context({'content': 'overriden content'})
        Author.objects.create(name='I like overrides')

    assert not Post.objects.exists()
    process_notifications(pg_connection)
    post = Post.objects.all().first()
    assert post is not None
    assert post.content == 'overriden content'
