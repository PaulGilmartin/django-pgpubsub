from dataclasses import dataclass
import datetime
from typing import Dict, List, Set, Tuple

from django.db.transaction import atomic
import pytest

from pgpubsub.channel import Channel
from pgpubsub.listen import listen_to_channels, process_notifications
from pgpubsub.models import Notification
from pgpubsub.notify import process_stored_notifications
from pgpubsub.tests.channels import AuthorTriggerChannel
from pgpubsub.tests.listeners import post_reads_per_date_cache
from pgpubsub.tests.models import Author, Post


def test_deserialize_1():
    @dataclass
    class MyChannel(Channel):
        arg1: str
        arg2: Dict[int, int]
        default_arg1: float = 0.0

    deserialized = _deserialize(MyChannel, arg1='1', arg2={1: 2}, default_arg1=3.4)
    assert {'arg1': '1', 'arg2': {1: 2},
            'default_arg1': 3.4} == deserialized


def test_deserialize_2():
    @dataclass
    class MyChannel(Channel):
        arg1: Dict[str, bool]
        default_arg1: bool = False
        default_arg2: int = 0

    deserialized = _deserialize(
        MyChannel, arg1={'Paul': False}, default_arg1=True)
    assert {'arg1': {'Paul': False},
            'default_arg1': True,
            'default_arg2': 0} == deserialized


def test_deserialize_3():
    @dataclass
    class MyChannel(Channel):
        arg1: datetime.date
        arg2: Dict[datetime.date, bool]
        arg3: Dict[str, datetime.datetime]

    deserialized = _deserialize(
        MyChannel,
        arg1=datetime.date(2021, 1, 1),
        arg2={
            datetime.date(2021, 1, 7): True,
            datetime.date(2021, 1, 17): False,
        },
        arg3={'chosen_date': datetime.datetime(2021, 1, 1, 9, 30)},
    )

    assert {
        'arg1': datetime.date(2021, 1, 1),
        'arg2': {datetime.date(2021, 1, 7): True,
                 datetime.date(2021, 1, 17): False},
        'arg3': {'chosen_date': datetime.datetime(2021, 1, 1, 9, 30)},
    } == deserialized


def _deserialize(channel_cls, **kwargs):
    serialized = channel_cls(**kwargs).serialize()
    return channel_cls.deserialize(serialized)


def test_deserialize_4():
    @dataclass
    class MyChannel(Channel):
        arg1: List[datetime.date]
        arg2: Set[float]
        arg3: Tuple[str]

    deserialized = _deserialize(
        MyChannel,
        arg1=[datetime.date(2021, 1, 1), datetime.date(2021, 1, 2)],
        arg2={1.0, 2.1},
        arg3=('hello', 'world'),
    )
    assert {
        'arg1': [datetime.date(2021, 1, 1), datetime.date(2021, 1, 2)],
        'arg2': {1.0, 2.1},
        'arg3': ('hello', 'world'),
    } == deserialized


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


@pytest.mark.django_db(transaction=True)
def test_process_stored_notifications(pg_connection):
    Author.objects.create(name='Billy')
    Author.objects.create(name='Billy2')
    assert 2 == len(pg_connection.notifies)
    assert 2 == Notification.objects.count()
    assert 0 == Post.objects.count()
    # Simulate when the listener fails to
    # receive notifications
    pg_connection.notifies = []
    pg_connection.poll()
    assert 0 == len(pg_connection.notifies)
    process_stored_notifications()
    pg_connection.poll()
    # One notification for each lockable channel
    assert 2 == len(pg_connection.notifies)
    process_notifications(pg_connection)
    assert 0 == Notification.objects.count()
    assert 2 == Post.objects.count()
