from django.core.management.base import BaseCommand

from plants.services import UpcomingNotificationScheduler


class Command(BaseCommand):
    help = 'Generate upcoming care events and queue notifications from planner output.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=UpcomingNotificationScheduler.DEFAULT_HORIZON_DAYS,
            help='Planning horizon (days) for upcoming notifications.',
        )
        parser.add_argument(
            '--daily-limit',
            type=int,
            default=UpcomingNotificationScheduler.DEFAULT_DAILY_LIMIT,
            help='Maximum planned care tasks per day.',
        )

    def handle(self, *args, **options):
        scheduler = UpcomingNotificationScheduler(
            horizon_days=options['days'],
            daily_limit=options['daily_limit'],
        )
        result = scheduler.generate()
        self.stdout.write(
            self.style.SUCCESS(
                (
                    'Generated from {tasks} task(s): '
                    '{created_events} new event(s), '
                    '{created_notifications} new notification(s).'
                ).format(**result)
            )
        )
