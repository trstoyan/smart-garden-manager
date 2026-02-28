from django.core.management.base import BaseCommand

from plants.services import NotificationDispatcher


class Command(BaseCommand):
    help = 'Dispatch queued notifications, with retry/backoff handling.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=NotificationDispatcher.DEFAULT_BATCH_SIZE,
            help='Maximum number of notifications to process in this run.',
        )
        parser.add_argument(
            '--max-attempts',
            type=int,
            default=NotificationDispatcher.DEFAULT_MAX_ATTEMPTS,
            help='Maximum retry attempts before notification is skipped.',
        )

    def handle(self, *args, **options):
        dispatcher = NotificationDispatcher(max_attempts=options['max_attempts'])
        result = dispatcher.dispatch_pending(batch_size=options['batch_size'])
        self.stdout.write(
            self.style.SUCCESS(
                'Processed {processed} notification(s): {sent} sent, {failed} failed.'.format(**result)
            )
        )
