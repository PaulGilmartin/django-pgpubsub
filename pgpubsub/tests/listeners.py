import datetime
from collections import defaultdict

from pgpubsub.tests.models import Author, Post
from pgpubsub.listen import listener, post_insert_listener
from pgpubsub.channel import TriggerPayload


post_reads_per_date_cache = defaultdict(dict)


@listener('post_reads_per_date')
def post_reads_per_date(
    *,
    post_id: int,
    date: datetime.date,
):
    print(f'Processing post_reads_per_date with args {post_id}, {date}')
    print(f'Cache before: {post_reads_per_date_cache}')
    current_count = post_reads_per_date_cache[date].get(post_id, 0)
    post_reads_per_date_cache[date][post_id] = current_count + 1
    print(f'Cache after: {post_reads_per_date_cache}')


@post_insert_listener(channel_name='author_insert', model=Author)
def create_first_post_for_author(trigger_payload: TriggerPayload):
    new_author = trigger_payload.new
    print(f'Creating first post for {new_author.name}')
    Post.objects.create(
        author_id=new_author.pk,
        content='Welcome! This is your first post',
        date=datetime.date.today(),
    )
