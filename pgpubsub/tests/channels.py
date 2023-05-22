from dataclasses import dataclass
import datetime

from pgpubsub.channel import Channel, TriggerChannel
from pgpubsub.tests.models import Author, Child, ChildOfAbstract, Media, Post


@dataclass
class Reads(Channel):
    model_id: int
    model_type: str
    date: datetime.date = None


@dataclass
class PostReads(Reads):
    model_type: str = 'Post'


@dataclass
class MediaTriggerChannel(TriggerChannel):
    model = Media
    lock_notifications = True


@dataclass
class ChildTriggerChannel(TriggerChannel):
    model = Child
    lock_notifications = True


@dataclass
class ChildOfAbstractTriggerChannel(TriggerChannel):
    model = ChildOfAbstract
    lock_notifications = True


@dataclass
class AuthorTriggerChannel(TriggerChannel):
    model = Author
    lock_notifications = True


@dataclass
class PostTriggerChannel(TriggerChannel):
    model = Post
    lock_notifications = True
