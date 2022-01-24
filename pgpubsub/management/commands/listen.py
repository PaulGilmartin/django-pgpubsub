from django.core.management import BaseCommand

from pgpubsub.channel import ChannelBase


class Command(BaseCommand):
    help = 'Listen to the named postgres channel for notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--channel',
            type=str,
            dest='channel',
        )

    def handle(self, *args, **options):
        ChannelBase.get(options['channel']).listen()
