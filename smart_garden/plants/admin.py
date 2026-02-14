from django.contrib import admin
from .models import Garden, PlantType, PlantGroup, Plant, CalendarEvent, Device, SensorReading, Notification


@admin.register(Garden)
class GardenAdmin(admin.ModelAdmin):
    list_display = ['name', 'location']
    search_fields = ['name']


@admin.register(PlantType)
class PlantTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'default_watering_interval_days', 'default_fertilization_interval_days']
    search_fields = ['name']
    fieldsets = (
        ('Basic Information', {
            'fields': ['name', 'default_water_type']
        }),
        ('Default Care Intervals', {
            'fields': ['default_watering_interval_days', 'default_fertilization_interval_days']
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
            'fields': ['name', 'group', 'location']
        }),
        ('Care History', {
            'fields': ['last_watered', 'last_fertilized']
        }),
        ('Individual Care Intervals', {
            'fields': [
                'individual_watering_interval_days',
                'individual_fertilization_interval_days'
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
    list_display = ['device_id', 'garden', 'description']
    list_filter = ['garden']
    search_fields = ['device_id', 'description']


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
    list_display = ['plant', 'event', 'sent', 'sent_at']
    list_filter = ['sent', 'sent_at']
    readonly_fields = ['sent_at']