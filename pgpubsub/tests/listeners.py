import time
from collections import defaultdict
import datetime

from django.db.transaction import atomic

import pgpubsub
from pgpubsub.tests.channels import (
    AuthorTriggerChannel,
    PostReads,
    PostTriggerChannel,
)
from pgpubsub.tests.models import Author, Post

post_reads_per_date_cache = defaultdict(dict)
author_reads_cache = {}


@pgpubsub.listener(PostReads)
def update_post_reads_per_date_cache(
        model_id: int, model_type: str, date: datetime.date):
    print(f'Processing update_post_reads_per_date with '
          f'args {model_id}, {date}')
    print(f'Cache before: {post_reads_per_date_cache}')
    current_count = post_reads_per_date_cache[date].get(model_id, 0)
    post_reads_per_date_cache[date][model_id] = current_count + 1
    print(f'Cache after: {post_reads_per_date_cache}')


@pgpubsub.listener(PostReads)
def notify_post_owner(model_id: int, model_type: str, **kwargs):
    post = Post.objects.get(pk=model_id)
    print(f'Notifying owner of {model_type} {post}')
    print('Someone is reading your post!')


@atomic
@pgpubsub.post_insert_listener(AuthorTriggerChannel)
def create_first_post_for_author(old: Author, new: Author):
    print(f'Creating first post for {new.name}')
    Post.objects.create(
        author_id=new.pk,
        content='Welcome! This is your first post',
        date=datetime.date.today(),
    )


@pgpubsub.post_delete_listener(PostTriggerChannel)
def email_author(old: Post, new: Post):
    author = Author.objects.get(pk=old.author_id)
    print(f'Emailing {author.name} to inform then post '
          f'{old.pk} has been deleted.')
    email(author)


def email(author: Author):
    pass
