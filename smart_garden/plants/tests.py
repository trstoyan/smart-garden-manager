import json
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from . import views
from .models import (
    CalendarEvent,
    Device,
    DeviceAction,
    Garden,
    Notification,
    PestDiseaseProfile,
    PestIncident,
    Plant,
    PlantCareRule,
    PlantGroup,
    PlantStatusLog,
    PlantType,
    SensorIngestRecord,
    SensorReading,
)
from .services import (
    CareTask,
    CareTaskPlanner,
    DeviceActionDispatcher,
    DeviceAutomationService,
    HeuristicTaskOptimizer,
    NotificationDispatcher,
    PestIncidentService,
    UpcomingNotificationScheduler,
)


class PlantModelTests(TestCase):
    def setUp(self):
        self.plant_type = PlantType.objects.create(name='Type')
        self.garden = Garden.objects.create(name='Garden')
        self.group = PlantGroup.objects.create(name='Group', plant_type=self.plant_type, garden=self.garden)

    def test_get_current_season(self):
        test_dates = {
            'spring': timezone.datetime(2025, 4, 15),
            'summer': timezone.datetime(2025, 7, 15),
            'fall': timezone.datetime(2025, 10, 15),
            'winter': timezone.datetime(2025, 1, 15),
        }
        for expected, mock_date in test_dates.items():
            with mock.patch('plants.models.timezone.now', return_value=mock_date):
                self.assertEqual(Plant.get_current_season(), expected)

    def test_next_dates_default(self):
        plant = Plant.objects.create(name='Plant', group=self.group)
        mock_dt = timezone.datetime(2025, 1, 1)
        with mock.patch('plants.models.timezone.now', return_value=mock_dt):
            self.assertEqual(plant.get_next_watering_date(), mock_dt.date() + timezone.timedelta(days=7))
            self.assertEqual(plant.get_next_fertilization_date(), mock_dt.date() + timezone.timedelta(days=30))
            self.assertEqual(plant.get_next_repotting_date(), mock_dt.date() + timezone.timedelta(days=180))


