Channels
========

Channels are the medium through which messages are sent.
A channel is defined as a dataclass, where the dataclass fields define the accepted
notification payload. A channel must subclass one of the ``pgpubsub.channel.Channel`` or
``pgpubsub.channel.TriggerChannel`` classes, where the latter should be used when a
postgres-trigger is used as the notifying event and the former when it is not.
Channels must be declared in your app's ``channels.py`` file.


The ``Channel`` class
---------------------

For our first example, the data required to update the aforementioned post-reads-per-day cache
is a date and a ``Post`` id. This payload defines the fields of our first channel dataclass,
through which notifications will be sent to update the post-reads-per-day cache. Since we
do not use a trigger here, our channel should inherit from ``pgpubsub.channel.Channel``:


.. code-block:: python

    # channels.py
    from dataclasses import dataclass
    import datetime

    from pgpubsub.channel import Channel


    @dataclass
    class PostReads(Channel):
        model_id: int
        date: datetime.date


Note the accepted dataclass field types for classes inheriting from
``Channel`` are iterables (lists, tuples, dicts, sets) of:

* python primitive types
* (naive) ``datetime.date`` objects


The ``TriggerChannel`` class
----------------------------

In our second example we wish to have a channel through which
notifications sent whenever a postgres-trigger is invoked by the creation
of an ``Author`` object. To achieve this, we define our channel like so (
also in our apps ``channels.py`` module):

.. code-block:: python

    from dataclasses import dataclass

    from pgpubsub.channel import TriggerChannel
    from pgpubsub.tests.models import Author


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
These objects are built by passing in the trigger notification payload through
Django's model `deserializers <https://docs.djangoproject.com/en/4.1/topics/serialization/>`__.

In this example, ``old`` would refer to the state of our ``Author`` object
pre-creation (and would hence be ``None``) and ``new`` would refer to a copy of
the newly created ``Author`` instance. This payload is inspired by the ``OLD``
and ``NEW`` values available in the postgres ``CREATE TRIGGER`` statement
(https://www.postgresql.org/docs/9.1/sql-createtrigger.html). The only custom
logic we need to define on a trigger channel is the ``model`` class-level
attribute.


Model Migrations
----------------------------

Note that the payload captures the snapshot of the ``Author`` instance for some
time. Later it will be deserialized (see more about this below in the
Listeners section). It may happen that by that time the ``Author`` model is
migrated in django and this requires careful handling to make sure the payload
can still be deserialized and processed. Special handling is required when the
migration is backward incompatible like making existing field mandatory.

Let's look to the example how to do that and what tooling ``pgpubsub`` provides
to facilitate that. Let's says we want to add a new mandatory text field
``email`` to ``Author``.

This is done in three steps (releases):

1. New optional field is added. Application is modified so that new records
   always get a value in ``email`` field.
2. Values are populated in the existing records.
3. Fields is made mandatory.

Note that before release 2 is deployed and the migration that populates the
field is applied modifications to some ``Author`` entities would produce
payloads that do not have value in the ``email`` field.

When release 3 is deployed the application may assume that every ``Author`` has
``email``. The problem is that the notifications produced before release 2 is
deployed may be still not processed (for example the listener process was not
run or there was an issue with the processing of some specific notification and
it was skipped). In order to safely deploy release 3 the deployer need to know
if there are any notifications that were created before django migrations of
the release 2 were applied.

To facilitate this ``Notification`` entity stores ``db_version`` field which
contains the latest migration identier for the django app the ``Author`` is
defined in. The deployer may check if there are any notifications with the old
``db_version`` before deploying version that potentially breaks backward
compatibility in terms of the data structure.

In this case deployer should check that there are no ``Notification`` entities
with ``db_version`` before the version that was assigned to the migrations in
release 2.
