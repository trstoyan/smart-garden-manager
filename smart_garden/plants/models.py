import secrets

from django.db import models
from django.utils import timezone


def generate_device_api_key():
    return secrets.token_hex(24)


class Garden(models.Model):
    name = models.CharField(max_length=100)
    location = models.TextField(blank=True)
    usda_hardiness_zone = models.CharField(max_length=10, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    soil_moisture_wet_threshold = models.IntegerField(null=True, blank=True)
    soil_moisture_dry_threshold = models.IntegerField(null=True, blank=True)
    light_low_threshold = models.IntegerField(null=True, blank=True)
    humidity_high_threshold = models.FloatField(null=True, blank=True)
    automation_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class PlantType(models.Model):
    name = models.CharField(max_length=100)
    scientific_name = models.CharField(max_length=200, blank=True)
    cultivar = models.CharField(max_length=120, blank=True)
    profile_notes = models.TextField(blank=True)
    preferred_usda_zone_min = models.IntegerField(null=True, blank=True)
    preferred_usda_zone_max = models.IntegerField(null=True, blank=True)

    MOISTURE_PREFERENCE_CHOICES = [
        ('dry', 'Dry'),
        ('balanced', 'Balanced'),
        ('moist', 'Moist'),
    ]
    SUBSTRATE_CHOICES = [
        ('soil', 'Soil'),
        ('coco', 'Coco Coir'),
        ('hydro', 'Hydroponic'),
        ('mix', 'Soilless Mix'),
    ]
    moisture_preference = models.CharField(
        max_length=20,
        choices=MOISTURE_PREFERENCE_CHOICES,
        default='balanced',
    )
    default_substrate_type = models.CharField(
        max_length=20,
        choices=SUBSTRATE_CHOICES,
        default='soil',
    )

    default_watering_interval_days = models.IntegerField(default=7)
    default_water_type = models.CharField(max_length=100, default='plain')
    default_fertilization_interval_days = models.IntegerField(default=30)
    default_repotting_interval_days = models.IntegerField(default=180)
    default_requires_pre_watering = models.BooleanField(default=False)
    default_pre_fertilization_water_gap_days = models.IntegerField(default=1)

    # Default season-specific watering intervals
    default_spring_watering_interval_days = models.IntegerField(null=True, blank=True)
    default_summer_watering_interval_days = models.IntegerField(null=True, blank=True)
    default_fall_watering_interval_days = models.IntegerField(null=True, blank=True)
    default_winter_watering_interval_days = models.IntegerField(null=True, blank=True)

    # Default location-specific watering intervals
    default_indoor_watering_interval_days = models.IntegerField(null=True, blank=True)
    default_outdoor_watering_interval_days = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return self.name

class PlantGroup(models.Model):
    name = models.CharField(max_length=100)
    plant_type = models.ForeignKey(PlantType, on_delete=models.CASCADE)
    garden = models.ForeignKey(Garden, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class PlantCareRule(models.Model):
    SCOPE_CHOICES = [
        ('plant', 'Plant'),
        ('group', 'Group'),
    ]

    name = models.CharField(max_length=120)
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES)
    plant = models.ForeignKey(
        'Plant',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='care_rules',
    )
    group = models.ForeignKey(
        PlantGroup,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='care_rules',
    )
    enabled = models.BooleanField(default=True)
    priority = models.IntegerField(default=100)

    watering_interval_days = models.IntegerField(null=True, blank=True)
    fertilization_interval_days = models.IntegerField(null=True, blank=True)
    repotting_interval_days = models.IntegerField(null=True, blank=True)
    requires_pre_watering = models.BooleanField(null=True, blank=True)
    pre_fertilization_water_gap_days = models.IntegerField(null=True, blank=True)
    soil_moisture_wet_threshold = models.IntegerField(null=True, blank=True)
    soil_moisture_dry_threshold = models.IntegerField(null=True, blank=True)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'id']
        indexes = [
            models.Index(fields=['scope', 'enabled', 'priority']),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(scope='plant') & models.Q(plant__isnull=False) & models.Q(group__isnull=True))
                    | (models.Q(scope='group') & models.Q(group__isnull=False) & models.Q(plant__isnull=True))
                ),
                name='care_rule_scope_target_consistency',
            ),
        ]

    def __str__(self):
        target = self.plant.name if self.scope == 'plant' and self.plant_id else self.group.name
        return f"{self.name} [{self.scope}:{target}]"


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
    substrate_type = models.CharField(
        max_length=20,
        choices=PlantType.SUBSTRATE_CHOICES,
        blank=True,
    )
    pot_volume_liters = models.FloatField(null=True, blank=True)
    drainage_class = models.IntegerField(null=True, blank=True)
    sun_exposure_hours = models.FloatField(null=True, blank=True)

    individual_watering_interval_days = models.IntegerField(null=True, blank=True)
    individual_fertilization_interval_days = models.IntegerField(null=True, blank=True)
    individual_repotting_interval_days = models.IntegerField(null=True, blank=True)
    individual_requires_pre_watering = models.BooleanField(null=True, blank=True)
    pre_fertilization_water_gap_days = models.IntegerField(null=True, blank=True)
    last_watered = models.DateField(null=True, blank=True)
    last_fertilized = models.DateField(null=True, blank=True)
    last_repotted = models.DateField(null=True, blank=True)

    # Season-specific watering intervals
    spring_watering_interval_days = models.IntegerField(null=True, blank=True)
    summer_watering_interval_days = models.IntegerField(null=True, blank=True)
    fall_watering_interval_days = models.IntegerField(null=True, blank=True)
    winter_watering_interval_days = models.IntegerField(null=True, blank=True)

    # Different watering intervals based on indoor/outdoor placement
    indoor_watering_interval_days = models.IntegerField(null=True, blank=True)
    outdoor_watering_interval_days = models.IntegerField(null=True, blank=True)
    soil_moisture_wet_threshold = models.IntegerField(null=True, blank=True)
    soil_moisture_critical_threshold = models.IntegerField(null=True, blank=True)

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

    def get_next_repotting_date(self):
        interval = self.individual_repotting_interval_days or self.group.plant_type.default_repotting_interval_days
        last = self.last_repotted or timezone.now().date()
        return last + timezone.timedelta(days=interval)

    def requires_pre_watering_before_fertilizing(self):
        if self.individual_requires_pre_watering is not None:
            return self.individual_requires_pre_watering
        return self.group.plant_type.default_requires_pre_watering

    def get_pre_fertilization_water_gap_days(self):
        if self.pre_fertilization_water_gap_days is not None:
            return self.pre_fertilization_water_gap_days
        return self.group.plant_type.default_pre_fertilization_water_gap_days

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(pot_volume_liters__isnull=True) | models.Q(pot_volume_liters__gte=0),
                name='plant_pot_volume_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(drainage_class__isnull=True)
                | (models.Q(drainage_class__gte=1) & models.Q(drainage_class__lte=5)),
                name='plant_drainage_class_range',
            ),
        ]

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

    class Meta:
        unique_together = ('plant', 'event_type', 'date')

    def __str__(self):
        return f"{self.plant.name}: {self.event_type} on {self.date}"