class CareTaskPlannerTests(TestCase):
    def setUp(self):
        self.today = timezone.datetime(2025, 1, 15).date()
        self.garden = Garden.objects.create(name='Garden')
        self.plant_type = PlantType.objects.create(
            name='Type',
            default_watering_interval_days=7,
            default_fertilization_interval_days=30,
            default_repotting_interval_days=180,
        )
        self.group = PlantGroup.objects.create(name='Group', plant_type=self.plant_type, garden=self.garden)

    def _create_plant(self, name, *, last_watered, last_fertilized, last_repotted=None):
        return Plant.objects.create(
            name=name,
            group=self.group,
            last_watered=last_watered,
            last_fertilized=last_fertilized,
            last_repotted=last_repotted,
        )

    def test_overdue_tasks_are_pinned_to_start_date(self):
        plant = self._create_plant(
            'Overdue Plant',
            last_watered=self.today - timezone.timedelta(days=10),
            last_fertilized=self.today - timezone.timedelta(days=5),
            last_repotted=self.today - timezone.timedelta(days=500),
        )
        planner = CareTaskPlanner(start_date=self.today, horizon_days=7, daily_limit=3)
        tasks = planner.tasks_in_window(plants=[plant])
        water_task = next(task for task in tasks if task.event_type == 'water')
        self.assertTrue(water_task.is_overdue)
        self.assertEqual(water_task.scheduled_date, self.today)
        self.assertEqual(water_task.days_overdue, 3)

    def test_daily_limit_balances_tasks(self):
        plant1 = self._create_plant(
            'Plant 1',
            last_watered=self.today - timezone.timedelta(days=7),
            last_fertilized=self.today - timezone.timedelta(days=30),
            last_repotted=self.today - timezone.timedelta(days=180),
        )
        plant2 = self._create_plant(
            'Plant 2',
            last_watered=self.today - timezone.timedelta(days=7),
            last_fertilized=self.today - timezone.timedelta(days=30),
            last_repotted=self.today - timezone.timedelta(days=180),
        )
        planner = CareTaskPlanner(start_date=self.today, horizon_days=7, daily_limit=2)
        tasks = planner.tasks_in_window(plants=[plant1, plant2])

        tasks_by_day = {}
        for task in tasks:
            tasks_by_day.setdefault(task.scheduled_date, 0)
            tasks_by_day[task.scheduled_date] += 1

        self.assertEqual(len(tasks), 6)
        self.assertTrue(all(count <= 2 for count in tasks_by_day.values()))

    def test_watering_is_delayed_when_soil_is_wet(self):
        device = Device.objects.create(device_id='dev-1', garden=self.garden)
        SensorReading.objects.create(device=device, soil_moisture=800)
        plant = self._create_plant(
            'Wet Soil Plant',
            last_watered=self.today - timezone.timedelta(days=7),
            last_fertilized=self.today - timezone.timedelta(days=1),
        )

        planner = CareTaskPlanner(start_date=self.today, horizon_days=7, daily_limit=3)
        tasks = planner.tasks_in_window(plants=[plant])
        water_task = next(task for task in tasks if task.event_type == 'water')

        self.assertEqual(water_task.scheduled_date, self.today + timezone.timedelta(days=1))
        self.assertIn('soil moisture', water_task.adjustment_reason.lower())

    def test_watering_is_accelerated_when_soil_is_dry(self):
        self.garden.soil_moisture_dry_threshold = 450
        self.garden.save(update_fields=['soil_moisture_dry_threshold'])
        device = Device.objects.create(device_id='dev-dry', garden=self.garden)
        SensorReading.objects.create(device=device, soil_moisture=420)
        plant = self._create_plant(
            'Dry Soil Plant',
            last_watered=self.today - timezone.timedelta(days=5),
            last_fertilized=self.today - timezone.timedelta(days=1),
        )
        planner = CareTaskPlanner(start_date=self.today, horizon_days=7, daily_limit=3)
        tasks = planner.tasks_in_window(plants=[plant])
        water_task = next(task for task in tasks if task.event_type == 'water')
        self.assertEqual(water_task.scheduled_date, self.today + timezone.timedelta(days=1))
        self.assertIn('accelerated', (water_task.adjustment_reason or '').lower())

    def test_fertilization_can_require_pre_watering_gap(self):
        self.plant_type.default_requires_pre_watering = True
        self.plant_type.default_pre_fertilization_water_gap_days = 2
        self.plant_type.save(update_fields=['default_requires_pre_watering', 'default_pre_fertilization_water_gap_days'])
        plant = self._create_plant(
            'Gap Plant',
            last_watered=self.today - timezone.timedelta(days=8),
            last_fertilized=self.today - timezone.timedelta(days=30),
        )
        planner = CareTaskPlanner(start_date=self.today, horizon_days=7, daily_limit=10)
        tasks = planner.tasks_in_window(plants=[plant])
        water_task = next(task for task in tasks if task.event_type == 'water')
        fert_task = next(task for task in tasks if task.event_type == 'fertilize')
        self.assertGreaterEqual(fert_task.scheduled_date, water_task.scheduled_date + timezone.timedelta(days=2))

    def test_container_and_trend_adjustment_can_accelerate_watering(self):
        today = self.today
        neutral_type = PlantType.objects.create(
            name='Neutral Type',
            default_watering_interval_days=7,
            moisture_preference='balanced',
            default_substrate_type='soil',
        )
        sensitive_type = PlantType.objects.create(
            name='Sensitive Type',
            default_watering_interval_days=7,
            moisture_preference='moist',
            default_substrate_type='coco',
        )
        neutral_group = PlantGroup.objects.create(name='Neutral', plant_type=neutral_type, garden=self.garden)
        sensitive_group = PlantGroup.objects.create(name='Sensitive', plant_type=sensitive_type, garden=self.garden)

        neutral_plant = Plant.objects.create(
            name='Neutral Plant',
            group=neutral_group,
            last_watered=today - timezone.timedelta(days=3),
            substrate_type='soil',
            pot_volume_liters=20,
            drainage_class=2,
        )
        sensitive_plant = Plant.objects.create(
            name='Sensitive Plant',
            group=sensitive_group,
            last_watered=today - timezone.timedelta(days=3),
            substrate_type='coco',
            pot_volume_liters=1.2,
            drainage_class=5,
        )

        device = Device.objects.create(device_id='trend-dev', garden=self.garden)
        old = SensorReading.objects.create(device=device, soil_moisture=700)
        new = SensorReading.objects.create(device=device, soil_moisture=620)
        SensorReading.objects.filter(id=old.id).update(timestamp=timezone.now() - timezone.timedelta(hours=2))
        SensorReading.objects.filter(id=new.id).update(timestamp=timezone.now() - timezone.timedelta(hours=1))

        planner = CareTaskPlanner(start_date=today, horizon_days=10, daily_limit=20)
        tasks = planner.tasks_in_window(plants=[neutral_plant, sensitive_plant])
        neutral_water = next(task for task in tasks if task.plant_name == 'Neutral Plant' and task.event_type == 'water')
        sensitive_water = next(task for task in tasks if task.plant_name == 'Sensitive Plant' and task.event_type == 'water')

        self.assertLessEqual(sensitive_water.scheduled_date, neutral_water.scheduled_date - timezone.timedelta(days=1))
        self.assertIn('Container/profile adjust', sensitive_water.adjustment_reason or '')

    def test_zone_profile_can_shift_watering(self):
        self.garden.usda_hardiness_zone = '12a'
        self.garden.save(update_fields=['usda_hardiness_zone'])
        zone_type = PlantType.objects.create(
            name='Zone Type',
            default_watering_interval_days=7,
            preferred_usda_zone_max=9,
        )
        control_type = PlantType.objects.create(name='Control Type', default_watering_interval_days=7)
        zone_group = PlantGroup.objects.create(name='Zone Group', plant_type=zone_type, garden=self.garden)
        control_group = PlantGroup.objects.create(name='Control Group', plant_type=control_type, garden=self.garden)
        zone_plant = Plant.objects.create(
            name='Zone Plant',
            group=zone_group,
            location='outdoor',
            last_watered=self.today - timezone.timedelta(days=4),
        )
        control_plant = Plant.objects.create(
            name='Control Plant',
            group=control_group,
            location='outdoor',
            last_watered=self.today - timezone.timedelta(days=4),
        )
        planner = CareTaskPlanner(start_date=self.today, horizon_days=10, daily_limit=20)
        tasks = planner.tasks_in_window(plants=[zone_plant, control_plant])
        zone_water = next(task for task in tasks if task.plant_name == 'Zone Plant' and task.event_type == 'water')
        control_water = next(task for task in tasks if task.plant_name == 'Control Plant' and task.event_type == 'water')
        self.assertLessEqual(zone_water.scheduled_date, control_water.scheduled_date - timezone.timedelta(days=1))

    def test_group_rule_overrides_watering_interval(self):
        plant = self._create_plant(
            'Group Rule Plant',
            last_watered=self.today - timezone.timedelta(days=1),
            last_fertilized=self.today - timezone.timedelta(days=2),
        )
        PlantCareRule.objects.create(
            name='Group Fast Water',
            scope='group',
            group=self.group,
            watering_interval_days=2,
            priority=50,
        )
        planner = CareTaskPlanner(start_date=self.today, horizon_days=7, daily_limit=10)
        tasks = planner.tasks_in_window(plants=[plant])
        water_task = next(task for task in tasks if task.event_type == 'water')
        self.assertEqual(water_task.due_date, self.today + timezone.timedelta(days=1))

    def test_plant_rule_wins_over_group_rule(self):
        plant = self._create_plant(
            'Plant Rule Plant',
            last_watered=self.today - timezone.timedelta(days=1),
            last_fertilized=self.today - timezone.timedelta(days=2),
        )
        PlantCareRule.objects.create(
            name='Group Rule',
            scope='group',
            group=self.group,
            watering_interval_days=2,
            priority=10,
        )
        PlantCareRule.objects.create(
            name='Plant Rule',
            scope='plant',
            plant=plant,
            watering_interval_days=5,
            priority=200,
        )
        planner = CareTaskPlanner(start_date=self.today, horizon_days=10, daily_limit=10)
        tasks = planner.tasks_in_window(plants=[plant])
        water_task = next(task for task in tasks if task.event_type == 'water')
        self.assertEqual(water_task.due_date, self.today + timezone.timedelta(days=4))


