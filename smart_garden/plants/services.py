import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Optional
from urllib import error as urlerror
from urllib import request as urlrequest

from django.core.mail import send_mail
from django.db import models
from django.utils import timezone

from .models import (
    CalendarEvent,
    DeviceAction,
    Notification,
    PestIncident,
    Plant,
    PlantCareRule,
    SensorReading,
)


@dataclass(frozen=True)
class CareTask:
    plant_id: int
    plant_name: str
    garden_name: str
    event_type: str
    due_date: date
    scheduled_date: date
    is_overdue: bool
    days_overdue: int
    soil_moisture: Optional[int] = None
    adjustment_reason: Optional[str] = None


class CareTaskPlanner:
    DEFAULT_HORIZON_DAYS = 14
    MAX_HORIZON_DAYS = 60
    DEFAULT_DAILY_LIMIT = 6
    MAX_PLANNING_SPAN_DAYS = 120

    SOIL_MOISTURE_WET_THRESHOLD = 600
    SOIL_MOISTURE_DRY_THRESHOLD = 400
    SOIL_MOISTURE_STALE_HOURS = 24
    SOIL_MOISTURE_DELAY_DAYS = 1

    HOT_TEMPERATURE_THRESHOLD = 30.0
    COLD_TEMPERATURE_THRESHOLD = 10.0
    LOW_HUMIDITY_THRESHOLD = 35.0
    DRYING_TREND_THRESHOLD = -40
    WETTING_TREND_THRESHOLD = 40

    def __init__(self, *, start_date=None, horizon_days=DEFAULT_HORIZON_DAYS, daily_limit=DEFAULT_DAILY_LIMIT):
        self.start_date = start_date or timezone.now().date()
        self.horizon_days = max(1, min(int(horizon_days), self.MAX_HORIZON_DAYS))
        self.daily_limit = max(1, int(daily_limit))

    def build_tasks(self, plants=None):
        if plants is None:
            plants = Plant.objects.select_related('group__garden', 'group__plant_type').all()
        plants = list(plants)
        rules_by_plant = self._effective_rules_by_plant(plants)
        latest_readings = self._latest_readings_by_garden(plants)
        soil_trends = self._soil_moisture_trend_by_garden(plants)

        tasks = []
        for plant in plants:
            rule = rules_by_plant.get(plant.id)
            watering_due_date = self._next_watering_date(plant, rule)
            watering_due_date, adjustment_reason, soil_moisture = self._apply_soil_moisture_adjustment(
                plant=plant,
                due_date=watering_due_date,
                latest_readings=latest_readings,
                rule=rule,
            )
            watering_due_date, env_reason = self._apply_environmental_adjustment(
                plant=plant,
                due_date=watering_due_date,
                latest_readings=latest_readings,
            )
            watering_due_date, profile_reason = self._apply_zone_profile_adjustment(
                plant=plant,
                due_date=watering_due_date,
            )
            watering_due_date, container_reason = self._apply_container_trend_adjustment(
                plant=plant,
                due_date=watering_due_date,
                latest_readings=latest_readings,
                soil_trends=soil_trends,
            )

            reasons = [
                reason for reason in (adjustment_reason, env_reason, profile_reason, container_reason) if reason
            ]
            tasks.append(
                self._build_task(
                    plant,
                    'water',
                    watering_due_date,
                    soil_moisture=soil_moisture,
                    adjustment_reason='; '.join(reasons) if reasons else None,
                )
            )

            fertilize_due = self._apply_fertilization_workflow(
                plant=plant,
                fertilize_due_date=self._next_fertilization_date(plant, rule),
                watering_due_date=watering_due_date,
                rule=rule,
            )
            tasks.append(self._build_task(plant, 'fertilize', fertilize_due))

            tasks.append(self._build_task(plant, 'repot', self._next_repotting_date(plant, rule)))

        return self._balance_tasks(tasks)

    def tasks_in_window(self, plants=None):
        tasks = self.build_tasks(plants=plants)
        window_end = self.start_date + timedelta(days=self.horizon_days - 1)
        return [task for task in tasks if self.start_date <= task.scheduled_date <= window_end]

    def grouped_tasks_in_window(self, plants=None):
        grouped = defaultdict(list)
        for task in self.tasks_in_window(plants=plants):
            grouped[task.scheduled_date].append(task)
        return grouped

    def _build_task(self, plant, event_type, due_date, soil_moisture=None, adjustment_reason=None):
        is_overdue = due_date < self.start_date
        days_overdue = (self.start_date - due_date).days if is_overdue else 0
        scheduled_date = self.start_date if is_overdue else due_date
        return CareTask(
            plant_id=plant.id,
            plant_name=plant.name,
            garden_name=plant.group.garden.name,
            event_type=event_type,
            due_date=due_date,
            scheduled_date=scheduled_date,
            is_overdue=is_overdue,
            days_overdue=days_overdue,
            soil_moisture=soil_moisture,
            adjustment_reason=adjustment_reason,
        )

    def _latest_readings_by_garden(self, plants):
        garden_ids = {plant.group.garden_id for plant in plants}
        if not garden_ids:
            return {}

        cutoff = timezone.now() - timedelta(hours=self.SOIL_MOISTURE_STALE_HOURS)
        readings = (
            SensorReading.objects
            .filter(device__garden_id__in=garden_ids, timestamp__gte=cutoff)
            .select_related('device__garden')
            .order_by('device__garden_id', '-timestamp')
        )

        latest_by_garden = {}
        for reading in readings:
            garden_id = reading.device.garden_id
            if garden_id not in latest_by_garden:
                latest_by_garden[garden_id] = reading
        return latest_by_garden

    def _soil_moisture_trend_by_garden(self, plants):
        garden_ids = {plant.group.garden_id for plant in plants}
        if not garden_ids:
            return {}

        cutoff = timezone.now() - timedelta(hours=12)
        readings = (
            SensorReading.objects
            .filter(
                device__garden_id__in=garden_ids,
                timestamp__gte=cutoff,
                soil_moisture__isnull=False,
            )
            .select_related('device__garden')
            .order_by('device__garden_id', '-timestamp')
        )

        bucket = defaultdict(list)
        for reading in readings:
            garden_id = reading.device.garden_id
            if len(bucket[garden_id]) < 2:
                bucket[garden_id].append(reading)

        trends = {}
        for garden_id, two_points in bucket.items():
            if len(two_points) == 2:
                newest, older = two_points[0], two_points[1]
                trends[garden_id] = newest.soil_moisture - older.soil_moisture
        return trends

    def _effective_rules_by_plant(self, plants):
        plant_ids = [plant.id for plant in plants]
        group_ids = {plant.group_id for plant in plants}
        if not plant_ids:
            return {}

        rules = list(
            PlantCareRule.objects.filter(enabled=True)
            .filter(models.Q(plant_id__in=plant_ids) | models.Q(group_id__in=group_ids))
            .select_related('plant', 'group')
            .order_by('priority', 'id')
        )

        plant_rules = {}
        group_rules = {}
        for rule in rules:
            if rule.scope == 'plant' and rule.plant_id and rule.plant_id not in plant_rules:
                plant_rules[rule.plant_id] = rule
            elif rule.scope == 'group' and rule.group_id and rule.group_id not in group_rules:
                group_rules[rule.group_id] = rule

        return {
            plant.id: plant_rules.get(plant.id) or group_rules.get(plant.group_id)
            for plant in plants
        }

    def _next_watering_date(self, plant, rule=None):
        if not rule or rule.watering_interval_days is None:
            return plant.get_next_watering_date()
        interval = max(1, int(rule.watering_interval_days))
        last = plant.last_watered or timezone.now().date()
        return last + timedelta(days=interval)

    def _next_fertilization_date(self, plant, rule=None):
        if not rule or rule.fertilization_interval_days is None:
            return plant.get_next_fertilization_date()
        interval = max(1, int(rule.fertilization_interval_days))
        last = plant.last_fertilized or timezone.now().date()
        return last + timedelta(days=interval)

    def _next_repotting_date(self, plant, rule=None):
        if not rule or rule.repotting_interval_days is None:
            return plant.get_next_repotting_date()
        interval = max(1, int(rule.repotting_interval_days))
        last = plant.last_repotted or timezone.now().date()
        return last + timedelta(days=interval)

    def _apply_soil_moisture_adjustment(self, plant, due_date, latest_readings, rule=None):
        reading = latest_readings.get(plant.group.garden_id)
        if not reading or reading.soil_moisture is None:
            return due_date, None, None

        wet_threshold = self._effective_soil_moisture_threshold(plant, rule)
        dry_threshold = self._effective_soil_moisture_dry_threshold(plant, rule)
        if reading.soil_moisture >= wet_threshold:
            delayed_due_date = max(
                due_date + timedelta(days=self.SOIL_MOISTURE_DELAY_DAYS),
                self.start_date + timedelta(days=self.SOIL_MOISTURE_DELAY_DAYS),
            )
            reason = f"Delayed: soil moisture {reading.soil_moisture} >= {wet_threshold}"
            return delayed_due_date, reason, reading.soil_moisture
        if reading.soil_moisture <= dry_threshold:
            accelerated = max(self.start_date, due_date - timedelta(days=1))
            if accelerated != due_date:
                reason = f"Accelerated: soil moisture {reading.soil_moisture} <= {dry_threshold}"
                return accelerated, reason, reading.soil_moisture

        return due_date, None, reading.soil_moisture

    def _apply_environmental_adjustment(self, plant, due_date, latest_readings):
        reading = latest_readings.get(plant.group.garden_id)
        if not reading:
            return due_date, None

        if (
            reading.temperature is not None and reading.humidity is not None
            and reading.temperature >= self.HOT_TEMPERATURE_THRESHOLD
            and reading.humidity <= self.LOW_HUMIDITY_THRESHOLD
        ):
            adjusted = max(self.start_date, due_date - timedelta(days=1))
            if adjusted != due_date:
                return adjusted, (
                    f"Accelerated: hot/dry ({reading.temperature:.1f}C/{reading.humidity:.1f}%)"
                )

        if reading.temperature is not None and reading.temperature <= self.COLD_TEMPERATURE_THRESHOLD:
            adjusted = due_date + timedelta(days=1)
            return adjusted, f"Delayed: cold temperature {reading.temperature:.1f}C"

        return due_date, None

    def _apply_zone_profile_adjustment(self, plant, due_date):
        garden = plant.group.garden
        plant_type = plant.group.plant_type
        if not garden.usda_hardiness_zone:
            return due_date, None

        zone_number = self._parse_zone_number(garden.usda_hardiness_zone)
        if zone_number is None:
            return due_date, None

        min_zone = plant_type.preferred_usda_zone_min
        max_zone = plant_type.preferred_usda_zone_max
        if min_zone is None and max_zone is None:
            return due_date, None

        if min_zone is not None and zone_number < min_zone:
            return due_date + timedelta(days=1), f"Profile delay: zone {zone_number} < preferred {min_zone}"
        if max_zone is not None and zone_number > max_zone:
            adjusted = max(self.start_date, due_date - timedelta(days=1))
            if adjusted != due_date:
                return adjusted, f"Profile accelerate: zone {zone_number} > preferred {max_zone}"

        return due_date, None

    def _apply_container_trend_adjustment(self, plant, due_date, latest_readings, soil_trends):
        reading = latest_readings.get(plant.group.garden_id)
        trend = soil_trends.get(plant.group.garden_id)
        adjustment_days = 0
        reasons = []

        substrate = plant.substrate_type or plant.group.plant_type.default_substrate_type
        if substrate in {'coco', 'hydro'}:
            adjustment_days -= 1
            reasons.append(f"substrate={substrate}")
        elif substrate == 'soil':
            adjustment_days += 0

        if plant.pot_volume_liters is not None:
            if plant.pot_volume_liters < 2:
                adjustment_days -= 1
                reasons.append("small pot")
            elif plant.pot_volume_liters > 15:
                adjustment_days += 1
                reasons.append("large pot")

        if plant.drainage_class is not None:
            if plant.drainage_class <= 2:
                adjustment_days += 1
                reasons.append("low drainage")
            elif plant.drainage_class >= 4:
                adjustment_days -= 1
                reasons.append("high drainage")

        moisture_pref = plant.group.plant_type.moisture_preference
        if moisture_pref == 'moist':
            adjustment_days -= 1
            reasons.append("moist preference")
        elif moisture_pref == 'dry':
            adjustment_days += 1
            reasons.append("dry preference")

        if trend is not None:
            if trend <= self.DRYING_TREND_THRESHOLD:
                adjustment_days -= 1
                reasons.append(f"drying trend {trend}")
            elif trend >= self.WETTING_TREND_THRESHOLD:
                adjustment_days += 1
                reasons.append(f"wetting trend {trend}")

        if (
            reading is not None
            and reading.soil_moisture is not None
            and plant.soil_moisture_critical_threshold is not None
            and reading.soil_moisture <= plant.soil_moisture_critical_threshold
        ):
            urgent_date = self.start_date
            return urgent_date, (
                f"Urgent: soil moisture {reading.soil_moisture} <= critical {plant.soil_moisture_critical_threshold}"
            )

        adjustment_days = max(-2, min(2, adjustment_days))
        adjusted_due = due_date + timedelta(days=adjustment_days)
        if adjusted_due < self.start_date:
            adjusted_due = self.start_date
        if adjusted_due == due_date or not reasons:
            return due_date, None
        return adjusted_due, f"Container/profile adjust ({', '.join(reasons)})"

    def _parse_zone_number(self, zone_value):
        digits = ''.join(ch for ch in str(zone_value) if ch.isdigit())
        if not digits:
            return None
        try:
            return int(digits[:2]) if len(digits) >= 2 else int(digits)
        except ValueError:
            return None

    def _apply_fertilization_workflow(self, plant, fertilize_due_date, watering_due_date, rule=None):
        requires_pre = (
            rule.requires_pre_watering
            if rule and rule.requires_pre_watering is not None
            else plant.requires_pre_watering_before_fertilizing()
        )
        if not requires_pre:
            return fertilize_due_date
        gap_days = (
            max(0, int(rule.pre_fertilization_water_gap_days))
            if rule and rule.pre_fertilization_water_gap_days is not None
            else max(0, int(plant.get_pre_fertilization_water_gap_days()))
        )
        effective_watering_day = max(self.start_date, watering_due_date)
        min_due = effective_watering_day + timedelta(days=gap_days)
        return max(fertilize_due_date, min_due)

    def _effective_soil_moisture_threshold(self, plant, rule=None):
        if rule and rule.soil_moisture_wet_threshold is not None:
            return rule.soil_moisture_wet_threshold
        if plant.soil_moisture_wet_threshold is not None:
            return plant.soil_moisture_wet_threshold
        if plant.group.garden.soil_moisture_wet_threshold is not None:
            return plant.group.garden.soil_moisture_wet_threshold
        return self.SOIL_MOISTURE_WET_THRESHOLD

    def _effective_soil_moisture_dry_threshold(self, plant, rule=None):
        if rule and rule.soil_moisture_dry_threshold is not None:
            return rule.soil_moisture_dry_threshold
        if plant.soil_moisture_critical_threshold is not None:
            return plant.soil_moisture_critical_threshold
        if plant.group.garden.soil_moisture_dry_threshold is not None:
            return plant.group.garden.soil_moisture_dry_threshold
        return self.SOIL_MOISTURE_DRY_THRESHOLD

    def _balance_tasks(self, tasks):
        planned = []
        daily_load = defaultdict(int)
        planning_end = self.start_date + timedelta(days=self.MAX_PLANNING_SPAN_DAYS)

        sorted_tasks = sorted(
            tasks,
            key=lambda task: (-task.days_overdue, task.due_date, task.plant_name, task.event_type),
        )

        for task in sorted_tasks:
            day = max(task.scheduled_date, self.start_date)
            while day <= planning_end and daily_load[day] >= self.daily_limit:
                day += timedelta(days=1)

            if day > planning_end:
                day = planning_end

            daily_load[day] += 1
            planned.append(replace(task, scheduled_date=day))

        return planned


