import multiprocessing
import time
from collections import defaultdict
import datetime

from django.db.transaction import atomic

from pgpubsub.listen import (
    listener,
    post_delete_listener,
    post_insert_listener,
)
from pgpubsub.tests.channels import (
    AuthorTriggerChannel,
    PostReads,
    PostTriggerChannel,
)
from pgpubsub.tests.models import Author, Post

post_reads_per_date_cache = defaultdict(dict)
author_reads_cache = {}


@listener(PostReads)
def update_post_reads_per_date_cache(model_id, model_type, date):
    print(f'Processing update_post_reads_per_date with ' f'args {model_id}, {date}')
    print(f'Cache before: {post_reads_per_date_cache}')
    current_count = post_reads_per_date_cache[date].get(model_id, 0)
    post_reads_per_date_cache[date][model_id] = current_count + 1
    print(f'Cache after: {post_reads_per_date_cache}')


@listener(PostReads)
def notify_post_owner(model_id, model_type, **kwargs):
    post = Post.objects.get(pk=model_id)
    print(f'Notifying owner of {model_type} {post}')
    print('Someone is reading your post!')


@atomic
@post_insert_listener(AuthorTriggerChannel)
def create_first_post_for_author(old, new):
    print(f'Creating first post for {new.name}')
    Post.objects.create(
        author_id=new.pk,
        content='Welcome! This is your first post',
        date=datetime.date.today(),
    )
    time.sleep(5)


@post_delete_listener(PostTriggerChannel)
def email_author(old, new):
    author = Author.objects.get(pk=old.author_id)
    print(f'Emailing {author.name} to inform then post {old.pk} ' f'has been deleted.')
    email(author)


def email(author):
    pass
