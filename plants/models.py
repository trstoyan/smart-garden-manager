from django.db import models
from django.utils import timezone

class Garden(models.Model):
    name = models.CharField(max_length=100)
    location = models.TextField(blank=True)

class PlantType(models.Model):
    name = models.CharField(max_length=100)
    default_watering_interval_days = models.IntegerField(default=7)
    default_water_type = models.CharField(max_length=100, default='plain')
    default_fertilization_interval_days = models.IntegerField(default=30)

class PlantGroup(models.Model):
    name = models.CharField(max_length=100)
    plant_type = models.ForeignKey(PlantType, on_delete=models.CASCADE)
    garden = models.ForeignKey(Garden, on_delete=models.CASCADE)

class Plant(models.Model):
    name = models.CharField(max_length=100)
    group = models.ForeignKey(PlantGroup, on_delete=models.CASCADE, related_name='plants')
    individual_watering_interval_days = models.IntegerField(null=True, blank=True)
    individual_fertilization_interval_days = models.IntegerField(null=True, blank=True)
    last_watered = models.DateField(null=True, blank=True)
    last_fertilized = models.DateField(null=True, blank=True)

    def get_next_watering_date(self):
        interval = self.individual_watering_interval_days or self.group.plant_type.default_watering_interval_days
        last = self.last_watered or timezone.now().date()
        return last + timezone.timedelta(days=interval)

    def get_next_fertilization_date(self):
        interval = self.individual_fertilization_interval_days or self.group.plant_type.default_fertilization_interval_days
        last = self.last_fertilized or timezone.now().date()
        return last + timezone.timedelta(days=interval)

class CalendarEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ('water', 'Watering'),
        ('fertilize', 'Fertilization'),
        ('repot', 'Repotting'),
        ('other', 'Other')
    ]

    plant = models.ForeignKey(Plant, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    date = models.DateField()
    notes = models.TextField(blank=True)

class Device(models.Model):
    device_id = models.CharField(max_length=100, unique=True)
    garden = models.ForeignKey(Garden, on_delete=models.CASCADE)
    description = models.TextField(blank=True)

class SensorReading(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    temperature = models.FloatField(null=True, blank=True)
    humidity = models.FloatField(null=True, blank=True)
    soil_moisture = models.IntegerField(null=True, blank=True)
    light = models.IntegerField(null=True, blank=True)

class Notification(models.Model):
    plant = models.ForeignKey(Plant, on_delete=models.CASCADE)
    event = models.ForeignKey(CalendarEvent, on_delete=models.CASCADE)
    sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
