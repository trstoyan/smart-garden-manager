from django.test import TestCase
from django.utils import timezone
from unittest import mock
from .models import (
    Garden,
    PlantType,
    PlantGroup,
    Plant,
    CalendarEvent,
    Device,
    SensorReading,
    Notification,
)

class PlantModelTests(TestCase):
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

    def test_get_next_watering_date_default(self):
        plant_type = PlantType.objects.create(name='Type')
        garden = Garden.objects.create(name='Garden')
        group = PlantGroup.objects.create(name='Group', plant_type=plant_type, garden=garden)
        plant = Plant.objects.create(name='Plant', group=group)
        mock_dt = timezone.datetime(2025, 1, 1)
        with mock.patch('plants.models.timezone.now', return_value=mock_dt):
            expected_date = mock_dt.date() + timezone.timedelta(days=plant_type.default_watering_interval_days)
            self.assertEqual(plant.get_next_watering_date(), expected_date)

    def test_get_next_fertilization_date_default(self):
        plant_type = PlantType.objects.create(name='Type')
        garden = Garden.objects.create(name='Garden')
        group = PlantGroup.objects.create(name='Group', plant_type=plant_type, garden=garden)
        plant = Plant.objects.create(name='Plant', group=group)
        mock_dt = timezone.datetime(2025, 1, 1)
        with mock.patch('plants.models.timezone.now', return_value=mock_dt):
            expected_date = mock_dt.date() + timezone.timedelta(days=plant_type.default_fertilization_interval_days)
            self.assertEqual(plant.get_next_fertilization_date(), expected_date)

class BasicModelTests(TestCase):
    def test_garden_creation(self):
        garden = Garden.objects.create(name='G', location='L')
        self.assertEqual(garden.name, 'G')
        self.assertEqual(garden.location, 'L')

    def test_plant_type_defaults(self):
        pt = PlantType.objects.create(name='T')
        self.assertEqual(pt.default_watering_interval_days, 7)
        self.assertEqual(pt.default_water_type, 'plain')
        self.assertEqual(pt.default_fertilization_interval_days, 30)

    def test_plant_group_creation(self):
        pt = PlantType.objects.create(name='T')
        garden = Garden.objects.create(name='G')
        group = PlantGroup.objects.create(name='Grp', plant_type=pt, garden=garden)
        self.assertEqual(group.name, 'Grp')
        self.assertEqual(group.plant_type, pt)
        self.assertEqual(group.garden, garden)

    def test_calendar_event_creation(self):
        pt = PlantType.objects.create(name='T')
        garden = Garden.objects.create(name='G')
        group = PlantGroup.objects.create(name='Grp', plant_type=pt, garden=garden)
        plant = Plant.objects.create(name='P', group=group)
        event = CalendarEvent.objects.create(
            plant=plant,
            event_type='water',
            date=timezone.now().date(),
            notes='n'
        )
        self.assertEqual(event.event_type, 'water')
        self.assertEqual(event.plant, plant)

    def test_sensor_reading_creation(self):
        garden = Garden.objects.create(name='G')
        device = Device.objects.create(device_id='d1', garden=garden)
        sr = SensorReading.objects.create(
            device=device,
            temperature=23.5,
            humidity=55.0,
            soil_moisture=10,
            light=200
        )
        self.assertEqual(sr.device, device)
        self.assertEqual(sr.temperature, 23.5)

    def test_notification_creation(self):
        pt = PlantType.objects.create(name='T')
        garden = Garden.objects.create(name='G')
        group = PlantGroup.objects.create(name='Grp', plant_type=pt, garden=garden)
        plant = Plant.objects.create(name='P', group=group)
        event = CalendarEvent.objects.create(
            plant=plant,
            event_type='water',
            date=timezone.now().date()
        )
        notification = Notification.objects.create(
            plant=plant,
            event=event,
            sent=True
        )
        self.assertTrue(notification.sent)
        self.assertEqual(notification.event, event)