class Device(models.Model):
    device_id = models.CharField(max_length=100, unique=True)
    api_key = models.CharField(
        max_length=64,
        unique=True,
        default=generate_device_api_key,
        editable=False,
    )
    garden = models.ForeignKey(Garden, on_delete=models.CASCADE)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.device_id

class SensorReading(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    temperature = models.FloatField(null=True, blank=True)
    humidity = models.FloatField(null=True, blank=True)
    soil_moisture = models.IntegerField(null=True, blank=True)
    light = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.device.device_id} @ {self.timestamp}"

    class Meta:
        indexes = [
            models.Index(fields=['device', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]


class SensorIngestRecord(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='ingest_records')
    idempotency_key = models.CharField(max_length=100)
    reading = models.ForeignKey(SensorReading, on_delete=models.CASCADE, related_name='ingest_records')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('device', 'idempotency_key')

    def __str__(self):
        return f"{self.device.device_id}:{self.idempotency_key}"


class DeviceAction(models.Model):
    ACTION_TYPE_CHOICES = [
        ('water_pump_on', 'Water Pump On'),
        ('grow_light_on', 'Grow Light On'),
        ('ventilation_on', 'Ventilation On'),
        ('custom', 'Custom'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('executed', 'Executed'),
        ('failed', 'Failed'),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='actions')
    action_type = models.CharField(max_length=30, choices=ACTION_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reason = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    attempts = models.IntegerField(default=0)
    last_error = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.device.device_id}: {self.action_type} ({self.status})"

    class Meta:
        indexes = [
            models.Index(fields=['status', 'next_attempt_at', 'attempts']),
            models.Index(fields=['device', 'action_type', 'status', 'created_at']),
        ]


class PlantStatusLog(models.Model):
    STATUS_CHOICES = [
        ('healthy', 'Healthy'),
        ('flowering', 'Flowering'),
        ('dormant', 'Dormant'),
        ('repotted', 'Repotted'),
        ('stressed', 'Stressed'),
        ('pest', 'Pest'),
        ('other', 'Other'),
    ]

    plant = models.ForeignKey(Plant, on_delete=models.CASCADE, related_name='status_logs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.plant.name}: {self.status} ({self.date})"


class PestDiseaseProfile(models.Model):
    PROFILE_TYPE_CHOICES = [
        ('pest', 'Pest'),
        ('disease', 'Disease'),
    ]

    name = models.CharField(max_length=120, unique=True)
    profile_type = models.CharField(max_length=20, choices=PROFILE_TYPE_CHOICES)
    symptoms = models.TextField()
    default_treatment_plan = models.TextField(blank=True)
    follow_up_interval_days = models.IntegerField(default=7)
    severity_hint = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.name


class PestIncident(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('monitoring', 'Monitoring'),
        ('resolved', 'Resolved'),
    ]
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    plant = models.ForeignKey(Plant, on_delete=models.CASCADE, related_name='pest_incidents')
    profile = models.ForeignKey(PestDiseaseProfile, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    detected_on = models.DateField(default=timezone.now)
    symptoms_observed = models.TextField(blank=True)
    treatment_plan = models.TextField(blank=True)
    next_follow_up_date = models.DateField(null=True, blank=True)
    resolved_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.plant.name} incident ({self.status})"

class Notification(models.Model):
    plant = models.ForeignKey(Plant, on_delete=models.CASCADE)
    event = models.ForeignKey(CalendarEvent, on_delete=models.CASCADE)
    sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    last_error = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Notification({self.plant.name}, {self.event.event_type}, sent={self.sent})"

    class Meta:
        indexes = [
            models.Index(fields=['sent', 'next_attempt_at']),
        ]
