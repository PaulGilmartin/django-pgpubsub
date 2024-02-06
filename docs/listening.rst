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

In some cases this might be not needed or desired e.g. when the listener is already run
in the environment that monitors and restarts the process on a failure (e.g. as part of
k8s deployment). In this case two additional options may be used namely ``--worker``
and ``--no-restart-on-failure``.

The ``listen`` command accepts several optional arguments:

* ``--channels``: a space separated list of the
  full module paths of the channels we wish to listen to.
  When no value is supplied, we default to listening to all registered channels
  in our project. For example, we can use the following command to listen to notifications coming through
  the ``PostReads`` channel only:

.. code-block::

    ./manage.py listen --channels 'pgpubsub.tests.channels.PostReads'


* ``--processes``: an integer which denotes the number of concurrent worker processes
  we wish to dedicate to listening to the specified channels. When no value is
  supplied, we default to using a single worker process. Note that if multiple processes
  are listening to the same channel then by default both processes will act on
  each notification. To prevent this and have each notification be acted upon
  by exactly one listening process, we need to add ``lock_notifications = True``
  to our channel. See the :ref:`exactly_once_messaging` section for more.

* ``--recover``: when supplied, we process all *stored* notifications for any
  of the selected channels. When no ``channels`` argument is supplied with ``recover``,
  we process notifications of all registered channels with ``lock_notifications=True``.
  See the :ref:`recovery` section for more.

* ``--loglevel``: when supplied, it sets the log level. The default is 'info'.

* ``--logformat``: when supplied, it sets the logger format using format syntax for python logging.

* ``--worker``: when supplied a single process that listens and processed notifications
  is run. This option cannot be used together with ``--processes`` option.

* ``--no-restart-on-failure``: when supplied a failure in the listener worker process
  will not cause automatic process restart. This is useful mainly when ``--worker``
  option is used. This can be used for the master process that is combined with
  ``--processes`` as well but it makes little sense as on the error in the child worker
  process it will not be restarted.

* ``--worker-start-method``: method to be used to start worker processes. Possible
  values are "spawn" (default) and "fork". "fork" is quicker but cannot be used if the
  processes starts additional threads.

Here's an example of using options in one command to run two processes that would
automatically recover on failure:

.. code-block::

    ./manage.py listen --channels 'pgpubsub.tests.channels.AuthorTriggerChannel' --processes 2 --recover --loglevel debug --logformat '%(asctime)s %(message)s'

Here's an example of using options in one command to run a process that wouldn't
automatically restart on failure:

.. code-block::

    ./manage.py listen --channels 'pgpubsub.tests.channels.AuthorTriggerChannel' --worker --recover --no-restart-on-failure
