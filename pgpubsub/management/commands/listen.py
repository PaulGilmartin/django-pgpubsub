import multiprocessing

from django.core.management import BaseCommand

from pgpubsub.listen import listen


class Command(BaseCommand):
    help = 'Listen to the named postgres channel(s) for notifications.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--channels',
            type=str,
            dest='channels',
            nargs='+',
        )
        parser.add_argument(
            '--processes',
            type=int,
            dest='processes',
        )
        parser.add_argument(
            '--recover',
            action='store_true',
            dest='recover',
            default=False,
            help='Process all stored notifications for selected channels.',
        )

    def handle(self, *args, **options):
        channel_names = options.get('channels')
        processes = options.get('processes') or 1
        recover = options.get('recover', False)
        multiprocessing.set_start_method('fork', force=True)
        for i in range(processes):
            process = multiprocessing.Process(
                name=f'pgpubsub_process_{i}',
                target=listen,
                args=(channel_names, recover),
            )
            process.start()