class HeuristicTaskOptimizer:
    EVENT_SCORE = {
        'water': 50,
        'fertilize': 30,
        'repot': 20,
        'other': 10,
    }
    OVERDUE_SCORE_PER_DAY = 100
    SOIL_DRY_BONUS = 20

    def __init__(self, *, daily_limit=6):
        self.daily_limit = max(1, int(daily_limit))

    def optimize(self, tasks, *, start_date=None):
        if not tasks:
            return []

        start = start_date or min(task.scheduled_date for task in tasks)
        scored = sorted(tasks, key=self._sorting_key, reverse=True)
        loads = defaultdict(int)
        optimized = []

        for task in scored:
            day = max(task.scheduled_date, start)
            while loads[day] >= self.daily_limit:
                day += timedelta(days=1)
            loads[day] += 1
            optimized.append(replace(task, scheduled_date=day))

        optimized.sort(key=lambda task: (task.scheduled_date, task.garden_name, -self._score(task), task.event_type))
        return optimized

    def _sorting_key(self, task):
        return (
            self._score(task),
            -task.days_overdue,
            -task.due_date.toordinal(),
            task.event_type == 'water',
        )

    def _score(self, task):
        score = self.EVENT_SCORE.get(task.event_type, 0)
        score += task.days_overdue * self.OVERDUE_SCORE_PER_DAY
        if task.soil_moisture is not None and task.soil_moisture < CareTaskPlanner.SOIL_MOISTURE_WET_THRESHOLD:
            score += self.SOIL_DRY_BONUS
        return score


