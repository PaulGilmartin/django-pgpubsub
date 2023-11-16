.. _payload_extras:

Payload Extras
==============

Sometimes it is beneficial to pass some contextual information from the trigger
to the trigger listener along the payload. Examples are:

- tracing information that allows to track complex request processing in a
  multi component system
- in a multitenant system a tenant information to be able to identify the
  tenant that peformed an operation that triggered a notification


This can be done by using **Payload Extras**. This feature includes:

- ability to add an additional a.k.a. extra information to the payload in the
  trigger
- ability to filter by the extra information in the listener process
- ability to use ``extra`` fields in the listener callbacks


Add ``extras`` to payload in the trigger
----------------------------------------

Define a postgres function that returns ``JSONB`` value that should be added to
the payload and set it using ``Notification.set_payload_extras_builder``.

.. code-block:: python

    from pgpubsub.models import Notification

    Notification.set_payload_extras_builder('get_tracing_extras')

The setting is effective for the current connection (by default) or till the
end of the current transanction if ``till_tx_end=True`` is specified.

The common pattern of usage is to store tracing information as a [custom
option](https://www.postgresql.org/docs/16/runtime-config-custom.html) when the
transaction is started using ``SET LOCAL myapp.myvalue = 'value'`` and then
retrive that via ``SELECT current_setting('myapp.myvalue')`` in a function
configured via ``set_payload_extras_builder``. 

See examples of usage in ``pgpubsub.tests.test_payload_extras.py``.


Filter by ``extras`` field in the trigger listener
--------------------------------------------------

Define a class that implements ``ListenerFilterProvider`` protocol and set option
``PGPUBSUB_LISTENER_FILTER`` to its fully qualified class name.

.. code-block:: python

    from pgpubsub.listeners import ListenerFilterProvider

    class TenantListenerFilterProvider(ListenerFilterProvider):
        def get_filter(self) -> Q:
            return Q(payload__extras__tenant='my-tenant')

    # django settings
    PGPUBSUB_LISTENER_FILTER = 'myapp.whatever.TenantListenerFilterProvider'

This configuration will skip any notifications that do not have ``tenant`` field
equal to ``my-tenant`` in the payload's ``extras`` field.

Pass ``extras`` field to the trigger listener callback
------------------------------------------------------

To enable this set ``PGPUBSUB_PASS_EXTRAS_TO_LISTENERS`` to ``True`` in django
settings and add a ``extras`` parameter to the listener callback.

.. code-block:: python

    # listeners.py
    import pgpubsub
    from pgpubsub.tests.channels import AuthorTriggerChannel
    from pgpubsub.tests.models import Author, Post

    @pgpubsub.post_insert_listener(AuthorTriggerChannel)
    def create_first_post_for_author(
        old: Author, new: Author, extras: Dict[str, Any]
    ):
        print(f'Creating first post for {new.name} with extras={extras}')
        Post.objects.create(
            author_id=new.pk,
            content='Welcome! This is your first post',
            date=datetime.date.today(),
        )

    # django settings
    PGPUBSUB_PASS_EXTRAS_TO_LISTENERS = True
