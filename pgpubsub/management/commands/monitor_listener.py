from threading import Event

from django.core.management import BaseCommand

from pgpubsub.metrics import configure_monitoring


class Command(BaseCommand):
    help = 'Send listener metrics periodically to the monitoring system.'

    def handle(self, *args, **options):
        configure_monitoring()
        Event().wait()
