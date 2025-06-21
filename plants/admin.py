from django.contrib import admin
from .models import Garden, PlantType, PlantGroup, Plant, CalendarEvent, Device, SensorReading, Notification

# Register your models here.
admin.site.register(Garden)
admin.site.register(PlantType)
admin.site.register(PlantGroup)
admin.site.register(Plant)
admin.site.register(CalendarEvent)
admin.site.register(Device)
admin.site.register(SensorReading)
admin.site.register(Notification)
