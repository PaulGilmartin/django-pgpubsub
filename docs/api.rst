.. _api:

API
===

Below are the core classes and functions of the ``pgpubsub`` module.


Channels
--------

.. autoclass:: pgpubsub.Channel


.. autoclass:: pgpubsub.TriggerChannel


Listeners
---------

.. autofunction:: pgpubsub.listener


.. autofunction:: pgpubsub.pre_save_listener


.. autofunction:: pgpubsub.post_save_listener


.. autofunction:: pgpubsub.pre_insert_listener


.. autofunction:: pgpubsub.post_insert_listener


.. autofunction:: pgpubsub.pre_update_listener


.. autofunction:: pgpubsub.post_update_listener


.. autofunction:: pgpubsub.pre_delete_listener


.. autofunction:: pgpubsub.post_delete_listener


.. autofunction:: pgpubsub.trigger_listener


Notifiers
---------

.. autofunction:: pgpubsub.notify


.. autofunction:: pgpubsub.process_stored_notifications
