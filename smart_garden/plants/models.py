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

    # Default season-specific watering intervals
    default_spring_watering_interval_days = models.IntegerField(null=True, blank=True)
    default_summer_watering_interval_days = models.IntegerField(null=True, blank=True)
    default_fall_watering_interval_days = models.IntegerField(null=True, blank=True)
    default_winter_watering_interval_days = models.IntegerField(null=True, blank=True)

    # Default location-specific watering intervals
    default_indoor_watering_interval_days = models.IntegerField(null=True, blank=True)
    default_outdoor_watering_interval_days = models.IntegerField(null=True, blank=True)

class PlantGroup(models.Model):
    name = models.CharField(max_length=100)
    plant_type = models.ForeignKey(PlantType, on_delete=models.CASCADE)
    garden = models.ForeignKey(Garden, on_delete=models.CASCADE)

class Plant(models.Model):
    LOCATION_CHOICES = [
        ('indoor', 'Indoor'),
        ('outdoor', 'Outdoor'),
    ]

    SEASON_CHOICES = [
        ('spring', 'Spring'),
        ('summer', 'Summer'),
        ('fall', 'Fall'),
        ('winter', 'Winter'),
    ]

    @staticmethod
    def get_current_season():
        """
        Determine the current season based on the current month.
        Returns: string - 'spring', 'summer', 'fall', or 'winter'
        """
        month = timezone.now().date().month
        if 3 <= month <= 5:  # Spring (March-May)
            return 'spring'
        elif 6 <= month <= 8:  # Summer (June-August)
            return 'summer'
        elif 9 <= month <= 11:  # Fall (September-November)
            return 'fall'
        else:  # Winter (December-February)
            return 'winter'

    name = models.CharField(max_length=100)
    group = models.ForeignKey(PlantGroup, on_delete=models.CASCADE, related_name='plants')
    location = models.CharField(max_length=10, choices=LOCATION_CHOICES, default='indoor')
    individual_watering_interval_days = models.IntegerField(null=True, blank=True)
    individual_fertilization_interval_days = models.IntegerField(null=True, blank=True)
    last_watered = models.DateField(null=True, blank=True)
    last_fertilized = models.DateField(null=True, blank=True)

    # Season-specific watering intervals
    spring_watering_interval_days = models.IntegerField(null=True, blank=True)
    summer_watering_interval_days = models.IntegerField(null=True, blank=True)
    fall_watering_interval_days = models.IntegerField(null=True, blank=True)
    winter_watering_interval_days = models.IntegerField(null=True, blank=True)

    # Different watering intervals based on indoor/outdoor placement
    indoor_watering_interval_days = models.IntegerField(null=True, blank=True)
    outdoor_watering_interval_days = models.IntegerField(null=True, blank=True)

    def get_next_watering_date(self):
        # Get current date for calculations
        current_date = timezone.now().date()
        last = self.last_watered or current_date

        # Get current season
        current_season = self.get_current_season()

        # Get plant type for default values
        plant_type = self.group.plant_type

        # Check for season-specific interval (plant level first, then plant type level)
        season_interval = None
        if current_season == 'spring':
            season_interval = self.spring_watering_interval_days or plant_type.default_spring_watering_interval_days
        elif current_season == 'summer':
            season_interval = self.summer_watering_interval_days or plant_type.default_summer_watering_interval_days
        elif current_season == 'fall':
            season_interval = self.fall_watering_interval_days or plant_type.default_fall_watering_interval_days
        elif current_season == 'winter':
            season_interval = self.winter_watering_interval_days or plant_type.default_winter_watering_interval_days

        # Check for location-specific interval (plant level first, then plant type level)
        location_interval = None
        if self.location == 'indoor':
            location_interval = self.indoor_watering_interval_days or plant_type.default_indoor_watering_interval_days
        elif self.location == 'outdoor':
            location_interval = self.outdoor_watering_interval_days or plant_type.default_outdoor_watering_interval_days

        # Determine the interval to use (priority: individual > season > location > default)
        interval = self.individual_watering_interval_days or season_interval or location_interval or plant_type.default_watering_interval_days

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
