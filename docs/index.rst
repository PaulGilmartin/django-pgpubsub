django-pgpubsub
===============

``django-pgpubsub`` provides a framework for building an asynchronous
and distributed message processing network on top of a Django application
using a PostgreSQL database. This is achieved by leveraging Postgres'
`LISTEN/NOTIFY <https://www.postgresql.org/docs/current/sql-notify.html>`__
protocol to build a message queue at the database layer.
The simple user-friendly interface,
minimal infrastructural requirements and the ability to leverage Postgres'
transactional behaviour to achieve exactly-once messaging, makes
``django-pgpubsub`` a solid choice as a lightweight alternative to AMPQ
messaging services, such as
`Celery <https://docs.celeryq.dev/en/stable/search.html?q=ampq>`__.


Primary Authors
---------------
* `Paul Gilmartin <https://github.com/PaulGilmartin>`__
* `Wesley Kendall <https://github.com/wesleykendall>`__



Highlights
----------

- **Minimal Operational Infrastructure**: If you're already running a Django application
  on top of a Postgres database, the installation of this library is the sum total
  of the operational work required to implement a framework for a distributed
  message processing framework. No additional frameworks or technologies
  are required.

- **Integration with Postgres Triggers (via django-pgtrigger)**:
  To quote the `official <https://www.postgresql.org/docs/current/sql-notify.html>`__
  Postgres docs:

  *"When NOTIFY is used to signal the occurrence of changes to a particular table,
  a useful programming technique is to put the NOTIFY in a statement trigger that is triggered
  by table updates.
  In this way, notification happens automatically when the table is changed,
  and the application programmer cannot accidentally forget to do it."*

  By making use of the ``django-pgtrigger``
  `library <https://pypi.org/project/django-pgtrigger/>`__, ``django-pgpubsub``
  offers a Django application layer abstraction of the trigger-notify Postgres
  pattern. This allows developers to easily write python-callbacks which will
  be invoked (asynchronously) whenever a custom ``django-pgtrigger`` is invoked.
  Utilising a Postgres-trigger as the ground-zero for emitting a
  message based on a database table event is far more robust than relying
  on something at the application layer (for example, a ``post_save`` signal,
  which could easily be missed if the ``bulk_create`` method was used).

- **Lightweight Polling**: we make use of the Postgres ``LISTEN/NOTIFY``
  protocol to have achieve notification polling which uses
  `no CPU and no database transactions unless there is a message to read. <https://www.psycopg.org/docs/advanced.html#asynchronous-notifications>`__

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
-----------

- A database-based queue will not be capable of the same volume of throughput as a dedicated
  AMPQ queue.

- If a message is sent using Postgres' ``NOTIFY`` and no process is listening at that time,
  the message is lost forever. As explained in the **Durability and Recovery** section above,
  pgpubsub can easily be configured so that we can replay "lost" messages, but this comes at the
  performance penalty of inserting a row into a table before sending each notification. This is the same
  penalty we must pay if we wish to have concurrent processes listening to the same channel without
  duplicate notifcation processing, as explained in the **Exactly-once notification processing** section above.


Alternatives
------------

- `Celery <https://docs.celeryq.dev/en/stable/search.html?q=ampq>`__: The canonical distributed message processing library for django based applications. This can handle large volumes of throughput and is well tested in production.
  It is however operationally quite heavy to maintain and set-up.

- `Procrastinate <https://procrastinate.readthedocs.io/>`__: This was a library we discovered whilst developing ``pgpubsub`` which also implements a distributed message processing library using the Postgres ``LISTEN/NOTIFY`` protocol. Whilst ``Procrastinate`` is well tested and offers several features which are not currently offered by ``pgpubsub``, we believe that the interface of ``pgpubsub`` coupled with the integration with django and Postgres triggers make our library a good alternative for certain use cases.



Quickstart
==========


Prerequisites
-------------

Before using this library, you must be running Django 2.2 (or later) on top
of a (single) PostgreSQL 11 (or later) database.


Installing
----------

.. code-block::

    pip install django-pgpubsub

``django-pgpubsub`` ships with a ``Notification`` model. This table must
be added to the app's database via the usual django ``migrate`` command.
We should also add ``pgpubsub`` and ``pgtrigger`` into ``INSTALLED_APPS``.
Additionally, if we wish to run the ``pgpubsub`` tests, we need to add
``pgpubsub.tests`` into ``INSTALLED_APPS`` too.


Developing and Contributing
---------------------------

If you would like to contribute to this library, you can spin up a development environment
by running ``docker compose up``.
This will create two containers, one with a postgres database and one with a
django application running the ``manage.py listen`` command.
You can then run the tests by running ``docker compose exec app pytest``.
Alternatively, if you want to run tests on Pycharm, you should override the ``entrypoint``
in the ``app`` service of ``docker-compose.yml`` to be ``''``.


Minimal Example
===============

Let's get a brief overview of how to use ``pgpubsub`` to asynchronously
create a ``Post`` row whenever an ``Author`` row is inserted into the
database. For this example, our notifying event will come from a
postgres trigger, but this is not a requirement for all notifying events.
A more detailed version of this example, and an example which
does not use a postgres trigger, can be found in the
:ref:`example_app` section.


Define a Channel
----------------

Channels are the medium through which we send notifications.
We define our channel in our app's ``channels.py`` file as a dataclass
as follows:


.. code-block:: python

    from dataclasses import dataclass

    from pgpubsub.channel import TriggerChannel
    from pgpubsub.tests.models import Author


    @dataclass
    class AuthorTriggerChannel(TriggerChannel):
        model = Author



Define a Listener
-----------------

A *listener* is the function which processes notifications sent through a channel.
We define our listener in our app's ``listeners.py`` file as follows:

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


.. note::

    Since ``AuthorTriggerChannel`` is a trigger-based channel, we need
    to perform a ``migrate`` command after first defining the above listener
    so as to install the underlying trigger in the database.

Finally, we must also ensure  that this listeners.py module is imported into the app's config
class. In this example, our app is calls "tests":

.. code-block:: python

    # tests/apps.py
    from django.apps import AppConfig


    class TestsConfig(AppConfig):
        name = 'tests'

        def ready(self):
            import pgpubsub.tests.listeners



Start Listening
---------------
To have our listener function listen for notifications on the ``AuthorTriggerChannel``,
we use the ``listen`` management command:

.. code-block::

    ./manage.py listen

Now whenever an ``Author`` is inserted into our database, our listener process creates
a ``Post`` object referencing that ``Author``.