class TaskCompletionViewTests(TestCase):
    def setUp(self):
        self.today = timezone.datetime(2025, 2, 1).date()
        garden = Garden.objects.create(name='Garden')
        plant_type = PlantType.objects.create(name='Type')
        group = PlantGroup.objects.create(name='Group', plant_type=plant_type, garden=garden)
        self.plant = Plant.objects.create(name='Plant', group=group)

    def test_complete_repot_task_updates_plant_and_status_log(self):
        response = self.client.post(
            reverse('plants:complete_task'),
            data={
                'plant_id': self.plant.id,
                'event_type': 'repot',
                'scheduled_date': self.today.isoformat(),
                'days': 14,
                'daily_limit': 6,
            },
        )
        self.assertEqual(response.status_code, 302)

        self.plant.refresh_from_db()
        self.assertEqual(self.plant.last_repotted, self.today)
        self.assertTrue(PlantStatusLog.objects.filter(plant=self.plant, status='repotted').exists())


class WebCrudViewTests(TestCase):
    def setUp(self):
        self.garden = Garden.objects.create(name='Web Garden')
        self.plant_type = PlantType.objects.create(name='Web Type')
        self.group = PlantGroup.objects.create(name='Web Group', plant_type=self.plant_type, garden=self.garden)
        self.plant = Plant.objects.create(name='Web Plant', group=self.group)
        self.rule = PlantCareRule.objects.create(name='Web Rule', scope='group', group=self.group, priority=10)

    def test_plant_detail_update_and_delete(self):
        detail_url = reverse('plants:plant_detail', args=[self.plant.id])
        update_response = self.client.post(
            detail_url,
            data={
                'name': 'Web Plant Updated',
                'group': self.group.id,
                'location': 'indoor',
            },
        )
        self.assertEqual(update_response.status_code, 302)
        self.plant.refresh_from_db()
        self.assertEqual(self.plant.name, 'Web Plant Updated')

        delete_response = self.client.post(reverse('plants:plant_delete', args=[self.plant.id]))
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Plant.objects.filter(id=self.plant.id).exists())

    def test_rule_detail_update_and_delete(self):
        detail_url = reverse('plants:rule_detail', args=[self.rule.id])
        update_response = self.client.post(
            detail_url,
            data={
                'name': 'Web Rule Updated',
                'scope': 'group',
                'group': self.group.id,
                'plant': '',
                'enabled': 'on',
                'priority': 5,
                'watering_interval_days': 3,
                'fertilization_interval_days': '',
                'repotting_interval_days': '',
                'requires_pre_watering': '',
                'pre_fertilization_water_gap_days': '',
                'soil_moisture_wet_threshold': '',
                'soil_moisture_dry_threshold': '',
                'notes': '',
            },
        )
        self.assertEqual(update_response.status_code, 302)
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.name, 'Web Rule Updated')

        delete_response = self.client.post(reverse('plants:rule_delete', args=[self.rule.id]))
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(PlantCareRule.objects.filter(id=self.rule.id).exists())


