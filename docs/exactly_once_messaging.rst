.. _exactly_once_messaging:

Exactly Once Messaging
======================

In the default implementation of the Postgres ``LISTEN/NOTIFY`` protocol,
multiple processes listening to the same channel will result in each process acting upon
each notification sent through that channel. This behaviour is often undesirable, so
``pgpubsub`` offers users the option to define channels which allow one, and only one,
listening process to act upon each notification. We can achieve this simply by defining
``lock_notifications = True`` on our channel object. This is the desired notification
processing behaviour for our ``AuthorTriggerChannel``, where we want to create exactly one
``Post`` whenever an ``Author`` row is inserted:

.. code-block:: python

    from dataclasses import dataclass

    from pgpubsub.channel import TriggerChannel
    from pgpubsub.tests.models import Author


    @dataclass
    class AuthorTriggerChannel(TriggerChannel):
        model = Author
        lock_notifications = True


.. note::

    When we change the value of ``lock_notifications`` on a trigger based
    channel, we must perform a ``migrate`` command after the change.

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

    .. code-block:: python

        notification = (
                Notification.objects.select_for_update(
                        skip_locked=True).filter(
                            channel=self.notification.channel,
                            payload=self.notification.payload,
                    ).first()
                )



   The fact that ``select_for_update`` in the above applies a lock on ``notification``
   ensures that no other process listening to the same channel can retrieve this notification
   object. Moreover, the use of ``skip_locked=True`` means that any process which
   cannot obtain the lock does not wait for the lock to release. This allows other
   processes to freely skip this notification and poll for others, whilst the one which
   did obtain the lock continues carries on to pass its notification into the
   listener callback. If the callback then successfully completes, the stored
   ``Notification`` is removed from the database.
