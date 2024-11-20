import datetime
from decimal import Decimal
from typing import Callable
from unittest.mock import Mock

import pytest
from django.db import transaction

from pgpubsub.channel import registry
from pgpubsub.compatibility import Notify
from pgpubsub.listen import (
    FullPayloadLockableNotificationProcessor,
    InvalidNotificationProcessor,
    LockableNotificationProcessor,
)
from pgpubsub.models import Notification
from pgpubsub.tests.channels import PostTriggerChannel
from pgpubsub.tests.models import Post


@pytest.fixture
def pg_connection() -> Mock:
    return Mock()


def pg_notification(channel: str, payload: str) -> Notify:
    return Notify(channel=channel, payload=payload, pid=1)


@pytest.fixture
def callback() -> Mock:
    mock = Mock()
    PostTriggerChannel.register(mock)
    yield mock
    del registry[PostTriggerChannel]


SOME_DATETIME = datetime.datetime.utcnow()

CHANNEL_NAME = PostTriggerChannel.listen_safe_name()


@pytest.mark.django_db(transaction=True)
def test_lockable_notification_processor_processes_legacy_insert_payload(
    callback: Callable, pg_connection
):
    post = Post(content='some-content', date=SOME_DATETIME, pk=1, rating=Decimal("1.1"))
    stored_payload = f"""
        {{
            "app": "tests",
            "model": "Post",
            "old": null,
            "new": {{
                "content": "{post.content}",
                "date": "{SOME_DATETIME.isoformat()}",
                "id": {post.pk},
                "rating": "1.1"
            }}
        }}
    """
    notification = Notification.objects.create(
        channel=CHANNEL_NAME, payload=stored_payload
    )

    sut = FullPayloadLockableNotificationProcessor(
        pg_notification(channel=CHANNEL_NAME, payload=stored_payload), pg_connection
    )

    with transaction.atomic():
        sut.process()

    callback.assert_called_with(old=None, new=post)

@pytest.mark.django_db(transaction=True)
def test_lockable_notification_processor_processes_legacy_update_payload(
    callback: Callable, pg_connection
):
    old_post = Post(
        content='some-old-content', date=SOME_DATETIME, pk=1, rating=Decimal("1.2")
    )
    new_post = Post(
        content='some-new-content', date=SOME_DATETIME, pk=1, rating=Decimal("1.3")
    )
    stored_payload = f"""
        {{
            "app": "tests",
            "model": "Post",
            "old": {{
                "content": "{old_post.content}",
                "date": "{SOME_DATETIME.isoformat()}",
                "id": 1,
                "rating": "1.1"
            }},
            "new": {{
                "content": "{new_post.content}",
                "date": "{SOME_DATETIME.isoformat()}",
                "id": 1,
                "rating": "1.2"
            }}
        }}
    """
    notification = Notification.objects.create(
        channel=CHANNEL_NAME, payload=stored_payload
    )

    sut = FullPayloadLockableNotificationProcessor(
        pg_notification(channel=CHANNEL_NAME, payload=stored_payload), pg_connection
    )

    with transaction.atomic():
        sut.process()

    callback.assert_called_with(old=old_post, new=new_post)


@pytest.mark.django_db(transaction=True)
def test_legacy_lockable_notification_processor_does_not_support_id_only_payloads(
    callback: Callable, pg_connection
):
    stored_payload = f"""
        {{
            "app": "tests",
            "model": "Post",
            "old": {{
                "content": "old_content",
                "date": "{SOME_DATETIME.isoformat()}",
                "id": 1,
                "rating": "1.1"
            }},
            "new": {{
                "content": "new_content",
                "date": "{SOME_DATETIME.isoformat()}",
                "id": 1,
                "rating": "1.2"
            }}
        }}
    """
    notification = Notification.objects.create(
        channel=CHANNEL_NAME, payload=stored_payload
    )

    with pytest.raises(InvalidNotificationProcessor):
        FullPayloadLockableNotificationProcessor(
            pg_notification(channel=CHANNEL_NAME, payload=str(notification.id)),
            pg_connection,
        )


@pytest.mark.django_db(transaction=True)
def test_lockable_notification_processor_processes_id_only_payload_for_insert(
    callback: Callable, pg_connection
):
    post = Post(content='some-content', date=SOME_DATETIME, pk=1, rating=Decimal("1.2")
    )
    stored_payload = f"""
        {{
            "app": "tests",
            "model": "Post",
            "old": null,
            "new": {{
                "content": "{post.content}",
                "date": "{SOME_DATETIME.isoformat()}",
                "id": {post.pk},
                "rating": "1.1"
            }}
        }}
    """
    notification = Notification.objects.create(
        channel=CHANNEL_NAME, payload=stored_payload
    )

    sut = LockableNotificationProcessor(
        pg_notification(channel=CHANNEL_NAME, payload=str(notification.id)),
        pg_connection,
    )

    with transaction.atomic():
        sut.process()

    callback.assert_called_with(old=None, new=post)


@pytest.mark.django_db(transaction=True)
def test_lockable_notification_processor_processes_id_only_payload_for_update(
    callback: Callable, pg_connection
):
    old_post = Post(
        content='some-old-content', date=SOME_DATETIME, pk=1, rating=Decimal("1.2")
    )
    new_post = Post(
        content='some-new-content', date=SOME_DATETIME, pk=1, rating=Decimal("1.3")
    )
    stored_payload = f"""
        {{
            "app": "tests",
            "model": "Post",
            "old": {{
                "content": "{old_post.content}",
                "date": "{SOME_DATETIME.isoformat()}",
                "id": 1,
                "rating": "1.1"
            }},
            "new": {{
                "content": "{new_post.content}",
                "date": "{SOME_DATETIME.isoformat()}",
                "id": 1,
                "rating": "1.2"
            }}
        }}
    """
    notification = Notification.objects.create(
        channel=CHANNEL_NAME, payload=stored_payload
    )

    sut = LockableNotificationProcessor(
        pg_notification(channel=CHANNEL_NAME, payload=str(notification.id)),
        pg_connection,
    )

    with transaction.atomic():
        sut.process()

    callback.assert_called_with(old=old_post, new=new_post)
