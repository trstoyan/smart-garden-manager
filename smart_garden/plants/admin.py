from django.contrib import admin
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


@admin.register(Garden)
class GardenAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'location',
        'usda_hardiness_zone',
        'soil_moisture_wet_threshold',
        'soil_moisture_dry_threshold',
        'light_low_threshold',
        'humidity_high_threshold',
        'automation_enabled',
    ]
    search_fields = ['name']
    fieldsets = (
        ('Basic Information', {
            'fields': ['name', 'location', 'usda_hardiness_zone', 'latitude', 'longitude']
        }),
        ('Automation Thresholds', {
            'fields': [
                'soil_moisture_wet_threshold',
                'soil_moisture_dry_threshold',
                'light_low_threshold',
                'humidity_high_threshold',
                'automation_enabled',
            ]
        }),
    )


@admin.register(PlantType)
class PlantTypeAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'scientific_name',
        'cultivar',
        'default_watering_interval_days',
        'default_fertilization_interval_days',
        'default_repotting_interval_days',
    ]
    search_fields = ['name']
    fieldsets = (
        ('Basic Information', {
            'fields': [
                'name',
                'scientific_name',
                'cultivar',
                'default_water_type',
                'profile_notes',
            ]
        }),
        ('Care Profile', {
            'fields': [
                'moisture_preference',
                'default_substrate_type',
                'preferred_usda_zone_min',
                'preferred_usda_zone_max',
            ]
        }),
        ('Default Care Intervals', {
            'fields': [
                'default_watering_interval_days',
                'default_fertilization_interval_days',
                'default_repotting_interval_days',
            ]
        }),
        ('Fertilization Workflow', {
            'fields': [
                'default_requires_pre_watering',
                'default_pre_fertilization_water_gap_days',
            ],
            'classes': ['collapse']
        }),
        ('Seasonal Watering Intervals', {
            'fields': [
                'default_spring_watering_interval_days',
                'default_summer_watering_interval_days',
                'default_fall_watering_interval_days',
                'default_winter_watering_interval_days'
            ],
            'classes': ['collapse']
        }),
        ('Location-Specific Intervals', {
            'fields': [
                'default_indoor_watering_interval_days',
                'default_outdoor_watering_interval_days'
            ],
            'classes': ['collapse']
        })
    )


@admin.register(PlantGroup)
class PlantGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'plant_type', 'garden']
    list_filter = ['plant_type', 'garden']
    search_fields = ['name']


@admin.register(PlantCareRule)
class PlantCareRuleAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'scope',
        'plant',
        'group',
        'enabled',
        'priority',
        'watering_interval_days',
        'fertilization_interval_days',
        'repotting_interval_days',
    ]
    list_filter = ['scope', 'enabled']
    search_fields = ['name', 'plant__name', 'group__name', 'notes']


