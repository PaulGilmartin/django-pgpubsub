from django.apps import AppConfig


class TestsConfig(AppConfig):
    name = 'pgpubsub.tests'
    default_auto_field = 'django.db.models.AutoField'

    def ready(self):
        import pgpubsub.tests.listeners  # noqa
