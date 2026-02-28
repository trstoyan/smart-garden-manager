from django.core.management.base import BaseCommand

from plants.services import PestIncidentService


class Command(BaseCommand):
    help = 'Schedule pest/disease incident follow-up events and notifications.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=PestIncidentService.DEFAULT_HORIZON_DAYS,
            help='Look-ahead window in days for follow-up scheduling.',
        )

    def handle(self, *args, **options):
        service = PestIncidentService()
        result = service.schedule_followups(horizon_days=options['days'])
        self.stdout.write(
            self.style.SUCCESS(
                (
                    'Incidents considered: {incidents_considered}, '
                    'created events: {created_events}, '
                    'created notifications: {created_notifications}.'
                ).format(**result)
            )
        )
