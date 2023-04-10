Notifications
=============


The ``notify`` Function
-----------------------

With our listeners listening on our channels, all that remains is to define where
our notifications are sent from.

For our first example, we need to send a notification through the ``PostReads`` channel
whenever a ``Post`` object is read. To achieve this, we can make use of the
``pgpubsub.notify.notify`` function.

In our example, we create a ``fetch`` class method
on the ``Post`` model which is used to retrieve a ``Post`` instance from the database
and also send a notification via the ``PostReads`` channel to asynchronously invoke the
``update_post_reads_per_date_cache`` listener. This ``fetch`` method could then
of course be utilised in whatever API call is used when a user reads a post:


.. code-block:: python

    # tests/models.py
    import datetime

    from django.db import models

    import pgpubsub

    class Post(models.Model):
        ...
        @classmethod
        def fetch(cls, post_id):
            post = cls.objects.get(pk=post_id)
            pgpubsub.notify(
                'pgpubsub.tests.channels.PostReads',
                model_id=post_id,
                date=datetime.date.today(),
            )
            return post



A few notes on the above implementation:

* Under the hood, this python function is making use of the postgres
  ``NOTIFY`` command to send the payload as a JSON object.
* The first argument to the ``notify`` function can either be the full module
  path of a channel or the channel class itself. The following keyword
  arguments should match the dataclass fields of the channel we're notifying
  (up to optional kwargs).
* Using ``pgpubsub.notify.notify`` is the appropriate choice for any non-postgres trigger
  based notification.


Trigger Notifications
---------------------

For trigger based channels, notifications are sent at the database
layer whenever the trigger is invoked. To understand this in a bit
more detail, let's consider our example above:

.. code-block:: python

    import datetime

    import pgpubsub
    from pgpubsub.tests.channels import AuthorTriggerChannel
    from pgpubsub.tests.models import Author, Post

    @pgpubsub.post_insert_listener(AuthorTriggerChannel)
    def create_first_post_for_author(old: Author, new: Author):
        print(f'Creating first post for {new.name}')
        Post.objects.create(
            author_id=new.pk,
            content='Welcome! This is your first post',
            date=datetime.date.today(),
        )


As explained in the previous section, if we write this function and perform a migration, the ``post_insert_listener`` decorator ensures that a trigger function
is written to the database. Then, after any ``Author`` row is inserted to the
database, the ``post_insert_listener`` also ensures that that database-level trigger
function is invoked, firing a notification with a JSON payload consisting
of the ``OLD`` and ``NEW`` values of the ``Author`` instance before and after the
its creation. Associating the channel like so

.. code-block:: python

    post_insert_listener(AuthorTriggerChannel)


ensures that the notification is sent via the ``AuthorTriggerChannel`` and hence ends up being
processed by the ``create_first_post_for_author`` listener. To examine the internals of the trigger functions used to send notifications at the database level,
see ``pgpubsub.triggers.py``.

Note that postgres ensures that notifications sent via ``NOTIFY`` are only sent *after* the commit which
created them is committed, we can be sure that in our example our newly
created ``Author`` will be safely in the database before the listener process attempts to
associate a ``Post`` to it.
