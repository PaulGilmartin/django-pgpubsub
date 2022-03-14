from django.apps import AppConfig


class TestsConfig(AppConfig):
    name = 'pgpubsub.tests'

    def ready(self):
        import pgpubsub.tests.listeners  # noqa
