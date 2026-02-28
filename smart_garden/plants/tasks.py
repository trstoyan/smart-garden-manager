from celery import shared_task

from .services import (
    DeviceActionDispatcher,
    DeviceAutomationService,
    NotificationDispatcher,
    PestIncidentService,
    UpcomingNotificationScheduler,
)


@shared_task
def generate_upcoming_notifications_task(days=2, daily_limit=12):
    scheduler = UpcomingNotificationScheduler(horizon_days=days, daily_limit=daily_limit)
    return scheduler.generate()


@shared_task
def process_notifications_task(batch_size=100, max_attempts=6):
    dispatcher = NotificationDispatcher(max_attempts=max_attempts)
    return dispatcher.dispatch_pending(batch_size=batch_size)


@shared_task
def evaluate_automations_task():
    service = DeviceAutomationService()
    return service.evaluate()


@shared_task
def process_device_actions_task(batch_size=100, max_attempts=6):
    dispatcher = DeviceActionDispatcher(max_attempts=max_attempts)
    return dispatcher.dispatch_pending(batch_size=batch_size)


@shared_task
def schedule_pest_followups_task(days=3):
    service = PestIncidentService()
    return service.schedule_followups(horizon_days=days)
