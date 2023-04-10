.. _recovery:

Recovery
========

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

Note that this recovery option can be enabled whenever we use the ``listen`` management command
by supplying it with the ``--recover`` option. This will tell the listening processes to replay
any missed stored notifications automatically when it starts up.
