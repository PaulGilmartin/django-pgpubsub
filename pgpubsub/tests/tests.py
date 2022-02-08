import datetime
import select
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple
from unittest import TestCase
from unittest.mock import patch

import psycopg2
import pytest
from django.db.transaction import atomic
from django.test import TransactionTestCase

from pgpubsub.channel import Channel
from pgpubsub.listen import listen_to_channels, process_notifications
from pgpubsub.notify import notify
from pgpubsub.tests.channels import PostReads
from pgpubsub.tests.listeners import post_reads_per_date_cache
from pgpubsub.tests.models import Author, Post


class TestChannelDeserialize(TestCase):
    def test_deserialize_1(self):
        @dataclass
        class MyChannel(Channel):
            arg1: str
            arg2: Dict[int, int]
            default_arg1: float = 0.0

        deserialized = self._deserialize(
            MyChannel, arg1='1', arg2={1:2}, default_arg1=3.4)
        self.assertEqual(
            {'arg1': '1', 'arg2': {1: 2}, 'default_arg1': 3.4},
            deserialized,
        )

    def test_deserialize_2(self):
        @dataclass
        class MyChannel(Channel):
            arg1: Dict[str, bool]
            default_arg1: bool=False
            default_arg2: int = 0

        deserialized = self._deserialize(
            MyChannel, arg1={'Paul': False}, default_arg1=True)
        self.assertEqual(
            {'arg1': {'Paul': False}, 'default_arg1': True, 'default_arg2': 0},
            deserialized,
        )

    def test_deserialize_3(self):
        @dataclass
        class MyChannel(Channel):
            arg1: datetime.date
            arg2: Dict[datetime.date, bool]
            arg3: Dict[str, datetime.datetime]

        deserialized = self._deserialize(
            MyChannel,
            arg1=datetime.date(2021, 1, 1),
            arg2={
                datetime.date(2021, 1, 7): True,
                datetime.date(2021, 1, 17): False,
            },
            arg3={'chosen_date': datetime.datetime(2021, 1, 1, 9, 30)},
        )

        self.assertEqual(
            {'arg1': datetime.date(2021, 1, 1),
             'arg2': {datetime.date(2021, 1, 7): True, datetime.date(2021, 1, 17): False},
             'arg3': {'chosen_date': datetime.datetime(2021, 1, 1, 9, 30)},
             },
            deserialized,
        )

    def test_deserialize_4(self):
        @dataclass
        class MyChannel(Channel):
            arg1: List[datetime.date]
            arg2: Set[float]
            arg3: Tuple[str]

        deserialized = self._deserialize(
            MyChannel,
            arg1=[datetime.date(2021, 1, 1), datetime.date(2021, 1, 2)],
            arg2={1.0, 2.1},
            arg3=('hello', 'world'),
        )
        self.assertEqual(
            {'arg1': [datetime.date(2021, 1, 1), datetime.date(2021, 1, 2)],
             'arg2': {1.0, 2.1},
             'arg3': ('hello', 'world'),
             },
            deserialized,
        )

    def _deserialize(self, channel_cls, **kwargs):
        serialized = channel_cls(**kwargs)._serialize()
        return channel_cls.deserialize(serialized)


@pytest.mark.django_db
class TestListenNotify(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.pg_connection = listen_to_channels()

    def test_post_fetch_notify(self):
        author = Author.objects.create(name='Billy')
        self.assertEqual(1, len(self.pg_connection.notifies))
        today = datetime.date.today()
        post = Post.objects.create(
            author=author, content='first post', date=today)
        self.assertEqual(post_reads_per_date_cache[today], {})
        Post.fetch(post.pk)
        self.assertEqual(2, len(self.pg_connection.notifies))
        process_notifications(self.pg_connection)
        self.assertEqual(post_reads_per_date_cache[today], {post.pk: 1})

    def test_author_insert_notify(self):
        author = Author.objects.create(name='Billy')
        self.assertEqual(1, len(self.pg_connection.notifies))
        self.assertEqual(0, Post.objects.count())
        process_notifications(self.pg_connection)
        self.assertEqual(1, Post.objects.count())
        post = Post.objects.last()
        self.assertEqual(post.author, author)

    def test_author_insert_notify_in_transaction(self):
        with atomic():
            author = Author.objects.create(name='Billy')
        # TODO: Understand why self.pg_connection.poll() is only
        # necessary when we invoke a notification inside
        # a transaction.
        self.pg_connection.poll()
        self.assertEqual(1, len(self.pg_connection.notifies))
        self.assertEqual(0, Post.objects.count())
        process_notifications(self.pg_connection)
        self.assertEqual(1, Post.objects.count())
        post = Post.objects.last()
        self.assertEqual(post.author, author)

    def test_author_insert_notify_transaction_rollback(self):
        class TestException(Exception):
            pass

        try:
            with atomic():
                Author.objects.create(name='Billy')
                raise TestException
        except TestException:
            pass

        # Notifications are only sent when the transaction commits
        self.pg_connection.poll()
        self.assertEqual(0, len(self.pg_connection.notifies))
        self.assertEqual(0, Author.objects.count())
        self.assertEqual(0, Post.objects.count())

    def test_author_bulk_insert_notify(self):
        authors = [Author(name='Billy'), Author(name='Craig')]
        with atomic():
            authors = Author.objects.bulk_create(authors)
        # TODO: Understand why self.pg_connection.poll() is only
        # necessary when we invoke a notification inside
        # a transaction (which happens in a bulk_create).
        self.pg_connection.poll()
        self.assertEqual(2, len(self.pg_connection.notifies))
        self.assertEqual(0, Post.objects.count())
        process_notifications(self.pg_connection)
        self.assertEqual(2, Post.objects.count())
        post_authors = Post.objects.values_list('author_id', flat=True)
        self.assertEqual(
            [author.pk for author in authors], list(post_authors))

    @patch('pgpubsub.tests.listeners.email')
    def test_post_delete_notify(self, mock_email):
        author = Author.objects.create(name='Billy')
        process_notifications(self.pg_connection)
        self.assertEqual(1, Post.objects.count())
        Post.objects.all().delete()
        process_notifications(self.pg_connection)
        mock_email.assert_called_with(author)
