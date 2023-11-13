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


Documentation
-------------

https://django-pgpubsub.readthedocs.io/en/latest/


Primary Authors
---------------
* [Paul Gilmartin](https://github.com/PaulGilmartin)
* [Wesley Kendall](https://github.com/wesleykendall)


Highlights
==========

- **Minimal Operational Infrastructure**: If you're already running a Django application
  on top of a Postgres database, the installation of this library is the sum total
  of the operational work required to implement a framework for a distributed
  message processing framework. No additional frameworks or technologies
  are required.

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

Quick start
===========

Prerequisites
-------------

Before using this library, you must be running Django 2.2 (or later) on top
of a (single) PostgreSQL 11 (or later) database.


Installing
----------

    pip install django-pgpubsub

``django-pgpubsub`` ships with a ``Notification`` model. This table must
be added to the app's database via the usual django ``migrate`` command.
We should also add `pgpubsub` and `pgtrigger` into `INSTALLED_APPS`.
Additionally, if we wish to run the `pgpubsub` tests, we need to add
`pgpubsub.tests` into `INSTALLED_APPS` too.

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
from dataclasses import dataclass

from pgpubsub.channel import TriggerChannel
from pgpubsub.tests.models import Author


@dataclass
class AuthorTriggerChannel(TriggerChannel):
    model = Author
```

**Define a Listener**

A *listener* is the function which processes notifications sent through a channel.
We define our listener in our app's ``listeners.py`` file as follows:

```python
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
```

**Note that since ``AuthorTriggerChannel`` is a trigger-based channel, we need
to perform a ``migrate`` command after first defining the above listener
so as to install the underlying trigger in the database.**

Finally, we must also ensure  that this listeners.py module is imported into the app's config
class. In this example, our app is calls "tests":

```python
# tests/apps.py
from django.apps import AppConfig


class TestsConfig(AppConfig):
    name = 'tests'

    def ready(self):
        import pgpubsub.tests.listeners
```


**Start Listening**

To have our listener function listen for notifications on the ``AuthorTriggerChannel``,
we use the ``listen`` management command:


    ./manage.py listen


Now whenever an ``Author`` is inserted into our database, our listener process creates
a ``Post`` object referencing that ``Author``:

https://user-images.githubusercontent.com/18212082/165683416-b5cbeca1-ea94-4cd4-a5a1-81751e1b0feb.mov

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
