.. _payload_context:

Payload Context
===============

Sometimes it is beneficial to pass some contextual information from the trigger
to the trigger listener along the payload. Examples are:

- tracing information that allows to track complex request processing in a
  multi component system
- in a multitenant system a tenant information to be able to identify the
  tenant that peformed an operation that triggered a notification


This can be done by using **Payload Context**. This feature includes:

- ability to add an additional information to the payload in the trigger
- ability to filter by the fields in the context in the listener process
- ability to use ``context`` fields in the listener callbacks


Add ``context`` to payload in the trigger
-----------------------------------------

Before doing updates that produce notifications set the context that should be
passed using ``pgpubsub.set_notification_context`` function. 

.. code-block:: python

    from pgpubsub import set_notification_context

    set_notification_context({'some-key': 'some-value'})

The setting is effective till the end of the current transanction.


Filter by ``context`` field in the trigger listener
---------------------------------------------------

Define a class that implements ``ListenerFilterProvider`` protocol and set
option ``PGPUBSUB_LISTENER_FILTER`` to its fully qualified class name.

.. code-block:: python

    from pgpubsub import ListenerFilterProvider

    class TenantListenerFilterProvider(ListenerFilterProvider):
        def get_filter(self) -> Q:
            return Q(payload__context__tenant='my-tenant')

    # django settings
    PGPUBSUB_LISTENER_FILTER = 'myapp.whatever.TenantListenerFilterProvider'

This configuration will skip any notifications that do not have ``tenant`` field
equal to ``my-tenant`` in the payload's ``context`` field.

Pass ``context`` field to the trigger listener callback
-------------------------------------------------------

To enable this set ``PGPUBSUB_CONTEXT_TO_LISTENERS`` to ``True`` in django
settings and add a ``context`` parameter to the listener callback.

.. code-block:: python

    # listeners.py
    import pgpubsub
    from pgpubsub.tests.channels import AuthorTriggerChannel
    from pgpubsub.tests.models import Author, Post

    @pgpubsub.post_insert_listener(AuthorTriggerChannel)
    def create_first_post_for_author(
        old: Author, new: Author, context: Dict[str, Any]
    ):
        print(f'Creating first post for {new.name} with context={context}')
        Post.objects.create(
            author_id=new.pk,
            content='Welcome! This is your first post',
            date=datetime.date.today(),
        )

    # django settings
    PGPUBSUB_PASS_CONTEXT_TO_LISTENERS = True
