django-pgpubsub
########################################################################

Documentation
=============

Introduction
=============
This PR introduces the first working sketch of the django-pubsub library (still not sure about the name).
It focuses on developing the beginnings of the user facing interface and basic mechanics of the
python implementation of the postgres notify-listen protocol.
We do not yet discuss the trickier topics of dealing with concurrency and listener durability.

Our documentation will be via two concrete examples:

* One in which we use the ``django-pgpubsub`` library to asynchronously maintain a cache
  of how frequently ``Post`` objects are read per day.

* Another in which we use the ``django-pgpubsub`` library define a postgres-trigger based
  notification to ensure that, whenever an `Author` object is created, a `Post` object is
  asynchronously created for that author with the title "Test Post".

Working versions of the examples documented here can be found in the ``pgpubsub.tests`` app of this
library.


Declaring the Channels
======================

Channel objects are the medium through which notifications are sent.
A channel is defined as a dataclass, where the dataclass fields define the accepted
notification payload. A channel must be declared in your app's ``channels.py`` file.

For our first example, the aforementioned post-reads-per-day cache is simply a dictionary of the form

.. code-block:: python

   {date_1: {post_id_x: read_count_of_post_id_x,...}, ..., date_n: {post_id_x : read_count_of_post_id_x, ...}}


Thus to update this cache whenever a ``Post`` is read, we need to
supply the cache with the id of the `Post` and the date on which it
was read. This data required for our cache helps shape our
``PostReads`` channel, through which we'll send notifications
to update the cache:

.. code-block:: python

   import datetime

   from pgpubsub.channels import Channel


   @dataclass
   class PostReads(Channel):
       model_id: int
       date: datetime.date


Note that it is possible to have optional kwargs on channels as well - see
``pgpubsub.tests.channels.py`` for an example.

In our second example we wish to have a channel through which
notifications sent whenever a postgres-trigger is invoked by the creation
of an ``Author`` object. To achieve this, we define our channel like so (
also in our apps ``channels.py`` module):

.. code-block:: python

    from pgpubsub.channels import TriggerChannel

    @dataclass
    class AuthorTriggerChannel(TriggerChannel):
        model = Author


Note that the key difference between this and the previous example is that
this channel inherits from ``TriggerChannel``, which defines the payload for
all trigger-based notifications:

.. code-block:: python

    @dataclass
    class TriggerChannel(_Channel):
        model = NotImplementedError
        old: django.db.models.Model
        new: django.db.models.Model


Here the ``old`` and ``new`` parameters are the (unsaved) versions of what the
trigger invoking instance looked like before and after the trigger was invoked.
In this example, ``old`` would refer to the state of our ``Author`` object
pre-creation (and would hence be ``None``) and ``new`` would refer to a copy of
the newly created ``Author`` instance. This payload is inspired by the ``OLD``
and ``NEW`` values available in the postgres ``CREATE TRIGGER`` statement
(https://www.postgresql.org/docs/9.1/sql-createtrigger.html).


Declaring the Listeners
=======================

In the ``django-pgpubsub`` library, a *listener* is the function
which processes the notifications sent through some particular channel.
A listener must be defined in our app's ``listeners.py`` file and must
be declared using one of the decorators in ``pgpubsub.listen.py``.
These decorators are also responsible for pointing a listener function
to listen to a particular channel.

Continuing with the example whereby we maintain a cache of post reads,
we implement a listener function like so:

.. code-block:: python

    from pgpubsub.listen import listener

    # Cache for illustrative purposes only
    post_reads_per_date_cache = defaultdict(dict)
    author_reads_cache = dict()

    @listener(PostReads)
    def update_post_reads_per_date_cache(model_id, date):
        print(f'Processing update_post_reads_per_date with '
              f'args {model_id}, {date}')
        print(f'Cache before: {post_reads_per_date_cache}')
        current_count = post_reads_per_date_cache[date].get(model_id, 0)
        post_reads_per_date_cache[date][model_id] = current_count + 1
        print(f'Cache after: {post_reads_per_date_cache}')


As we may expect, the channel we associate to a listener also
defines the signature of the listener function.
Note that it is possible to have multiple
listeners to a single channel and the signatures of those listeners
can vary by arguments declared as optional on their common channel -
see ``pgpubsub.tests.listeners.py`` for an example.

Next we implement the listener which is used to asynchronously
create a ``Post`` object whenever a new ``Author`` object is created.
For this listener, we can use the pre-defined ``post_insert_listener``
decorator:

.. code-block:: python

        from pgpubsub.listen import post_insert_listener

        @post_insert_listener(AuthorTriggerChannel)
        def create_first_post_for_author(old, new):
            print(f'Creating first post for {new.name}')
            Post.objects.create(
                author_id=new.pk,
                content='Welcome! This is your first post',
                date=datetime.date.today(),
            )

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
into the app's config class (similar to signals):

.. code-block:: python

    class TestsConfig(AppConfig):
        name = 'tests'

        def ready(self):
            import tests.listeners


Start Listening to Channels
===========================

To actually have all of our project's listener functions "listening" for
incoming notifications on their associated channel, we can make use
of the ``listen`` management command:

.. code-block:: python

    ./manage.py listen

The ``listen`` command also accepts an optional ``--channels``
argument, whose value should be a space separated list of the
full module paths of the channels we wish to send notifications
through. This for example allows us to have a process dedicated
to queueing notifications for our ``PostReads`` channel:

.. code-block:: python

    ./manage.py listen --channels 'pgpubsub.tests.channels.PostReads'

and another channel in dedicated to queueing notifications for our
``AuthorTrigger`` channel:

.. code-block:: python

    ./manage.py listen --channels 'pgpubsub.tests.channels.AuthorTriggerChannel'




Sending Notifications
=====================

For non-trigger based channels, like ``PostReads``, we send our notifications through the channel
and to the ``update_post_reads_per_date_cache`` listener via an explicit call to the
``pgpubsub.notify.notify`` function. In our example, we create a ``fetch`` classmethod
on the ``Post`` model which is used to retrieve a ``Post`` instance from the database
and also send a notification to asynchronously invoke the ``update_post_reads_per_date_cache``
with the notification payload:

.. code-block:: python

    from pgpubsub.notify import notify
    class Post(models.Model):
        ...
    @classmethod
    def fetch(cls, post_id):
        post = cls.objects.get(pk=post_id)
        notify(
            'pgpubsub.tests.channels.PostReads',
            model_id=post_id,
            date=datetime.date.today(),
        )
        return post


Under the hood, this python function is making use of the postgres
``NOTIFY`` command to send the payload as a JSON object.

For trigger based channels, notifications are sent purely at the database
layer whenever the corresponding trigger is invoked. In our example, this
means that whenever an ``Author`` object is created, a ``PERFORM NOTIFY``
SQL command is invoked under the hood. This sends a json payload consisting
of the ``OLD`` and ``NEW`` values of the ``Author`` instance before and after the
creation of the author via the ``AuthorTriggerChannel`` to the
``create_first_post_for_author``, which then creates a ``Post`` object for the
new author in the listening process. Note that since postgres ensures that
notifications sent via ``NOTIFY`` are only sent *after* the commit which
created them is committed, we can be sure that in our example our newly
created ``Author``
will be safely in the database before the listener process attempts to
associate a ``Post`` to it.

`View the django-pgpubsub docs here
<https://django-pgpubsub.readthedocs.io/>`_.


Ensuring Notifications Do Not Get Lost
======================================

Scenarios in which a notification could end up not being
processed completely:

1. The notification is sent to a channel which is not listening.
   This could happen for a few reasons:
    a) The listener was never started.
    b) The listener was down temporarily during a deployment
      window.

