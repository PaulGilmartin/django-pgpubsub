from dataclasses import dataclass
import datetime

from pgpubsub.channel import Channel, TriggerChannel
from pgpubsub.tests.models import Author, Post


@dataclass
class Reads(Channel):
    model_id: int
    model_type: str
    date: datetime.date = None


@dataclass
class PostReads(Reads):
    model_type: str = 'Post'


@dataclass
class AuthorTriggerChannel(TriggerChannel):
    model = Author
    lock_notifications = True


@dataclass
class PostTriggerChannel(TriggerChannel):
    model = Post
    lock_notifications = True
