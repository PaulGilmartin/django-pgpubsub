Listening
=========

To have our listener functions listen for
incoming notifications on their associated channel, we can make use
of the ``listen`` management command provided by the ``pgpubsub`` library:

.. code-block::

    ./manage.py listen

When a process started in this manner encounters an exception, ``pgpubsub``
will automatically spin up a secondary process to continue listening before the
exception ends the initial process. This means that we do not have to worry about
restarting our listening processes any time a listener incurs a python level exception.

The ``listen`` command accepts three optional arguments:

* ``--channels``: a space separated list of the
  full module paths of the channels we wish to listen to.
  When no value is supplied, we default to listening to all registered channels
  in our project. For example, we can use the following command to listen to notifications coming through
  the ``PostReads`` channel only:

.. code-block::

    ./manage.py listen --channels 'pgpubsub.tests.channels.PostReads'


* ``--processes``: an integer which denotes the number of concurrent processes
  we wish to dedicate to listening to the specified channels. When no value is
  supplied, we default to using a single process. Note that if multiple processes
  are listening to the same channel then by default both processes will act on
  each notification. To prevent this and have each notification be acted upon
  by exactly one listening process, we need to add ``lock_notifications = True``
  to our channel. See the :ref:`exactly_once_messaging` section for more.

* ``--recover``: when supplied, we process all *stored* notifications for any
  of the selected channels. When no ``channels`` argument is supplied with ``recover``,
  we process notifications of all registered channels with ``lock_notifications=True``.
  See the :ref:`recovery` section for more.

Here's an example of using all three options in one command:

.. code-block::

    ./manage.py listen --channels 'pgpubsub.tests.channels.AuthorTriggerChannel' --processes 2 --recover
