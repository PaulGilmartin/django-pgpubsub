.. _example_app:

Example Application
===================

Suppose we have the following basic django models (a fully executable version of this example can be
found in ``pgpubsub.tests``):

.. code-block:: python

    # models.py
    class Author(models.Model):
        user = models.ForeignKey(
            User,
            on_delete=models.PROTECT,
            null=True,
        )
        name = models.TextField()


    class Post(models.Model):
        content = models.TextField()
        date = models.DateTimeField()
        author = models.ForeignKey(
            Author,
            null=True,
            on_delete=models.SET_NULL,
            related_name='entries',
        )


Given these models, we'll describe the mechanics of using the ``pgpubsub`` library
to achieve the following aims (which are for illustrative purposes only):

* To asynchronously maintain a cache of how frequently ``Post`` objects are
  read per day.

* To define a postgres-trigger to ensure that, whenever an ``Author`` object is created, a ``Post`` object is
  asynchronously created for that author with the title "Test Post".