class WebSetupCrudTests(TestCase):
    def test_garden_type_group_crud_via_webui_posts(self):
        garden_create = self.client.post(
            reverse('plants:garden_create'),
            data={'name': 'UI Garden', 'location': 'Patio'},
        )
        self.assertEqual(garden_create.status_code, 302)
        garden = Garden.objects.get(name='UI Garden')

        type_create = self.client.post(
            reverse('plants:plant_type_create'),
            data={
                'name': 'UI Type',
                'scientific_name': '',
                'cultivar': '',
                'profile_notes': '',
                'preferred_usda_zone_min': '',
                'preferred_usda_zone_max': '',
                'moisture_preference': 'balanced',
                'default_substrate_type': 'soil',
                'default_watering_interval_days': 7,
                'default_water_type': 'plain',
                'default_fertilization_interval_days': 30,
                'default_repotting_interval_days': 180,
                'default_requires_pre_watering': '',
                'default_pre_fertilization_water_gap_days': 1,
                'default_spring_watering_interval_days': '',
                'default_summer_watering_interval_days': '',
                'default_fall_watering_interval_days': '',
                'default_winter_watering_interval_days': '',
                'default_indoor_watering_interval_days': '',
                'default_outdoor_watering_interval_days': '',
            },
        )
        self.assertEqual(type_create.status_code, 302)
        plant_type = PlantType.objects.get(name='UI Type')

        group_create = self.client.post(
            reverse('plants:plant_group_create'),
            data={'name': 'UI Group', 'garden': garden.id, 'plant_type': plant_type.id},
        )
        self.assertEqual(group_create.status_code, 302)
        group = PlantGroup.objects.get(name='UI Group')

        group_update = self.client.post(
            reverse('plants:plant_group_detail', args=[group.id]),
            data={'name': 'UI Group Updated', 'garden': garden.id, 'plant_type': plant_type.id},
        )
        self.assertEqual(group_update.status_code, 302)
        group.refresh_from_db()
        self.assertEqual(group.name, 'UI Group Updated')

        group_delete = self.client.post(reverse('plants:plant_group_delete', args=[group.id]))
        self.assertEqual(group_delete.status_code, 302)
        self.assertFalse(PlantGroup.objects.filter(id=group.id).exists())

    def test_onboarding_wizard_post_flow(self):
        step1 = self.client.post(
            reverse('plants:onboarding_wizard') + '?step=1',
            data={'name': 'Wizard Garden', 'location': 'Balcony'},
        )
        self.assertEqual(step1.status_code, 302)

        step2 = self.client.post(
            reverse('plants:onboarding_wizard') + '?step=2',
            data={
                'name': 'Wizard Type',
                'moisture_preference': 'balanced',
                'default_substrate_type': 'soil',
                'default_watering_interval_days': 7,
                'default_fertilization_interval_days': 30,
                'default_repotting_interval_days': 180,
            },
        )
        self.assertEqual(step2.status_code, 302)
        garden = Garden.objects.get(name='Wizard Garden')
        plant_type = PlantType.objects.get(name='Wizard Type')

        step3 = self.client.post(
            reverse('plants:onboarding_wizard') + '?step=3',
            data={'name': 'Wizard Group', 'garden': garden.id, 'plant_type': plant_type.id},
        )
        self.assertEqual(step3.status_code, 302)
        group = PlantGroup.objects.get(name='Wizard Group')

        step4 = self.client.post(
            reverse('plants:onboarding_wizard') + '?step=4',
            data={'name': 'Wizard Plant', 'group': group.id, 'location': 'indoor'},
        )
        self.assertEqual(step4.status_code, 302)
        self.assertTrue(Plant.objects.filter(name='Wizard Plant').exists())

        step5 = self.client.post(
            reverse('plants:onboarding_wizard') + '?step=5',
            data={'skip': '1'},
        )
        self.assertEqual(step5.status_code, 302)

    def test_setup_center_starter_pack(self):
        response = self.client.post(
            reverse('plants:setup_center'),
            data={'starter_pack': 'balcony_herbs'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Garden.objects.filter(name__startswith='Balcony Garden').exists())
        self.assertTrue(PlantType.objects.filter(name__startswith='Herbs').exists())
        self.assertTrue(PlantGroup.objects.filter(name__startswith='Kitchen Herbs').exists())
        self.assertTrue(Plant.objects.filter(name__startswith='Basil').exists())


class WebOperationsFlowTests(TestCase):
    def setUp(self):
        self.garden = Garden.objects.create(name='Ops Garden')
        self.plant_type = PlantType.objects.create(name='Ops Type')
        self.group = PlantGroup.objects.create(name='Ops Group', plant_type=self.plant_type, garden=self.garden)
        self.plant = Plant.objects.create(name='Ops Plant', group=self.group)

    def test_device_create_update_rotate_delete(self):
        create = self.client.post(
            reverse('plants:devices_center'),
            data={'device_id': 'ops-dev-1', 'garden': self.garden.id, 'description': 'Pump controller'},
        )
        self.assertEqual(create.status_code, 302)
        device = Device.objects.get(device_id='ops-dev-1')
        old_key = device.api_key

        update = self.client.post(
            reverse('plants:device_detail', args=[device.id]),
            data={'device_id': 'ops-dev-1-renamed', 'garden': self.garden.id, 'description': 'Updated'},
        )
        self.assertEqual(update.status_code, 302)
        device.refresh_from_db()
        self.assertEqual(device.device_id, 'ops-dev-1-renamed')

        rotate = self.client.post(reverse('plants:device_rotate_key', args=[device.id]))
        self.assertEqual(rotate.status_code, 302)
        device.refresh_from_db()
        self.assertNotEqual(device.api_key, old_key)

        delete = self.client.post(reverse('plants:device_delete', args=[device.id]))
        self.assertEqual(delete.status_code, 302)
        self.assertFalse(Device.objects.filter(id=device.id).exists())

    def test_notifications_process_and_retry(self):
        event = CalendarEvent.objects.create(plant=self.plant, event_type='water', date=timezone.now().date())
        notification = Notification.objects.create(
            plant=self.plant,
            event=event,
            sent=False,
            next_attempt_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        process = self.client.post(
            reverse('plants:process_notifications'),
            data={'batch_size': 10, 'max_attempts': 6},
        )
        self.assertEqual(process.status_code, 302)
        notification.refresh_from_db()
        self.assertTrue(notification.sent)

        notification.sent = False
        notification.attempts = 3
        notification.last_error = 'provider error'
        notification.next_attempt_at = None
        notification.save(update_fields=['sent', 'attempts', 'last_error', 'next_attempt_at'])
        retry = self.client.post(reverse('plants:retry_notification', args=[notification.id]))
        self.assertEqual(retry.status_code, 302)
        notification.refresh_from_db()
        self.assertEqual(notification.attempts, 0)
        self.assertEqual(notification.last_error, '')
        self.assertFalse(notification.sent)
        self.assertIsNotNone(notification.next_attempt_at)

    def test_notifications_send_telegram_test(self):
        with mock.patch('plants.views.NotificationDispatcher.send_telegram_test_message') as mocked_sender:
            response = self.client.post(reverse('plants:test_telegram_notification'))
        self.assertEqual(response.status_code, 302)
        mocked_sender.assert_called_once_with()

    def test_notifications_send_telegram_test_error(self):
        with mock.patch(
            'plants.views.NotificationDispatcher.send_telegram_test_message',
            side_effect=RuntimeError('invalid token'),
        ) as mocked_sender:
            response = self.client.post(reverse('plants:test_telegram_notification'))
        self.assertEqual(response.status_code, 302)
        mocked_sender.assert_called_once_with()

    def test_device_actions_evaluate_process_and_retry(self):
        device = Device.objects.create(device_id='ops-action-dev', garden=self.garden)
        SensorReading.objects.create(device=device, soil_moisture=300, light=90, humidity=85.0)

        evaluate = self.client.post(reverse('plants:evaluate_automations'))
        self.assertEqual(evaluate.status_code, 302)
        self.assertTrue(DeviceAction.objects.filter(device=device).exists())

        process = self.client.post(
            reverse('plants:process_device_actions'),
            data={'batch_size': 100, 'max_attempts': 6},
        )
        self.assertEqual(process.status_code, 302)

        action = DeviceAction.objects.create(
            device=device,
            action_type='custom',
            status='failed',
            attempts=4,
            last_error='timeout',
        )
        retry = self.client.post(reverse('plants:retry_device_action', args=[action.id]))
        self.assertEqual(retry.status_code, 302)
        action.refresh_from_db()
        self.assertEqual(action.status, 'pending')
        self.assertEqual(action.attempts, 0)
        self.assertEqual(action.last_error, '')


class WebRuleCoverageViewTests(TestCase):
    def setUp(self):
        garden = Garden.objects.create(name='Coverage Garden')
        plant_type = PlantType.objects.create(name='Coverage Type')
        covered_group = PlantGroup.objects.create(name='Covered Group', plant_type=plant_type, garden=garden)
        uncovered_group = PlantGroup.objects.create(name='Uncovered Group', plant_type=plant_type, garden=garden)

        self.covered_plant = Plant.objects.create(name='Covered Plant', group=covered_group)
        self.missing_plant = Plant.objects.create(name='Missing Plant', group=uncovered_group)
        PlantCareRule.objects.create(name='Covered Rule', scope='group', group=covered_group, enabled=True)

    def test_rule_coverage_view_shows_missing_and_covered_sections(self):
        request = RequestFactory().get(reverse('plants:rule_coverage'))
        with mock.patch('plants.views.render', return_value=HttpResponse('ok')) as mock_render:
            response = views.rule_coverage_view(request)

        self.assertEqual(response.status_code, 200)
        _, _, context = mock_render.call_args.args
        self.assertEqual(context['total_plants'], 2)
        self.assertEqual(context['plants_covered'], 1)
        self.assertEqual(context['plants_missing'], 1)
        self.assertEqual(context['groups_without_rule'], 1)
        self.assertEqual(context['missing_plants'][0]['plant'].name, 'Missing Plant')


class SensorReadingIngestApiTests(TestCase):
    def setUp(self):
        self.garden = Garden.objects.create(name='Garden')
        self.device = Device.objects.create(device_id='esp32-1', garden=self.garden)
        self.url = reverse('plants:sensor_data_ingest')

    def test_ingest_accepts_valid_key_and_payload(self):
        payload = {'device_id': self.device.device_id, 'temperature': 23.5, 'soil_moisture': 550}
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_DEVICE_KEY=self.device.api_key,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(SensorReading.objects.count(), 1)

    def test_ingest_rejects_invalid_key(self):
        payload = {'device_id': self.device.device_id, 'humidity': 50.0}
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_DEVICE_KEY='bad-key',
        )
        self.assertEqual(response.status_code, 401)

    def test_ingest_idempotency_key_reuses_existing_reading(self):
        payload = {
            'device_id': self.device.device_id,
            'temperature': 23.5,
            'soil_moisture': 550,
        }
        first = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_DEVICE_KEY=self.device.api_key,
            HTTP_X_IDEMPOTENCY_KEY='sample-1',
        )
        second = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_DEVICE_KEY=self.device.api_key,
            HTTP_X_IDEMPOTENCY_KEY='sample-1',
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()['reused'])
        self.assertEqual(SensorReading.objects.count(), 1)
        self.assertEqual(SensorIngestRecord.objects.count(), 1)
        self.assertEqual(first.json()['reading_id'], second.json()['reading_id'])


