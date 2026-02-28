from rest_framework import serializers
from django.utils import timezone

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


class GardenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Garden
        fields = '__all__'


class PlantTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantType
        fields = '__all__'


class PlantGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantGroup
        fields = '__all__'


class PlantSerializer(serializers.ModelSerializer):
    next_watering_date = serializers.SerializerMethodField()
    next_fertilization_date = serializers.SerializerMethodField()
    next_repotting_date = serializers.SerializerMethodField()

    class Meta:
        model = Plant
        fields = '__all__'
        read_only_fields = ['next_watering_date', 'next_fertilization_date', 'next_repotting_date']

    def get_next_watering_date(self, obj):
        return obj.get_next_watering_date()

    def get_next_fertilization_date(self, obj):
        return obj.get_next_fertilization_date()

    def get_next_repotting_date(self, obj):
        return obj.get_next_repotting_date()


class CalendarEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarEvent
        fields = '__all__'


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = '__all__'
        read_only_fields = ['api_key']


class SensorReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorReading
        fields = '__all__'
        read_only_fields = ['timestamp']


class SensorIngestRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorIngestRecord
        fields = '__all__'
        read_only_fields = ['created_at']


class PlantStatusLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantStatusLog
        fields = '__all__'


class PestDiseaseProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PestDiseaseProfile
        fields = '__all__'


class PestIncidentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PestIncident
        fields = '__all__'

    def validate(self, attrs):
        status_value = attrs.get('status')
        if status_value == 'resolved' and not attrs.get('resolved_on'):
            attrs['resolved_on'] = timezone.now().date()
        return attrs

    def create(self, validated_data):
        profile = validated_data.get('profile')
        detected_on = validated_data.get('detected_on')
        if profile:
            if not validated_data.get('treatment_plan') and profile.default_treatment_plan:
                validated_data['treatment_plan'] = profile.default_treatment_plan
            if not validated_data.get('next_follow_up_date') and detected_on:
                validated_data['next_follow_up_date'] = detected_on + timezone.timedelta(
                    days=profile.follow_up_interval_days
                )
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data.get('status') == 'resolved' and not validated_data.get('resolved_on'):
            validated_data['resolved_on'] = timezone.now().date()
        return super().update(instance, validated_data)


class DeviceActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceAction
        fields = '__all__'
        read_only_fields = ['created_at', 'attempts', 'last_error', 'next_attempt_at', 'executed_at']


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'


class SensorReadingIngestSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=100)
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True)
    temperature = serializers.FloatField(required=False, allow_null=True)
    humidity = serializers.FloatField(required=False, allow_null=True)
    soil_moisture = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    light = serializers.IntegerField(required=False, allow_null=True, min_value=0)

    def validate(self, attrs):
        measurement_fields = ('temperature', 'humidity', 'soil_moisture', 'light')
        if not any(field in attrs and attrs[field] is not None for field in measurement_fields):
            raise serializers.ValidationError('At least one sensor measurement is required.')
        return attrs


class PlantCareRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantCareRule
        fields = '__all__'

    def validate(self, attrs):
        scope = attrs.get('scope', getattr(self.instance, 'scope', None))
        plant = attrs.get('plant', getattr(self.instance, 'plant', None))
        group = attrs.get('group', getattr(self.instance, 'group', None))
        if scope == 'plant':
            if not plant or group is not None:
                raise serializers.ValidationError("Plant scope requires 'plant' and forbids 'group'.")
        elif scope == 'group':
            if not group or plant is not None:
                raise serializers.ValidationError("Group scope requires 'group' and forbids 'plant'.")
        else:
            raise serializers.ValidationError("Scope must be 'plant' or 'group'.")
        return attrs
