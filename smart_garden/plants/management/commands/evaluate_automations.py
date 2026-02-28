from django.core.management.base import BaseCommand

from plants.services import DeviceAutomationService


class Command(BaseCommand):
    help = 'Evaluate latest sensor readings and queue device automation actions.'

    def handle(self, *args, **options):
        service = DeviceAutomationService()
        result = service.evaluate()
        self.stdout.write(
            self.style.SUCCESS(
                'Evaluated {devices_evaluated} device(s), created {actions_created} action(s).'.format(**result)
            )
        )
