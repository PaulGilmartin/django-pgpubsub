Listeners
=========

In the ``pgpubsub`` library, a *listener* is the function
which processes notifications sent through some particular channel.

A listener must be defined in our app's ``listeners.py`` file and must
be declared using one of the decorators in ``pgpubsub.listen.py``.
These decorators are also responsible for pointing a listener function
to listen to a particular channel. When a function is associated to a channel
in this way, we say that function *listening* to that channel.


The ``listener`` Decorator
--------------------------

Continuing with the example whereby we maintain a cache of post reads,
we implement a listener function like so:

.. code-block:: python

    # tests/listeners.py
    from collections import defaultdict
    import datetime

    import pgpubsub
    from pgpubsub.tests.channels import PostReads

    # Simple cache for illustrative purposes only
    post_reads_per_date_cache = defaultdict(dict)


    @pgpubsub.listener(PostReads)
    def update_post_reads_per_date_cache(model_id: int, date: datetime.date):
        current_count = post_reads_per_date_cache[date].get(model_id, 0)
        post_reads_per_date_cache[date][model_id] = current_count + 1


A few notes on the above:

* The channel we associate to a listener also
  defines the signature of the listener function.
* The notification payload is deserialized
  in such a way that the input arguments to the listener function
  have the same type as was declared on the ``PostReads`` channel.
* It is possible to have multiple
  listeners to a single channel and the signatures of those listeners
  can vary by arguments declared as optional kwargs on their common channel -
  see ``pgpubsub.tests.listeners.py`` for an example.


Trigger Listeners
-----------------

Next we implement the listener which is used to asynchronously
create a ``Post`` object whenever a new ``Author`` object is created.
For this listener, we can use the pre-defined ``post_insert_listener``
decorator:

.. code-block:: python

    # tests/listeners.py
    import datetime

    import pgpubsub
    from pgpubsub.tests.channels import AuthorTriggerChannel
    from pgpubsub.tests.models import Author, Post


    @pgpubsub.post_insert_listener(AuthorTriggerChannel)
    def create_first_post_for_author(old: Author, new: Author):
        print(f'Creating first post for {new.name}')
        Post.objects.create(
            author_id=new.pk,
            content='Welcome! This is your first post',
            date=datetime.date.today(),
        )

Any listener associated to a trigger-based channel (one inheriting from
``TriggerChannel``) necessarily has a signature consisting of the ``old``
and ``new`` payload described in the previous section.

Note that declaring a trigger-based listener in the manner above *actually
writes a postgres-trigger to our database*. This is achieved by
leveraging the ``django-pgtrigger`` library to write a pg-trigger
which will send a payload using the postgres ``NOTIFY`` command
whenever an ``Author`` object is inserted into the database. Note that
as with all triggers defined using ``django-pgtrigger``, this trigger
is first written to the database after a migration.


.. note::

    We must perform a django ``migrate`` command after adding (or changing)
    a listener on a trigger channel as above.


Finally, we must also ensure that this ``listeners.py`` module is imported
into the app's config class (similar to how one would use django signals):

.. code-block:: python

    # tests/apps.py
    from django.apps import AppConfig


    class TestsConfig(AppConfig):
        name = 'tests'

        def ready(self):
            import pgpubsub.tests.listeners

