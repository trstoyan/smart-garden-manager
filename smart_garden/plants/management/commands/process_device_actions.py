from django.core.management.base import BaseCommand

from plants.services import DeviceActionDispatcher


class Command(BaseCommand):
    help = 'Dispatch queued device actions, with retry/backoff handling.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=DeviceActionDispatcher.DEFAULT_BATCH_SIZE,
            help='Maximum number of device actions to process in this run.',
        )
        parser.add_argument(
            '--max-attempts',
            type=int,
            default=DeviceActionDispatcher.DEFAULT_MAX_ATTEMPTS,
            help='Maximum retry attempts before action is marked failed.',
        )

    def handle(self, *args, **options):
        dispatcher = DeviceActionDispatcher(max_attempts=options['max_attempts'])
        result = dispatcher.dispatch_pending(batch_size=options['batch_size'])
        self.stdout.write(
            self.style.SUCCESS(
                'Processed {processed} action(s): {executed} executed, {failed} failed.'.format(**result)
            )
        )