class NotificationPipelineTests(TestCase):
    def setUp(self):
        plant_type = PlantType.objects.create(name='Type')
        garden = Garden.objects.create(name='Garden')
        group = PlantGroup.objects.create(name='Group', plant_type=plant_type, garden=garden)
        self.plant = Plant.objects.create(name='Plant', group=group)
        self.event = CalendarEvent.objects.create(plant=self.plant, event_type='water', date=timezone.now().date())
        self.notification = Notification.objects.create(
            plant=self.plant,
            event=self.event,
            sent=False,
            next_attempt_at=timezone.now() - timezone.timedelta(minutes=1),
        )

    def test_dispatch_success_marks_sent(self):
        out = StringIO()
        call_command('process_notifications', batch_size=10, stdout=out)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.sent)
        self.assertIn('1 sent', out.getvalue())

    def test_dispatch_failure_sets_backoff(self):
        def failing_sender(_notification):
            raise RuntimeError('provider down')

        dispatcher = NotificationDispatcher(sender=failing_sender, max_attempts=3)
        result = dispatcher.dispatch_pending(batch_size=10)
        self.notification.refresh_from_db()
        self.assertEqual(result['failed'], 1)
        self.assertEqual(self.notification.attempts, 1)
        self.assertIn('provider down', self.notification.last_error)
        self.assertIsNotNone(self.notification.next_attempt_at)

    def test_telegram_channel_requires_credentials(self):
        with mock.patch.dict('os.environ', {'NOTIFICATION_CHANNELS': 'telegram'}, clear=False):
            dispatcher = NotificationDispatcher(max_attempts=3)
            result = dispatcher.dispatch_pending(batch_size=10)

        self.notification.refresh_from_db()
        self.assertEqual(result['failed'], 1)
        self.assertIn('TELEGRAM_BOT_TOKEN', self.notification.last_error)
        self.assertEqual(self.notification.attempts, 1)

    def test_telegram_channel_success_marks_sent(self):
        response = mock.MagicMock()
        response.getcode.return_value = 200
        response.read.return_value = b'{"ok": true, "result": {"message_id": 123}}'

        cm = mock.MagicMock()
        cm.__enter__.return_value = response
        cm.__exit__.return_value = False

        with mock.patch.dict(
            'os.environ',
            {
                'NOTIFICATION_CHANNELS': 'telegram',
                'TELEGRAM_BOT_TOKEN': 'test-token',
                'TELEGRAM_CHAT_ID': '123456',
            },
            clear=False,
        ), mock.patch('plants.services.urlrequest.urlopen', return_value=cm) as mocked_urlopen:
            dispatcher = NotificationDispatcher(max_attempts=3)
            result = dispatcher.dispatch_pending(batch_size=10)

        self.notification.refresh_from_db()
        self.assertEqual(result['sent'], 1)
        self.assertTrue(self.notification.sent)
        self.assertEqual(mocked_urlopen.call_count, 1)
        request = mocked_urlopen.call_args[0][0]
        self.assertIn('/sendMessage', request.full_url)

    def test_generate_upcoming_notifications_is_idempotent(self):
        self.plant.last_watered = timezone.now().date() - timezone.timedelta(days=7)
        self.plant.last_fertilized = timezone.now().date() - timezone.timedelta(days=30)
        self.plant.last_repotted = timezone.now().date() - timezone.timedelta(days=180)
        self.plant.save(update_fields=['last_watered', 'last_fertilized', 'last_repotted'])

        scheduler = UpcomingNotificationScheduler(horizon_days=2, daily_limit=12)
        first = scheduler.generate()
        second = scheduler.generate()
        self.assertGreaterEqual(first['created_notifications'], 1)
        self.assertEqual(second['created_notifications'], 0)