2. The notification is picked up by a listener, but the listener
   function fails whilst processing the notification.

3. (Unsure if actually possible) Could it be that the action
    which created the notification is successful, but the
    NOTIFY command fails to actually send the notification?
    Hard to see how - if the NOTIFY failed, then surely
    the transaction would be rolled back/process would be
    terminated (and hence the user action would fail)?
    I suppose if someone had weird exception handling around
    the notify command this could happen. It is not like
    connecting to rabbit MQ though where the connection
    can fail and the user action still goes through -
    the NOTIFY is only sent after the transaction ends
    and uses the same db connection.



Solving the problem of when no one is listening
===============================================

Let's consider a client with the following set-up:

1. Two web servers, P (primary) and S (secondary).
2. A single postgres db.
3. A process ``listen`` process running on P listening to
   two channels, ``PostReads`` and ``AuthorTriggerChannel``.


Idea 1 : Have a dedicated "backup" channel which is purely
dedicated to collecting notifications from all registered
channels and storing them in the db. These can later be
replayed.
Whenever a notification is sent to a channel, the same notification
is sent to the backup channel.
A notification is also sent to the backup channel whenever the listener
process fails to fully process a notification. This notification would
be marked as "failed" or something. Could also send whenever it actually
does process the notification, marking the notification as complete.



Idea 2: Two processes can be listening to the same channel without
the fear of the same notification being processed more than once.
If this was possible, the idea of a backup channel may be obsolete,
as then we could just use this listening processes to also store
notifications.

Couple of ways to go here:
- Skip lock: https://spin.atomicobject.com/2021/02/04/redis-postgresql/
  This would require saving the notification in the user's thread, hence
  hurting performance a small amount. It seems like it would also
  require more. It would also involve polling the db for unused jobs,
  which kind of negates the cheap polling we get.
- Advisory locks seem a bit cheaper? Not sure if as good though?


Scenario 1: We wish to stop and restart the listen process for a code update
without missing any notifications
----------------------------------------------------------------------------

- Using Idea 1: Have backup channel running on P and S. Bring down
  P and S one by one.

- Using Idea 2: Have same ``listen`` process running on P and S. Deploy
  code to P and S one by one: bring listen process down on S first,
  deploy code to S, bring back up on S. Now do the same on P.



Scenario 2: A bug in the code means the listen process fails whenever a
notification is received via the ``AuthorTriggerChannel``. We want to
replay the failed notifications later.
-----------------------------------------------------------------------









Installation
============

Install django-pgpubsub with::

    pip3 install django-pgpubsub

After this, add ``pgpubsub`` to the ``INSTALLED_APPS``
setting of your Django project.

Contributing Guide
==================

For information on setting up django-pgpubsub for development and
contributing changes, view `CONTRIBUTING.rst <CONTRIBUTING.rst>`_.