@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'group', 'location', 'last_watered', 'last_fertilized',
        'get_next_watering_date', 'get_next_fertilization_date'
    ]
    list_filter = ['location', 'group__plant_type', 'group__garden']
    search_fields = ['name']
    date_hierarchy = 'last_watered'
    
    fieldsets = (
        ('Basic Information', {
            'fields': [
                'name',
                'group',
                'location',
                'substrate_type',
                'pot_volume_liters',
                'drainage_class',
                'sun_exposure_hours',
            ]
        }),
        ('Care History', {
            'fields': ['last_watered', 'last_fertilized']
        }),
        ('Lifecycle', {
            'fields': ['last_repotted']
        }),
        ('Individual Care Intervals', {
            'fields': [
                'individual_watering_interval_days',
                'individual_fertilization_interval_days',
                'individual_repotting_interval_days',
            ],
            'classes': ['collapse']
        }),
        ('Fertilization Workflow', {
            'fields': [
                'individual_requires_pre_watering',
                'pre_fertilization_water_gap_days',
            ],
            'classes': ['collapse']
        }),
        ('Seasonal Watering Overrides', {
            'fields': [
                'spring_watering_interval_days',
                'summer_watering_interval_days',
                'fall_watering_interval_days',
                'winter_watering_interval_days'
            ],
            'classes': ['collapse']
        }),
        ('Location-Specific Overrides', {
            'fields': [
                'indoor_watering_interval_days',
                'outdoor_watering_interval_days'
            ],
            'classes': ['collapse']
        }),
        ('Sensor-Aware Watering', {
            'fields': ['soil_moisture_wet_threshold', 'soil_moisture_critical_threshold'],
            'classes': ['collapse']
        })
    )
    
    def get_next_watering_date(self, obj):
        return obj.get_next_watering_date()
    get_next_watering_date.short_description = 'Next Watering'
    get_next_watering_date.admin_order_field = 'last_watered'
    
    def get_next_fertilization_date(self, obj):
        return obj.get_next_fertilization_date()
    get_next_fertilization_date.short_description = 'Next Fertilization'
    get_next_fertilization_date.admin_order_field = 'last_fertilized'


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ['plant', 'event_type', 'date', 'notes']
    list_filter = ['event_type', 'date']
    search_fields = ['plant__name', 'notes']
    date_hierarchy = 'date'


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['device_id', 'garden', 'description', 'api_key']
    list_filter = ['garden']
    search_fields = ['device_id', 'description', 'api_key']
    readonly_fields = ['api_key']


@admin.register(SensorReading)
class SensorReadingAdmin(admin.ModelAdmin):
    list_display = ['device', 'timestamp', 'temperature', 'humidity', 'soil_moisture', 'light']
    list_filter = ['device', 'timestamp']
    date_hierarchy = 'timestamp'
    readonly_fields = ['timestamp']
    
    def has_add_permission(self, request):
        # Sensor readings should typically be added via API, not admin
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['plant', 'event', 'sent', 'sent_at', 'attempts', 'next_attempt_at']
    list_filter = ['sent', 'sent_at', 'next_attempt_at']
    readonly_fields = ['sent_at', 'attempts', 'last_error', 'next_attempt_at']


@admin.register(PlantStatusLog)
class PlantStatusLogAdmin(admin.ModelAdmin):
    list_display = ['plant', 'status', 'date']
    list_filter = ['status', 'date']
    search_fields = ['plant__name', 'notes']
    date_hierarchy = 'date'


@admin.register(DeviceAction)
class DeviceActionAdmin(admin.ModelAdmin):
    list_display = [
        'device',
        'action_type',
        'status',
        'attempts',
        'next_attempt_at',
        'created_at',
        'executed_at',
    ]
    list_filter = ['action_type', 'status', 'created_at', 'next_attempt_at']
    search_fields = ['device__device_id', 'reason']
    date_hierarchy = 'created_at'
    readonly_fields = ['attempts', 'last_error', 'next_attempt_at']


@admin.register(PestDiseaseProfile)
class PestDiseaseProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'profile_type', 'follow_up_interval_days', 'severity_hint']
    list_filter = ['profile_type']
    search_fields = ['name', 'symptoms']


@admin.register(PestIncident)
class PestIncidentAdmin(admin.ModelAdmin):
    list_display = ['plant', 'profile', 'status', 'severity', 'detected_on', 'next_follow_up_date']
    list_filter = ['status', 'severity', 'detected_on']
    search_fields = ['plant__name', 'symptoms_observed', 'notes']
    date_hierarchy = 'detected_on'


@admin.register(SensorIngestRecord)
class SensorIngestRecordAdmin(admin.ModelAdmin):
    list_display = ['device', 'idempotency_key', 'reading', 'created_at']
    search_fields = ['device__device_id', 'idempotency_key']
    readonly_fields = ['device', 'idempotency_key', 'reading', 'created_at']
    date_hierarchy = 'created_at'