class AutomationTests(TestCase):
    def setUp(self):
        self.garden = Garden.objects.create(
            name='Garden',
            soil_moisture_dry_threshold=450,
            light_low_threshold=120,
            humidity_high_threshold=75.0,
        )
        self.device = Device.objects.create(device_id='dev-1', garden=self.garden)

    def test_automation_service_creates_actions(self):
        SensorReading.objects.create(device=self.device, soil_moisture=400, light=100, humidity=80.0)
        result = DeviceAutomationService().evaluate()
        self.assertEqual(result['devices_evaluated'], 1)
        self.assertGreaterEqual(result['actions_created'], 3)
        self.assertTrue(DeviceAction.objects.filter(device=self.device, action_type='water_pump_on').exists())

    def test_evaluate_automation_command(self):
        SensorReading.objects.create(device=self.device, soil_moisture=300)
        out = StringIO()
        call_command('evaluate_automations', stdout=out)
        self.assertIn('created', out.getvalue())

    def test_device_action_dispatcher_success(self):
        DeviceAction.objects.create(
            device=self.device,
            action_type='water_pump_on',
            status='pending',
            next_attempt_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        result = DeviceActionDispatcher(max_attempts=2).dispatch_pending(batch_size=10)
        action = DeviceAction.objects.get(device=self.device, action_type='water_pump_on')
        self.assertEqual(result['processed'], 1)
        self.assertEqual(result['executed'], 1)
        self.assertEqual(action.status, 'executed')
        self.assertIsNotNone(action.executed_at)

    def test_device_action_dispatcher_retry_then_fail(self):
        action = DeviceAction.objects.create(
            device=self.device,
            action_type='custom',
            status='pending',
            next_attempt_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        with mock.patch.dict('os.environ', {'ACTUATOR_ADAPTER': 'unsupported'}):
            first = DeviceActionDispatcher(max_attempts=2).dispatch_pending(batch_size=10)
            self.assertEqual(first['failed'], 1)
            action.refresh_from_db()
            self.assertEqual(action.status, 'pending')
            self.assertEqual(action.attempts, 1)
            self.assertIn('Unsupported ACTUATOR_ADAPTER', action.last_error)
            action.next_attempt_at = timezone.now() - timezone.timedelta(minutes=1)
            action.save(update_fields=['next_attempt_at'])

            second = DeviceActionDispatcher(max_attempts=2).dispatch_pending(batch_size=10)
            self.assertEqual(second['failed'], 1)
            action.refresh_from_db()
            self.assertEqual(action.status, 'failed')
            self.assertEqual(action.attempts, 2)

    def test_process_device_actions_command(self):
        DeviceAction.objects.create(
            device=self.device,
            action_type='grow_light_on',
            status='pending',
            next_attempt_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        out = StringIO()
        call_command('process_device_actions', batch_size=10, stdout=out)
        self.assertIn('executed', out.getvalue())


class ApiSurfaceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='apiuser', password='pass1234')
        self.client.login(username='apiuser', password='pass1234')

    def test_garden_crud_api(self):
        create_resp = self.client.post(
            '/api/gardens/',
            data=json.dumps({'name': 'API Garden', 'location': 'Zone A'}),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        list_resp = self.client.get('/api/gardens/')
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.json()['count'], 1)

    def test_care_rule_crud_api(self):
        garden = Garden.objects.create(name='Rule Garden')
        plant_type = PlantType.objects.create(name='Rule Type')
        group = PlantGroup.objects.create(name='Rule Group', plant_type=plant_type, garden=garden)
        create_resp = self.client.post(
            '/api/care-rules/',
            data=json.dumps({
                'name': 'Group Moisture Rule',
                'scope': 'group',
                'group': group.id,
                'priority': 10,
                'watering_interval_days': 3,
                'soil_moisture_dry_threshold': 470,
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        list_resp = self.client.get('/api/care-rules/')
        self.assertEqual(list_resp.status_code, 200)
        self.assertGreaterEqual(list_resp.json()['count'], 1)

    def test_dashboard_summary_api(self):
        resp = self.client.get(reverse('plants:dashboard_summary_api'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('plants', resp.json())

    def test_device_action_dispatch_api(self):
        garden = Garden.objects.create(name='Dispatch Garden')
        device = Device.objects.create(device_id='dispatch-1', garden=garden)
        DeviceAction.objects.create(
            device=device,
            action_type='water_pump_on',
            status='pending',
            next_attempt_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        response = self.client.post(
            reverse('plants:device_action_dispatch_api'),
            data=json.dumps({'batch_size': 10, 'max_attempts': 3}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('processed', response.json())

    def test_openapi_schema_endpoint(self):
        resp = self.client.get('/api/schema/')
        self.assertEqual(resp.status_code, 200)

    def test_ai_assistant_coming_soon_api(self):
        resp = self.client.get(reverse('plants:ai_assistant_api'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'coming_soon')

    def test_pest_incident_create_uses_profile_defaults(self):
        garden = Garden.objects.create(name='Incident Garden')
        plant_type = PlantType.objects.create(name='Incident Type')
        group = PlantGroup.objects.create(name='Incident Group', plant_type=plant_type, garden=garden)
        plant = Plant.objects.create(name='Incident Plant', group=group)
        profile = PestDiseaseProfile.objects.create(
            name='Aphids',
            profile_type='pest',
            symptoms='Sticky leaves',
            default_treatment_plan='Apply neem oil weekly',
            follow_up_interval_days=4,
        )
        payload = {
            'plant': plant.id,
            'profile': profile.id,
            'status': 'open',
            'severity': 'medium',
            'detected_on': timezone.now().date().isoformat(),
            'symptoms_observed': 'Small bugs on stem',
        }
        response = self.client.post('/api/pest-incidents/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        incident = PestIncident.objects.get(id=response.json()['id'])
        self.assertEqual(incident.treatment_plan, 'Apply neem oil weekly')
        self.assertIsNotNone(incident.next_follow_up_date)

    def test_pest_followup_schedule_endpoint(self):
        garden = Garden.objects.create(name='Followup Garden')
        plant_type = PlantType.objects.create(name='Followup Type')
        group = PlantGroup.objects.create(name='Followup Group', plant_type=plant_type, garden=garden)
        plant = Plant.objects.create(name='Followup Plant', group=group)
        incident = PestIncident.objects.create(
            plant=plant,
            status='open',
            severity='high',
            detected_on=timezone.now().date(),
            next_follow_up_date=timezone.now().date() + timezone.timedelta(days=1),
            symptoms_observed='Spots on leaves',
        )
        response = self.client.post(
            reverse('plants:pest_followup_schedule_api'),
            data=json.dumps({'days': 2}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CalendarEvent.objects.filter(plant=plant, event_type='other').exists())
        self.assertTrue(Notification.objects.filter(plant=plant).exists())
        self.assertIsNotNone(incident.id)


class WeatherApiTests(TestCase):
    @mock.patch('plants.views.urlrequest.urlopen')
    def test_weather_forecast_proxy(self, mock_urlopen):
        payload = json.dumps({'daily': {'temperature_2m_max': [20]}}).encode('utf-8')
        mock_response = mock.MagicMock()
        mock_response.read.return_value = payload
        mock_response.getcode.return_value = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        response = self.client.get(reverse('plants:weather_forecast_api') + '?lat=40.7&lon=-74.0')
        self.assertEqual(response.status_code, 200)
        self.assertIn('daily', response.json())


class TaskOptimizerTests(TestCase):
    def test_optimizer_prioritizes_overdue_high_urgency_tasks(self):
        start = timezone.datetime(2025, 1, 15).date()
        tasks = [
            CareTask(
                plant_id=1,
                plant_name='A',
                garden_name='Garden',
                event_type='repot',
                due_date=start,
                scheduled_date=start,
                is_overdue=False,
                days_overdue=0,
            ),
            CareTask(
                plant_id=2,
                plant_name='B',
                garden_name='Garden',
                event_type='water',
                due_date=start - timezone.timedelta(days=2),
                scheduled_date=start,
                is_overdue=True,
                days_overdue=2,
            ),
        ]
        optimized = HeuristicTaskOptimizer(daily_limit=1).optimize(tasks, start_date=start)
        self.assertEqual(optimized[0].plant_name, 'B')
        self.assertEqual(optimized[0].scheduled_date, start)
        self.assertEqual(optimized[1].scheduled_date, start + timezone.timedelta(days=1))


class OptimizedPlanApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='optuser', password='pass1234')
        self.client.login(username='optuser', password='pass1234')

        garden = Garden.objects.create(name='Garden')
        plant_type = PlantType.objects.create(name='Type')
        group = PlantGroup.objects.create(name='Group', plant_type=plant_type, garden=garden)
        Plant.objects.create(name='Plant', group=group, last_watered=timezone.now().date() - timezone.timedelta(days=7))

    def test_optimized_plan_endpoint_returns_tasks(self):
        response = self.client.get(reverse('plants:optimized_plan_api') + '?days=7&daily_limit=3')
        self.assertEqual(response.status_code, 200)
        self.assertIn('tasks', response.json())


class PestFollowupCommandTests(TestCase):
    def test_schedule_pest_followups_command(self):
        garden = Garden.objects.create(name='Cmd Garden')
        plant_type = PlantType.objects.create(name='Cmd Type')
        group = PlantGroup.objects.create(name='Cmd Group', plant_type=plant_type, garden=garden)
        plant = Plant.objects.create(name='Cmd Plant', group=group)
        PestIncident.objects.create(
            plant=plant,
            status='open',
            severity='medium',
            detected_on=timezone.now().date(),
            next_follow_up_date=timezone.now().date(),
            symptoms_observed='Leaf curl',
        )
        out = StringIO()
        call_command('schedule_pest_followups', days=1, stdout=out)
        self.assertIn('created events', out.getvalue())