class NotificationDispatcher:
    DEFAULT_BATCH_SIZE = 100
    DEFAULT_MAX_ATTEMPTS = 6
    RETRY_BACKOFF_MINUTES = (1, 5, 15, 60, 180, 720)
    DEFAULT_CHANNELS = ('log',)

    def __init__(self, *, logger=None, sender=None, max_attempts=DEFAULT_MAX_ATTEMPTS):
        self.logger = logger or logging.getLogger(__name__)
        self.sender = sender or self._default_sender
        self.max_attempts = max(1, int(max_attempts))

    def dispatch_pending(self, *, batch_size=DEFAULT_BATCH_SIZE):
        size = max(1, int(batch_size))
        now = timezone.now()
        pending = list(
            Notification.objects
            .select_related('plant', 'event')
            .filter(sent=False, attempts__lt=self.max_attempts)
            .filter(models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=now))
            .order_by('event__date', 'id')[:size]
        )

        sent_count = 0
        failed_count = 0
        for notification in pending:
            try:
                self.sender(notification)
                notification.sent = True
                notification.sent_at = now
                notification.last_error = ''
                notification.next_attempt_at = None
                sent_count += 1
            except Exception as exc:
                notification.attempts += 1
                notification.last_error = str(exc)[:1000]
                backoff_minutes = self._backoff_minutes(notification.attempts)
                notification.next_attempt_at = now + timedelta(minutes=backoff_minutes)
                failed_count += 1
                self.logger.warning(
                    'Notification dispatch failed id=%s attempt=%s next_attempt_at=%s error=%s',
                    notification.id,
                    notification.attempts,
                    notification.next_attempt_at,
                    notification.last_error,
                )

        if pending:
            Notification.objects.bulk_update(
                pending,
                ['sent', 'sent_at', 'attempts', 'last_error', 'next_attempt_at'],
            )

        return {
            'processed': len(pending),
            'sent': sent_count,
            'failed': failed_count,
        }

    def _default_sender(self, notification):
        channels = self._channels()
        for channel in channels:
            if channel == 'log':
                self._send_log(notification)
            elif channel == 'email':
                self._send_email(notification)
            elif channel == 'webhook':
                self._send_webhook(notification)
            else:
                raise ValueError(f'Unsupported notification channel: {channel}')

    def _channels(self):
        raw = os.getenv('NOTIFICATION_CHANNELS', ','.join(self.DEFAULT_CHANNELS))
        channels = [channel.strip().lower() for channel in raw.split(',') if channel.strip()]
        return channels or list(self.DEFAULT_CHANNELS)

    def _send_log(self, notification):
        self.logger.info(
            'Dispatched notification for plant=%s event=%s date=%s',
            notification.plant.name,
            notification.event.event_type,
            notification.event.date,
        )

    def _send_email(self, notification):
        recipient = os.getenv('NOTIFICATION_EMAIL_TO')
        if not recipient:
            raise RuntimeError('NOTIFICATION_EMAIL_TO is required for email channel')

        subject = f"[SmartGarden] {notification.event.event_type.title()} due for {notification.plant.name}"
        message = (
            f"Plant: {notification.plant.name}\n"
            f"Event: {notification.event.event_type}\n"
            f"Date: {notification.event.date}\n"
            f"Notes: {notification.event.notes or 'N/A'}\n"
        )
        send_mail(
            subject=subject,
            message=message,
            from_email=os.getenv('DEFAULT_FROM_EMAIL', 'noreply@smartgarden.local'),
            recipient_list=[recipient],
            fail_silently=False,
        )

    def _send_webhook(self, notification):
        webhook_url = os.getenv('NOTIFICATION_WEBHOOK_URL')
        if not webhook_url:
            raise RuntimeError('NOTIFICATION_WEBHOOK_URL is required for webhook channel')

        payload = {
            'notification_id': notification.id,
            'plant': notification.plant.name,
            'event_type': notification.event.event_type,
            'date': notification.event.date.isoformat(),
            'notes': notification.event.notes,
        }
        data = json.dumps(payload).encode('utf-8')
        req = urlrequest.Request(
            webhook_url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urlrequest.urlopen(req, timeout=10) as resp:
                status_code = resp.getcode()
        except urlerror.URLError as exc:
            raise RuntimeError(f'Webhook delivery failed: {exc}') from exc

        if status_code >= 400:
            raise RuntimeError(f'Webhook delivery returned status {status_code}')

    def _backoff_minutes(self, attempts):
        index = max(0, attempts - 1)
        if index >= len(self.RETRY_BACKOFF_MINUTES):
            return self.RETRY_BACKOFF_MINUTES[-1]
        return self.RETRY_BACKOFF_MINUTES[index]


class UpcomingNotificationScheduler:
    DEFAULT_HORIZON_DAYS = 2
    DEFAULT_DAILY_LIMIT = 12

    def __init__(self, *, start_date=None, horizon_days=DEFAULT_HORIZON_DAYS, daily_limit=DEFAULT_DAILY_LIMIT):
        self.start_date = start_date or timezone.now().date()
        self.horizon_days = max(1, int(horizon_days))
        self.daily_limit = max(1, int(daily_limit))

    def generate(self):
        planner = CareTaskPlanner(
            start_date=self.start_date,
            horizon_days=self.horizon_days,
            daily_limit=self.daily_limit,
        )
        tasks = planner.tasks_in_window()
        now = timezone.now()

        created_events = 0
        created_notifications = 0
        for task in tasks:
            event, event_created = CalendarEvent.objects.get_or_create(
                plant_id=task.plant_id,
                event_type=task.event_type,
                date=task.scheduled_date,
                defaults={'notes': 'Auto-generated by upcoming notification scheduler'},
            )
            if event_created:
                created_events += 1

            _, notification_created = Notification.objects.get_or_create(
                plant_id=task.plant_id,
                event=event,
                defaults={
                    'sent': False,
                    'attempts': 0,
                    'last_error': '',
                    'next_attempt_at': now,
                },
            )
            if notification_created:
                created_notifications += 1

        return {
            'tasks': len(tasks),
            'created_events': created_events,
            'created_notifications': created_notifications,
        }


class DeviceAutomationService:
    RECENT_SENSOR_HOURS = 3
    DUPLICATE_WINDOW_MINUTES = 30
    DEFAULT_SOIL_DRY_THRESHOLD = 400
    DEFAULT_LIGHT_LOW_THRESHOLD = 150
    DEFAULT_HUMIDITY_HIGH_THRESHOLD = 80.0

    def evaluate(self):
        now = timezone.now()
        cutoff = now - timedelta(hours=self.RECENT_SENSOR_HOURS)
        readings = (
            SensorReading.objects
            .select_related('device__garden')
            .filter(timestamp__gte=cutoff)
            .order_by('device_id', '-timestamp')
        )

        latest_by_device = {}
        for reading in readings:
            if reading.device_id not in latest_by_device:
                latest_by_device[reading.device_id] = reading

        created = 0
        for reading in latest_by_device.values():
            garden = reading.device.garden
            if not garden.automation_enabled:
                continue

            if (
                reading.soil_moisture is not None
                and reading.soil_moisture <= self._soil_dry_threshold(garden)
            ):
                created += self._queue_action(
                    device_id=reading.device_id,
                    action_type='water_pump_on',
                    reason=f"Soil moisture low ({reading.soil_moisture})",
                    payload={'soil_moisture': reading.soil_moisture},
                )

            if reading.light is not None and reading.light <= self._light_low_threshold(garden):
                created += self._queue_action(
                    device_id=reading.device_id,
                    action_type='grow_light_on',
                    reason=f"Light low ({reading.light})",
                    payload={'light': reading.light},
                )

            if (
                reading.humidity is not None
                and reading.humidity >= self._humidity_high_threshold(garden)
            ):
                created += self._queue_action(
                    device_id=reading.device_id,
                    action_type='ventilation_on',
                    reason=f"Humidity high ({reading.humidity})",
                    payload={'humidity': reading.humidity},
                )

        return {'devices_evaluated': len(latest_by_device), 'actions_created': created}

    def _queue_action(self, *, device_id, action_type, reason, payload):
        recent_cutoff = timezone.now() - timedelta(minutes=self.DUPLICATE_WINDOW_MINUTES)
        already_queued = DeviceAction.objects.filter(
            device_id=device_id,
            action_type=action_type,
            status='pending',
            created_at__gte=recent_cutoff,
        ).exists()
        if already_queued:
            return 0

        DeviceAction.objects.create(
            device_id=device_id,
            action_type=action_type,
            status='pending',
            reason=reason,
            payload=payload,
        )
        return 1

    def _soil_dry_threshold(self, garden):
        return garden.soil_moisture_dry_threshold or self.DEFAULT_SOIL_DRY_THRESHOLD

    def _light_low_threshold(self, garden):
        return garden.light_low_threshold or self.DEFAULT_LIGHT_LOW_THRESHOLD

    def _humidity_high_threshold(self, garden):
        return garden.humidity_high_threshold or self.DEFAULT_HUMIDITY_HIGH_THRESHOLD


class DeviceActionDispatcher:
    DEFAULT_BATCH_SIZE = 100
    DEFAULT_MAX_ATTEMPTS = 6
    RETRY_BACKOFF_MINUTES = (1, 5, 15, 60, 180, 720)

    def __init__(self, *, logger=None, max_attempts=DEFAULT_MAX_ATTEMPTS):
        self.logger = logger or logging.getLogger(__name__)
        self.max_attempts = max(1, int(max_attempts))

    def dispatch_pending(self, *, batch_size=DEFAULT_BATCH_SIZE):
        size = max(1, int(batch_size))
        now = timezone.now()
        pending = list(
            DeviceAction.objects
            .select_related('device')
            .filter(status='pending', attempts__lt=self.max_attempts, next_attempt_at__lte=now)
            .order_by('created_at')[:size]
        )

        executed_count = 0
        failed_count = 0
        for action in pending:
            try:
                self._dispatch(action)
                action.status = 'executed'
                action.executed_at = now
                action.last_error = ''
                executed_count += 1
            except Exception as exc:
                action.attempts += 1
                action.last_error = str(exc)[:1000]
                if action.attempts >= self.max_attempts:
                    action.status = 'failed'
                backoff_minutes = self._backoff_minutes(action.attempts)
                action.next_attempt_at = now + timedelta(minutes=backoff_minutes)
                failed_count += 1
                self.logger.warning(
                    'Device action dispatch failed id=%s attempt=%s status=%s error=%s',
                    action.id,
                    action.attempts,
                    action.status,
                    action.last_error,
                )

        if pending:
            DeviceAction.objects.bulk_update(
                pending,
                ['status', 'attempts', 'last_error', 'next_attempt_at', 'executed_at'],
            )

        return {
            'processed': len(pending),
            'executed': executed_count,
            'failed': failed_count,
        }

    def _dispatch(self, action):
        adapter = os.getenv('ACTUATOR_ADAPTER', 'log').strip().lower()
        if adapter == 'log':
            self._dispatch_log(action)
            return
        if adapter == 'webhook':
            self._dispatch_webhook(action)
            return
        raise RuntimeError(f'Unsupported ACTUATOR_ADAPTER: {adapter}')

    def _dispatch_log(self, action):
        self.logger.info(
            'Executed action device=%s type=%s payload=%s',
            action.device.device_id,
            action.action_type,
            action.payload,
        )

    def _dispatch_webhook(self, action):
        webhook_url = os.getenv('ACTUATOR_WEBHOOK_URL')
        if not webhook_url:
            raise RuntimeError('ACTUATOR_WEBHOOK_URL is required for webhook adapter')

        payload = {
            'action_id': action.id,
            'device_id': action.device.device_id,
            'action_type': action.action_type,
            'reason': action.reason,
            'payload': action.payload,
        }
        req = urlrequest.Request(
            webhook_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urlrequest.urlopen(req, timeout=10) as resp:
                status_code = resp.getcode()
        except urlerror.URLError as exc:
            raise RuntimeError(f'Actuator webhook failed: {exc}') from exc
        if status_code >= 400:
            raise RuntimeError(f'Actuator webhook returned status {status_code}')

    def _backoff_minutes(self, attempts):
        index = max(0, attempts - 1)
        if index >= len(self.RETRY_BACKOFF_MINUTES):
            return self.RETRY_BACKOFF_MINUTES[-1]
        return self.RETRY_BACKOFF_MINUTES[index]


class PestIncidentService:
    DEFAULT_HORIZON_DAYS = 3

    def schedule_followups(self, *, reference_date=None, horizon_days=DEFAULT_HORIZON_DAYS):
        today = reference_date or timezone.now().date()
        horizon_end = today + timedelta(days=max(0, int(horizon_days)))
        incidents = PestIncident.objects.select_related('plant', 'profile').filter(
            status__in=['open', 'monitoring'],
            next_follow_up_date__isnull=False,
            next_follow_up_date__gte=today,
            next_follow_up_date__lte=horizon_end,
        )

        created_events = 0
        created_notifications = 0
        for incident in incidents:
            profile_name = incident.profile.name if incident.profile else 'General'
            notes = f"Pest follow-up ({profile_name}): {incident.treatment_plan or incident.symptoms_observed or 'Check plant'}"
            event, event_created = CalendarEvent.objects.get_or_create(
                plant=incident.plant,
                event_type='other',
                date=incident.next_follow_up_date,
                defaults={'notes': notes},
            )
            if event_created:
                created_events += 1
            _, notif_created = Notification.objects.get_or_create(
                plant=incident.plant,
                event=event,
                defaults={
                    'sent': False,
                    'attempts': 0,
                    'last_error': '',
                    'next_attempt_at': timezone.now(),
                },
            )
            if notif_created:
                created_notifications += 1

        return {
            'incidents_considered': incidents.count(),
            'created_events': created_events,
            'created_notifications': created_notifications,
        }
