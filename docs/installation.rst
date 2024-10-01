Installation
============

Install django-pgpubsub with::

    pip3 install django-pgpubsub

After this, add ``pgpubsub`` to the ``INSTALLED_APPS``
setting of your Django project.

``django-pgpubsub`` ships with a ``Notification`` model. This table must
be added to the app's database via the usual django ``migrate`` command.
We should also add ``pgpubsub`` and ``pgtrigger`` into ``INSTALLED_APPS``.
If we wish to run the ``pgpubsub`` tests, we need to add
``pgpubsub.tests`` into ``INSTALLED_APPS`` too.

``pgpubsub`` is compatible with both ``psycopg2`` and ``psycopg``. Install the
version you prefer and ``pgpubsub`` will use it. If both are installed
``psycopg2`` is prefered in order to be compatible with the previous
``pgpubsub`` versions. Set environment variable
``PGPUBSUB_USE_PSYCOPG_V3=True`` to override and force ``psycopg`` version 3
usage.
