from django.core.management import BaseCommand

from pgpubsub.listen import listen


class Command(BaseCommand):
    help = 'Listen to the named postgres channel for notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--channels',
            type=str,
            dest='channels',
            nargs='+',
        )

    def handle(self, *args, **options):
        channel_names = options.get('channels')
        listen(channel_names)
