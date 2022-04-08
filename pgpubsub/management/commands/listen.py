import multiprocessing

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
        parser.add_argument(
            '--processes',
            type=int,
            dest='processes',
        )

    def handle(self, *args, **options):
        channel_names = options.get('channels')
        processes = options.get('processes', 1)
        print(f'Processes {processes}')
        for i in range(processes):
            process = multiprocessing.Process(
                name=f'pgpubsub_process_{i}',
                target=listen,
                args=(channel_names,),
            )
            process.start()
