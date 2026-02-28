from django import forms

from .models import Device, Garden, Plant, PlantCareRule, PlantGroup, PlantType


class PlantForm(forms.ModelForm):
    class Meta:
        model = Plant
        fields = '__all__'


class PlantCareRuleForm(forms.ModelForm):
    class Meta:
        model = PlantCareRule
        exclude = ['created_at', 'updated_at']


class GardenForm(forms.ModelForm):
    class Meta:
        model = Garden
        fields = '__all__'


class PlantTypeForm(forms.ModelForm):
    class Meta:
        model = PlantType
        fields = '__all__'


class PlantGroupForm(forms.ModelForm):
    class Meta:
        model = PlantGroup
        fields = '__all__'


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = ['device_id', 'garden', 'description']
