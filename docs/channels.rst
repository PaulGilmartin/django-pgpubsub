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
In this example, ``old`` would refer to the state of our ``Author`` object
pre-creation (and would hence be ``None``) and ``new`` would refer to a copy of
the newly created ``Author`` instance. This payload is inspired by the ``OLD``
and ``NEW`` values available in the postgres ``CREATE TRIGGER`` statement
(https://www.postgresql.org/docs/9.1/sql-createtrigger.html). The only custom
logic we need to define on a trigger channel is the ``model`` class-level
attribute.
