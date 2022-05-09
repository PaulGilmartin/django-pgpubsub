django-pgpubsub
===============

``django-pgpubsub`` provides a framework for building an asynchronous
and distributed message processing network on top of a Django application
using a PostgreSQL database. This is achieved by leveraging Postgres'
[LISTEN/NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html)
protocol to build a message queue at the database layer.
The simple user-friendly interface,
minimal infrastructural requirements and the ability to leverage Postgres'
transactional behaviour to achieve exactly-once messaging, makes
``django-pgpubsub`` a solid choice as a lightweight alternative to AMPQ
messaging services, such as
[Celery](https://docs.celeryq.dev/en/stable/search.html?q=ampq)


Primary Authors
---------------
* [Paul Gilmartin](https://github.com/PaulGilmartin)
* [Wesley Kendall](https://github.com/wesleykendall)


Highlights
==========

- **Minimal Operational Infrastructure**: If you're already running a Django application
  on top of a Postgres database, the installation of this library is the sum total
  of the operational work required to implement a framework for a distributed
  message processing framework. No additional servers or server configuration
  is required.

- **Integration with Postgres Triggers (via django-pgtrigger)**:
  To quote the [official](https://www.postgresql.org/docs/current/sql-notify.html)
  Postgres docs:

  *"When NOTIFY is used to signal the occurrence of changes to a particular table,
  a useful programming technique is to put the NOTIFY in a statement trigger that is triggered
  by table updates.
  In this way, notification happens automatically when the table is changed,
  and the application programmer cannot accidentally forget to do it."*

  By making use of the ``django-pgtrigger``
  [library](https://pypi.org/project/django-pgtrigger/), ``django-pgpubsub``
  offers a Django application layer abstraction of the trigger-notify Postgres
  pattern. This allows developers to easily write python-callbacks which will
  be invoked (asynchronously) whenever a custom ``django-pgtrigger`` is invoked.
  Utilising a Postgres-trigger as the ground-zero for emitting a
  message based on a database table event is far more robust than relying
  on something at the application layer (for example, a ``post_save`` signal,
  which could easily be missed if the ``bulk_create`` method was used).

- **Lightweight Polling**: we make use of the Postgres ``LISTEN/NOTIFY``
  protocol to have achieve notification polling which uses
  [no CPU and no database transactions unless there is a message to read.](https://www.psycopg.org/docs/advanced.html#asynchronous-notifications)

- **Exactly-once notification processing**: ``django-pgpubsub`` can be configured so
  that notifications are processed exactly once. This is achieved by storing
  a copy of each new notification in the database and mandating that a notification
  processor must obtain a postgres lock on that message before processing it.
  This allows us to have concurrent processes listening to the same message channel
  with the guarantee that no two channels will act on the same notification. Moreover,
  the use of Django's ``.select_for_update(skip_locked=True)`` method allows
  concurrent listeners to continue processing incoming messages without waiting
  for lock-release events from other listening processes.

- **Durability and Recovery**: ``django-pgpubsub`` can be configured so that
  notifications are stored in the database before they're sent to be processed.
  This allows us to replay any notification which may have been missed by listening
  processes, for example in the event a notification was sent whilst the listening
  processes were down.

- **Atomicity**: The Postgres ``NOTIFY`` protocol respects the atomicity
  of the transaction in which it is invoked. The result of this is that
  any notifications sent using ``django-pgpubsub`` will be sent if and only if
  the transaction in which it sent is successfully committed to the database.


Limitations
===========

- A database-based queue will not be capable of the same volume of throughput as a dedicated
  AMPQ queue.

- If a message is sent using Postgres' ``NOTIFY`` and no process is listening at that time,
  the message is lost forever. As explained in the **Durability and Recovery** section above,
  pgpubsub can easily be configured so that we can replay "lost" messages, but this comes at the
  performance penalty of inserting a row into a table before sending each notification. This is the same
  penalty we must pay if we wish to have concurrent processes listening to the same channel without
  duplicate notiifcation processing, as explained in the **Exactly-once notification processing** section above.


Alternatives
============

- [Celery](https://docs.celeryq.dev/en/stable/search.html?q=ampq): The canonical distributed message processing library for django based applications. This can handle large volumes of throughput and is well tested in production.
  It is however operationally quite heavy to maintain and set-up.

- [Procrastinate](https://procrastinate.readthedocs.io/): This was a library we discovered whilst developing ``pgpubsub`` which also implements a distributed message processing library using the Postgres ``LISTEN/NOTIFY`` protocol. Whilst ``Procrastinate`` is well tested and offers several features which are not currently offered by ``pgpubsub``, we believe that the interface of ``pgpubsub`` coupled with the integration with django and Postgres triggers make our library a good alternative for certain use cases.

Quick start
===========

Prerequisites
-------------

Before using this library, you must be running Django 2.2 (or later) on top
of a (single) PostgreSQL 9.4 (or later) database.


Installing
----------

    pip install django-pgpubsub

``django-pgpubsub`` ships with a ``Notification`` model. This table must
be added to the app's database via the usual django ``migrate`` command.

Minimal Example
---------------

Let's get a brief overview of how to use ``pgpubsub`` to asynchronously
create a ``Post`` row whenever an ``Author`` row is inserted into the
database. For this example, our notifying event will come from a
postgres trigger, but this is not a requirement for all notifying events.
A more detailed version of this example, and an example which
does not use a postgres trigger, can be found in the
**Documentation (by Example)** section below.

**Define a Channel**

Channels are the medium through which we send notifications.
We define our channel in our app's ``channels.py`` file as a dataclass
as follows:

```python
from pgpubsub.channels import TriggerChannel

@dataclass
class AuthorTriggerChannel(TriggerChannel):
    model = Author
```

**Define a Listener**

A *listener* is the function which processes notifications sent through a channel.
We define our listener in our app's ``listeners.py`` file as follows:

```python
import pgpubsub

from .channels import AuthorTriggerChannel

@pgpubsub.post_insert_listener(AuthorTriggerChannel)
def create_first_post_for_author(old: Author, new: Author):
    print(f'Creating first post for {new.name}')
    Post.objects.create(
        author_id=new.pk,
        content='Welcome! This is your first post',
        date=datetime.date.today(),
    )
```

Since ``AuthorTriggerChannel`` is a trigger-based channel, we need
to perform a ``migrate`` command after first defining the above listener
so as to install the underlying trigger in the database.

**Start Listening**

To have our listener function listen for notifications on the ``AuthorTriggerChannel``,
we use the ``listen`` management command:


    ./manage.py listen


Now whenever an ``Author`` is inserted into our database, our listener process creates
a ``Post`` object referencing that ``Author``:

https://user-images.githubusercontent.com/18212082/165683416-b5cbeca1-ea94-4cd4-a5a1-81751e1b0feb.mov


Documentation (by Example)
==========================

In this section we give a brief overview of how to use
``pgpubsub`` to add asynchronous message processing functionality
to an existing django application.


Our Test Application
--------------------
Suppose we have the following basic django models (
a fully executable version of this example can be
found in ``pgpubsub.tests``):

```python
# models.py
class Author(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    name = models.TextField()


class Post(models.Model):
    content = models.TextField()
    date = models.DateTimeField()
    author = models.ForeignKey(
        Author, null=True, on_delete=models.SET_NULL, related_name='entries'
    )
```

Given these models, we'll describe the mechanics of using the ``pgpubsub`` library
to achieve the following aims (which are for illustrative purposes only):

* To asynchronously maintain a cache of how frequently ``Post`` objects are
  read per day.

* To define a postgres-trigger to ensure that, whenever an ``Author`` object is created, a ``Post`` object is
  asynchronously created for that author with the title "Test Post".


Channels
---------

Channels are the medium through which messages are sent.
A channel is defined as a dataclass, where the dataclass fields define the accepted
notification payload. A channel must be declared in your app's ``channels.py`` file.


For our first example, the data required to update the aforementioned post-reads-per-day cache
is a date and a ``Post`` id. This payload defines the fields of our first channel dataclass,
through which notifications will be sent to update the post-reads-per-day cache:


```python
# channels.py
import datetime

from pgpubsub.channels import Channel


@dataclass
class PostReads(Channel):
    model_id: int
    date: datetime.date
```
Note the accepted dataclass field types for classes inheriting from
``Channel`` are iterables (lists, tuples, dicts, sets) of:
* python primitive types
* (naive) datetime.date objects


In our second example we wish to have a channel through which
notifications sent whenever a postgres-trigger is invoked by the creation
of an ``Author`` object. To achieve this, we define our channel like so (
also in our apps ``channels.py`` module):

```python
from pgpubsub.channels import TriggerChannel

@dataclass
class AuthorTriggerChannel(TriggerChannel):
    model = Author
```

Note that the key difference between this and the previous example is that
this channel inherits from ``TriggerChannel``, which defines the payload for
all trigger-based notifications:

```python
@dataclass
class TriggerChannel(_Channel):
    model = NotImplementedError
    old: django.db.models.Model
    new: django.db.models.Model
```

Here the ``old`` and ``new`` parameters are the (unsaved) versions of what the
trigger invoking instance looked like before and after the trigger was invoked.
In this example, ``old`` would refer to the state of our ``Author`` object
pre-creation (and would hence be ``None``) and ``new`` would refer to a copy of
the newly created ``Author`` instance. This payload is inspired by the ``OLD``
and ``NEW`` values available in the postgres ``CREATE TRIGGER`` statement
(https://www.postgresql.org/docs/9.1/sql-createtrigger.html). The only custom
logic we need to define on a trigger channel is the ``model`` class-level
attribute.


Listeners
--------

In the ``pgpubsub`` library, a *listener* is the function
which processes notifications sent through some particular channel.

A listener must be defined in our app's ``listeners.py`` file and must
be declared using one of the decorators in ``pgpubsub.listen.py``.
These decorators are also responsible for pointing a listener function
to listen to a particular channel. When a function is associated to a channel
in this way, we say that function "listening" to that channel.

Continuing with the example whereby we maintain a cache of post reads,
we implement a listener function like so:

```python
# tests/listeners.py
import datetime

import pgpubsub

# Simple cache for illustrative purposes only
post_reads_per_date_cache = defaultdict(dict)
author_reads_cache = dict()

@pgpubsub.listener(PostReads)
def update_post_reads_per_date_cache(model_id: int, date: datetime.date):
    print(f'Processing update_post_reads_per_date with '
          f'args {model_id}, {date}')
    print(f'Cache before: {post_reads_per_date_cache}')
    current_count = post_reads_per_date_cache[date].get(model_id, 0)
    post_reads_per_date_cache[date][model_id] = current_count + 1
    print(f'Cache after: {post_reads_per_date_cache}')
```

A few notes on the above:

* As we may expect, the channel we associate to a listener also
  defines the signature of the listener function.
* The notification payload is deserialized
  in such a way that the input arguments to the listener function
  have the same type as was declared on the ``PostReads`` channel.
* It is possible to have multiple
  listeners to a single channel and the signatures of those listeners
  can vary by arguments declared as optional on their common channel -
  see ``pgpubsub.tests.listeners.py`` for an example.

Next we implement the listener which is used to asynchronously
create a ``Post`` object whenever a new ``Author`` object is created.
For this listener, we can use the pre-defined ``post_insert_listener``
decorator:

```python
# tests/listeners.py
import pgpubsub

from .channels import AuthorTriggerChannel


@pgpubsub.post_insert_listener(AuthorTriggerChannel)
def create_first_post_for_author(old: Author, new: Author):
    print(f'Creating first post for {new.name}')
    Post.objects.create(
        author_id=new.pk,
        content='Welcome! This is your first post',
        date=datetime.date.today(),
    )
```

Any listener associated to a trigger-based channel (one inheriting from
``TriggerChannel``) necessarily has a signature consisting of the ``old``
and ``new`` payload described in the previous section. Note that
declaring a trigger-based listener in the manner above *actually
writes a postgres-trigger to our database*. This is achieved by
leveraging the ``django-pgtrigger`` library to write a pg-trigger
which will send a payload using the postgres ``NOTIFY`` command
whenever an ``Author`` object is inserted into the database. Note that
as with all triggers defined using ``django-pgtrigger``, this trigger
is first written to the database after a migration.

Finally, we must also ensure that this ``listeners.py`` module is imported
into the app's config class (similar to how one would use django signals):

```python
# tests/apps.py

class TestsConfig(AppConfig):
    name = 'tests'

    def ready(self):
        import tests.listeners
```

Listening
---------

To have our listener functions "listen" for
incoming notifications on their associated channel, we can make use
of the ``listen`` management command provided by the ``pgpubsub`` library:

    ./manage.py listen

When a process started in this manner encounters an exception, ``pgpubsub``
will automatically spins up a secondary process to continue listening before the
exception ends the initial process. This means that we do not have to worry about
restarting our listening processes any time a listener incurs a python level exception.

The ``listen`` command accepts two optional arguments:

* ``--channels``: a space separated list of the
  full module paths of the channels we wish to listen to.
  When no value is supplied, we default to listening to all registered channels
  in our project. For example,
  we can use the following command to listen to notifications coming through
  the ``PostReads`` channel only:


    ./manage.py listen --channels 'pgpubsub.tests.channels.PostReads'


* ``--processes``: an integer which denotes the number of concurrent processes
  we wish to dedicate to listening to the specified channels. When no value is
  supplied, we default to using a single process. Note that if multiple processes
  are listening to the same channel then by default both processes will act on
  each notification. To prevent this and have each notification be acted upon
  by exactly one listening process, we need to add ``lock_notifications = True``
  to our channel. See the "Lockable Notifications and Exactly-Once Messaging"
  section below for more.


Notifications
-------------

With our listener's listening on our channels, all that remains is to define where
our notifications are sent from.

For our first example, we need to send a notification through the ``PostReads`` channel
whenever a ``Post`` object is read. To achieve this, we can make use of the
``pgpubsub.notify.notify`` function. In our example, we create a ``fetch`` classmethod
on the ``Post`` model which is used to retrieve a ``Post`` instance from the database
and also send a notification via the ``PostReads`` channel to asynchronously invoke the
``update_post_reads_per_date_cache`` listener. This `fetch` method could then
of course be utilised in whatever API call is used when a user reads a post:

```python
# tests/models.py
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
```


A few notes on the above implementation:

* Under the hood, this python function is making use of the postgres
  ``NOTIFY`` command to send the payload as a JSON object.
* The first argument to the `notify` function can either be the full module
  path of a channel or the channel class itself. The following keyword
  arguments should match the dataclass fields of the channel we're notifying
  (up to optional kwargs).
* Using ``pgpubsub.notify.notify`` is the appropriate choice for any non-postgres trigger
  based notification.


For trigger based channels, notifications are sent purely at the database
layer whenever the corresponding trigger is invoked. To understand this in a bit
more detail, let's consider our example above:

```python
@pgpubsub.post_insert_listener(AuthorTriggerChannel)
def create_first_post_for_author(old: Author, new: Author):
    print(f'Creating first post for {new.name}')
    Post.objects.create(
        author_id=new.pk,
        content='Welcome! This is your first post',
        date=datetime.date.today(),
    )
```

As explained above, if we write this function and perform a migration
, the ``post_insert_listener`` decorator ensures that a trigger function
is written to the database. Then, after any ``Author`` row is inserted to the
database, the ``post_insert_listener`` also ensures that that database-level trigger
function is invoked, firing a notification with a JSON payload consisting
of the ``OLD`` and ``NEW`` values of the ``Author`` instance before and after the
its creation. Associating the channel like so

```python
post_insert_listener(AuthorTriggerChannel)
```


ensures that the notification is sent via the ``AuthorTriggerChannel`` and hence ends up being
processed by the ``create_first_post_for_author`` listener. To examine the internals of the trigger functions used to send notifications at the database level,
see ``pgpubsub.triggers.py``.

Note that postgres ensures that notifications sent via ``NOTIFY`` are only sent *after* the commit which
created them is committed, we can be sure that in our example our newly
created ``Author`` will be safely in the database before the listener process attempts to
associate a ``Post`` to it.


Lockable Notifications and Exactly-Once Messaging
-------------------------------------------------

In the default implementation of the Postgres ``LISTEN/NOTIFY`` protocol,
multiple processes listening to the same channel will result in each process acting upon
each notification sent through that channel. This behaviour is often undesirable, so
``pgpubsub`` offers users the option to define channels which allow one, and only one,
listening process to act upon each notification. We can achieve this simply by defining
``lock_notifications=True`` on our channel object. This is the desired notification
processing behaviour for our ``AuthorTriggerChannel``, where we want to create exactly one
``Post`` whenever an ``Author`` row is inserted:

```python
from pgpubsub.channels import TriggerChannel

@dataclass
class AuthorTriggerChannel(TriggerChannel):
    model = Author
    lock_notifications = True
```

Enabling ``lock_notifications`` on a channel has the following effect:

1. Whenever a notification is sent through that channel
   (either via the ``pgpubsub.notify`` function or the ``pgpubsub.triggers.Notify`` trigger),
   a ``pgpubsub.models.Notification`` object is inserted into the database. This stored notification
   contains the same JSON payload as the transient Postgres notification. Note that
   since Postgres notify events are atomic with respect to their transaction, the notification
   is sent if and only if a ``Notification`` is stored.
2. When a process listening to that channel detects an incoming Postgres notification,
   it fetches and *obtains a lock upon* any stored ``Notification`` object with the same
   payload. This is achieved as follows:

    ```python

        notification = (
                Notification.objects.select_for_update(
                        skip_locked=True).filter(
                            channel=self.notification.channel,
                            payload=self.notification.payload,
                    ).first()
                )
    ```

    The fact that ``select_for_update`` in the above applies a lock on ``notification``
    ensures that no other process listening to the same channel can retrieve this notification
    object. Moreover, the use of ``skip_locked=True`` means that any process which
    cannot obtain the lock does not wait for the lock to release. This allows other processes
    to freely skip this notification and poll for others, whilst the one which
    did obtain the lock continues carries on to pass its notification into the
    listener callback. If the callback then successfully completes, the stored
    ``Notification`` is removed from the database.


Recovery
------------

In the default implementation of the Postgres ``LISTEN/NOTIFY`` protocol, if a notification
is sent via a channel and no process is listening on that channel at that time, the
notification is lost forever. As described in the previous section,
enabling ``lock_notifications`` on our channel means we store a ``Notification`` object
in the database. Thus, if we happen to "lose" a notification on such a channel in the
aforementioned way (e.g. if all of our listener processes were down when a notification was sent), we still have a stored copy
of the payload in our database.

``pgpubsub`` provides a function ``pgpubsub.process_stored_notifications`` which fetches
all stored ``Notifications`` from the database and sends them to their respective channels
to be processed. This allows to recover from scenarios like the one in the paragraph described
above.


Live Demos
==========

`bulk_create` over several processes
------------------------------------

In the below example we show how `pgpubsub` handles a bulk creation
of ``Author`` objects when several processes are listening to the
``AuthorTriggerChannel`` channel. For the sake of the below demonstration,
we added a `time.sleep(3)` statement into the `create_first_post_for_author`
listener function. Note how only one processes is able to process any given
notification:

https://user-images.githubusercontent.com/18212082/165823588-df91e84a-47f2-4220-8999-8556665e3de3.mov
