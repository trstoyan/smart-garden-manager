import json
from datetime import date, timedelta
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.http import require_POST
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .forms import DeviceForm, GardenForm, PlantCareRuleForm, PlantForm, PlantGroupForm, PlantTypeForm
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
    SensorIngestRecord,
    PlantType,
    SensorReading,
    generate_device_api_key,
)
from .serializers import (
    CalendarEventSerializer,
    DeviceActionSerializer,
    DeviceSerializer,
    GardenSerializer,
    NotificationSerializer,
    PestDiseaseProfileSerializer,
    PestIncidentSerializer,
    PlantCareRuleSerializer,
    PlantGroupSerializer,
    PlantSerializer,
    PlantStatusLogSerializer,
    PlantTypeSerializer,
    SensorReadingIngestSerializer,
    SensorReadingSerializer,
)
from .services import (
    CareTaskPlanner,
    DeviceActionDispatcher,
    DeviceAutomationService,
    HeuristicTaskOptimizer,
    NotificationDispatcher,
    PestIncidentService,
)


def _parse_positive_int(value, default, lower, upper):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(lower, min(parsed, upper))


def _unique_name(model, base):
    if not model.objects.filter(name=base).exists():
        return base
    suffix = 2
    while model.objects.filter(name=f"{base} {suffix}").exists():
        suffix += 1
    return f"{base} {suffix}"


def _split_form_fields(form, advanced_names=None):
    advanced_set = set(advanced_names or [])
    basic = []
    advanced = []
    for name in form.fields:
        bound_field = form[name]
        if name in advanced_set:
            advanced.append(bound_field)
        else:
            basic.append(bound_field)
    return basic, advanced


def _limited_form(form, allowed_names):
    allowed = set(allowed_names)
    for field_name in list(form.fields):
        if field_name not in allowed:
            form.fields.pop(field_name, None)
    return form


def home(request):
    return render(request, 'index.html')


def onboarding_wizard_view(request):
    step = _parse_positive_int(request.GET.get('step'), default=1, lower=1, upper=5)
    step_meta = {
        1: {
            'title': 'Create Your Garden',
            'help': 'Start with one garden space (balcony, indoor shelf, backyard bed).',
            'form_class': GardenForm,
            'allowed_fields': ['name', 'location'],
            'session_key': 'onboarding_garden_id',
        },
        2: {
            'title': 'Add Plant Type',
            'help': 'Define the care profile for a type (for example: Tomato, Basil, Monstera).',
            'form_class': PlantTypeForm,
            'allowed_fields': [
                'name',
                'moisture_preference',
                'default_substrate_type',
                'default_watering_interval_days',
                'default_fertilization_interval_days',
                'default_repotting_interval_days',
            ],
            'session_key': 'onboarding_plant_type_id',
        },
        3: {
            'title': 'Create Plant Group',
            'help': 'Group similar plants together for easier scheduling.',
            'form_class': PlantGroupForm,
            'allowed_fields': ['name', 'garden', 'plant_type'],
            'session_key': 'onboarding_group_id',
        },
        4: {
            'title': 'Add First Plant',
            'help': 'Create your first plant record.',
            'form_class': PlantForm,
            'allowed_fields': ['name', 'group', 'location'],
            'session_key': 'onboarding_plant_id',
        },
        5: {
            'title': 'Register First Device (Optional)',
            'help': 'You can skip this and add devices later.',
            'form_class': DeviceForm,
            'allowed_fields': ['device_id', 'garden', 'description'],
            'session_key': 'onboarding_device_id',
        },
    }
    config = step_meta[step]

    initial = {}
    if step == 3:
        if request.session.get('onboarding_garden_id'):
            initial['garden'] = request.session['onboarding_garden_id']
        if request.session.get('onboarding_plant_type_id'):
            initial['plant_type'] = request.session['onboarding_plant_type_id']
    elif step == 4 and request.session.get('onboarding_group_id'):
        initial['group'] = request.session['onboarding_group_id']
    elif step == 5 and request.session.get('onboarding_garden_id'):
        initial['garden'] = request.session['onboarding_garden_id']

    if request.method == 'POST':
        if step == 5 and request.POST.get('skip') == '1':
            messages.success(request, 'Onboarding complete. You can add devices later.')
            return redirect('plants:setup_center')

        form = _limited_form(config['form_class'](request.POST, initial=initial), config['allowed_fields'])
        if form.is_valid():
            instance = form.save()
            request.session[config['session_key']] = instance.id
            if step < 5:
                return redirect(f"{reverse('plants:onboarding_wizard')}?step={step + 1}")
            messages.success(request, 'Onboarding complete.')
            return redirect('plants:setup_center')
    else:
        form = _limited_form(config['form_class'](initial=initial), config['allowed_fields'])

    basic_fields, advanced_fields = _split_form_fields(form, advanced_names=[])
    context = {
        'step': step,
        'total_steps': 5,
        'step_title': config['title'],
        'step_help': config['help'],
        'step_labels': [
            'Garden',
            'Plant Type',
            'Group',
            'Plant',
            'Device',
        ],
        'form': form,
        'basic_fields': basic_fields,
        'advanced_fields': advanced_fields,
        'show_skip': step == 5,
    }
    return render(request, 'plants/onboarding_wizard.html', context)


def setup_center_view(request):
    if request.method == 'POST':
        starter_pack = request.POST.get('starter_pack', '').strip()
        if starter_pack == 'balcony_herbs':
            garden = Garden.objects.create(name=_unique_name(Garden, 'Balcony Garden'), location='Balcony')
            plant_type = PlantType.objects.create(
                name=_unique_name(PlantType, 'Herbs'),
                moisture_preference='balanced',
                default_substrate_type='soil',
                default_watering_interval_days=3,
                default_fertilization_interval_days=21,
                default_repotting_interval_days=120,
            )
            group = PlantGroup.objects.create(
                name=_unique_name(PlantGroup, 'Kitchen Herbs'),
                garden=garden,
                plant_type=plant_type,
            )
            Plant.objects.create(name=_unique_name(Plant, 'Basil'), group=group, location='outdoor')
            messages.success(request, 'Starter pack created: Balcony Herbs.')
            return redirect('plants:setup_center')
        if starter_pack == 'indoor_houseplants':
            garden = Garden.objects.create(name=_unique_name(Garden, 'Indoor Garden'), location='Living Room')
            plant_type = PlantType.objects.create(
                name=_unique_name(PlantType, 'Houseplants'),
                moisture_preference='balanced',
                default_substrate_type='soil',
                default_watering_interval_days=7,
                default_fertilization_interval_days=30,
                default_repotting_interval_days=180,
            )
            group = PlantGroup.objects.create(
                name=_unique_name(PlantGroup, 'Indoor Foliage'),
                garden=garden,
                plant_type=plant_type,
            )
            Plant.objects.create(name=_unique_name(Plant, 'Monstera'), group=group, location='indoor')
            messages.success(request, 'Starter pack created: Indoor Houseplants.')
            return redirect('plants:setup_center')
        messages.error(request, 'Unknown starter pack.')
        return redirect('plants:setup_center')

    gardens = Garden.objects.all().order_by('name')
    plant_types = PlantType.objects.all().order_by('name')
    plant_groups = PlantGroup.objects.select_related('garden', 'plant_type').all().order_by('name')
    plants = Plant.objects.all()
    devices = Device.objects.all()
    setup_checks = [
        gardens.exists(),
        plant_types.exists(),
        plant_groups.exists(),
        plants.exists(),
        devices.exists(),
    ]
    context = {
        'gardens': gardens,
        'plant_types': plant_types,
        'plant_groups': plant_groups,
        'setup_progress': {
            'gardens': gardens.count(),
            'plant_types': plant_types.count(),
            'plant_groups': plant_groups.count(),
            'plants': plants.count(),
            'devices': devices.count(),
        },
        'setup_completed_steps': sum(1 for item in setup_checks if item),
        'setup_total_steps': len(setup_checks),
    }
    return render(request, 'plants/setup_center.html', context)


def tools_tutorial_view(request):
    return render(request, 'plants/tools_tutorial.html')


def ai_assistant_preview_view(request):
    return render(request, 'plants/ai_assistant_preview.html')


def plants_dashboard(request):
    plants = (
        Plant.objects
        .select_related('group__garden', 'group__plant_type')
        .all()
        .order_by('name')
    )
    return render(request, 'plants/dashboard.html', {'plants': plants})


def plant_create_view(request):
    if request.method == 'POST':
        form = PlantForm(request.POST)
        if form.is_valid():
            plant = form.save()
            messages.success(request, f'Plant "{plant.name}" created.')
            return redirect('plants:plant_detail', plant_id=plant.id)
    else:
        form = PlantForm()
    basic_fields, advanced_fields = _split_form_fields(
        form,
        advanced_names={
            'substrate_type',
            'pot_volume_liters',
            'drainage_class',
            'sun_exposure_hours',
            'individual_watering_interval_days',
            'individual_fertilization_interval_days',
            'individual_repotting_interval_days',
            'individual_requires_pre_watering',
            'pre_fertilization_water_gap_days',
            'spring_watering_interval_days',
            'summer_watering_interval_days',
            'fall_watering_interval_days',
            'winter_watering_interval_days',
            'indoor_watering_interval_days',
            'outdoor_watering_interval_days',
            'soil_moisture_wet_threshold',
            'soil_moisture_critical_threshold',
            'last_watered',
            'last_fertilized',
            'last_repotted',
        },
    )
    return render(
        request,
        'plants/plant_form.html',
        {'form': form, 'plant': None, 'basic_fields': basic_fields, 'advanced_fields': advanced_fields},
    )


def garden_create_view(request):
    if request.method == 'POST':
        form = GardenForm(request.POST)
        if form.is_valid():
            garden = form.save()
            messages.success(request, f'Garden "{garden.name}" created.')
            return redirect('plants:garden_detail', garden_id=garden.id)
    else:
        form = GardenForm()
    basic_fields, advanced_fields = _split_form_fields(
        form,
        advanced_names={
            'usda_hardiness_zone',
            'latitude',
            'longitude',
            'soil_moisture_wet_threshold',
            'soil_moisture_dry_threshold',
            'light_low_threshold',
            'humidity_high_threshold',
            'automation_enabled',
        },
    )
    return render(
        request,
        'plants/garden_form.html',
        {'form': form, 'garden': None, 'basic_fields': basic_fields, 'advanced_fields': advanced_fields},
    )


def garden_detail_view(request, garden_id):
    garden = get_object_or_404(Garden, pk=garden_id)
    if request.method == 'POST':
        form = GardenForm(request.POST, instance=garden)
        if form.is_valid():
            garden = form.save()
            messages.success(request, f'Garden "{garden.name}" updated.')
            return redirect('plants:garden_detail', garden_id=garden.id)
    else:
        form = GardenForm(instance=garden)
    basic_fields, advanced_fields = _split_form_fields(
        form,
        advanced_names={
            'usda_hardiness_zone',
            'latitude',
            'longitude',
            'soil_moisture_wet_threshold',
            'soil_moisture_dry_threshold',
            'light_low_threshold',
            'humidity_high_threshold',
            'automation_enabled',
        },
    )
    return render(
        request,
        'plants/garden_form.html',
        {'form': form, 'garden': garden, 'basic_fields': basic_fields, 'advanced_fields': advanced_fields},
    )


@require_POST
def garden_delete_view(request, garden_id):
    garden = get_object_or_404(Garden, pk=garden_id)
    name = garden.name
    garden.delete()
    messages.success(request, f'Garden "{name}" deleted.')
    return redirect('plants:setup_center')


def plant_type_create_view(request):
    if request.method == 'POST':
        form = PlantTypeForm(request.POST)
        if form.is_valid():
            plant_type = form.save()
            messages.success(request, f'Plant type "{plant_type.name}" created.')
            return redirect('plants:plant_type_detail', plant_type_id=plant_type.id)
    else:
        form = PlantTypeForm()
    basic_fields, advanced_fields = _split_form_fields(
        form,
        advanced_names={
            'scientific_name',
            'cultivar',
            'profile_notes',
            'preferred_usda_zone_min',
            'preferred_usda_zone_max',
            'default_water_type',
            'default_requires_pre_watering',
            'default_pre_fertilization_water_gap_days',
            'default_spring_watering_interval_days',
            'default_summer_watering_interval_days',
            'default_fall_watering_interval_days',
            'default_winter_watering_interval_days',
            'default_indoor_watering_interval_days',
            'default_outdoor_watering_interval_days',
        },
    )
    return render(
        request,
        'plants/plant_type_form.html',
        {'form': form, 'plant_type': None, 'basic_fields': basic_fields, 'advanced_fields': advanced_fields},
    )


def plant_type_detail_view(request, plant_type_id):
    plant_type = get_object_or_404(PlantType, pk=plant_type_id)
    if request.method == 'POST':
        form = PlantTypeForm(request.POST, instance=plant_type)
        if form.is_valid():
            plant_type = form.save()
            messages.success(request, f'Plant type "{plant_type.name}" updated.')
            return redirect('plants:plant_type_detail', plant_type_id=plant_type.id)
    else:
        form = PlantTypeForm(instance=plant_type)
    basic_fields, advanced_fields = _split_form_fields(
        form,
        advanced_names={
            'scientific_name',
            'cultivar',
            'profile_notes',
            'preferred_usda_zone_min',
            'preferred_usda_zone_max',
            'default_water_type',
            'default_requires_pre_watering',
            'default_pre_fertilization_water_gap_days',
            'default_spring_watering_interval_days',
            'default_summer_watering_interval_days',
            'default_fall_watering_interval_days',
            'default_winter_watering_interval_days',
            'default_indoor_watering_interval_days',
            'default_outdoor_watering_interval_days',
        },
    )
    return render(
        request,
        'plants/plant_type_form.html',
        {'form': form, 'plant_type': plant_type, 'basic_fields': basic_fields, 'advanced_fields': advanced_fields},
    )


@require_POST
def plant_type_delete_view(request, plant_type_id):
    plant_type = get_object_or_404(PlantType, pk=plant_type_id)
    name = plant_type.name
    plant_type.delete()
    messages.success(request, f'Plant type "{name}" deleted.')
    return redirect('plants:setup_center')


def plant_group_create_view(request):
    if request.method == 'POST':
        form = PlantGroupForm(request.POST)
        if form.is_valid():
            group = form.save()
            messages.success(request, f'Plant group "{group.name}" created.')
            return redirect('plants:plant_group_detail', group_id=group.id)
    else:
        form = PlantGroupForm()
    basic_fields, advanced_fields = _split_form_fields(form, advanced_names=[])
    return render(
        request,
        'plants/plant_group_form.html',
        {'form': form, 'group_obj': None, 'basic_fields': basic_fields, 'advanced_fields': advanced_fields},
    )


def plant_group_detail_view(request, group_id):
    group = get_object_or_404(PlantGroup, pk=group_id)
    if request.method == 'POST':
        form = PlantGroupForm(request.POST, instance=group)
        if form.is_valid():
            group = form.save()
            messages.success(request, f'Plant group "{group.name}" updated.')
            return redirect('plants:plant_group_detail', group_id=group.id)
    else:
        form = PlantGroupForm(instance=group)
    basic_fields, advanced_fields = _split_form_fields(form, advanced_names=[])
    return render(
        request,
        'plants/plant_group_form.html',
        {'form': form, 'group_obj': group, 'basic_fields': basic_fields, 'advanced_fields': advanced_fields},
    )


@require_POST
def plant_group_delete_view(request, group_id):
    group = get_object_or_404(PlantGroup, pk=group_id)
    name = group.name
    group.delete()
    messages.success(request, f'Plant group "{name}" deleted.')
    return redirect('plants:setup_center')


def devices_center_view(request):
    if request.method == 'POST':
        form = DeviceForm(request.POST)
        if form.is_valid():
            device = form.save()
            messages.success(request, f'Device "{device.device_id}" created.')
            return redirect('plants:device_detail', device_id=device.id)
    else:
        form = DeviceForm()

    devices = Device.objects.select_related('garden').all().order_by('device_id')
    basic_fields, advanced_fields = _split_form_fields(form, advanced_names=[])
    return render(
        request,
        'plants/devices_center.html',
        {
            'form': form,
            'devices': devices,
            'basic_fields': basic_fields,
            'advanced_fields': advanced_fields,
        },
    )


def device_detail_view(request, device_id):
    device = get_object_or_404(Device, pk=device_id)
    if request.method == 'POST':
        form = DeviceForm(request.POST, instance=device)
        if form.is_valid():
            updated = form.save()
            messages.success(request, f'Device "{updated.device_id}" updated.')
            return redirect('plants:device_detail', device_id=updated.id)
    else:
        form = DeviceForm(instance=device)

    basic_fields, advanced_fields = _split_form_fields(form, advanced_names=[])
    context = {
        'form': form,
        'basic_fields': basic_fields,
        'advanced_fields': advanced_fields,
        'device': device,
        'recent_readings': SensorReading.objects.filter(device=device).order_by('-timestamp')[:20],
        'recent_actions': DeviceAction.objects.filter(device=device).order_by('-created_at')[:20],
    }
    return render(request, 'plants/device_form.html', context)


@require_POST
def device_delete_view(request, device_id):
    device = get_object_or_404(Device, pk=device_id)
    label = device.device_id
    device.delete()
    messages.success(request, f'Device "{label}" deleted.')
    return redirect('plants:devices_center')


@require_POST
def device_rotate_key_view(request, device_id):
    device = get_object_or_404(Device, pk=device_id)
    device.api_key = generate_device_api_key()
    device.save(update_fields=['api_key'])
    messages.success(request, f'API key rotated for "{device.device_id}".')
    return redirect('plants:device_detail', device_id=device.id)


def sensor_readings_center_view(request):
    devices = Device.objects.all().order_by('device_id')
    selected_device = request.GET.get('device', '').strip()

    readings = SensorReading.objects.select_related('device').all().order_by('-timestamp')
    if selected_device:
        try:
            readings = readings.filter(device_id=int(selected_device))
        except ValueError:
            messages.error(request, 'Invalid device filter.')
            return redirect('plants:sensor_readings_center')

    context = {
        'devices': devices,
        'selected_device': selected_device,
        'readings': readings[:300],
    }
    return render(request, 'plants/sensor_readings_center.html', context)


def notifications_center_view(request):
    state = request.GET.get('state', 'all').strip().lower()
    notifications = Notification.objects.select_related('plant', 'event').all().order_by('-id')

    if state == 'pending':
        notifications = notifications.filter(sent=False)
    elif state == 'sent':
        notifications = notifications.filter(sent=True)
    elif state == 'failed':
        notifications = notifications.filter(sent=False, attempts__gt=0).exclude(last_error='')

    context = {
        'state': state,
        'notifications': notifications[:300],
        'pending_count': Notification.objects.filter(sent=False).count(),
        'sent_count': Notification.objects.filter(sent=True).count(),
        'failed_count': Notification.objects.filter(sent=False, attempts__gt=0).exclude(last_error='').count(),
    }
    return render(request, 'plants/notifications_center.html', context)


@require_POST
def process_notifications_view(request):
    batch_size = _parse_positive_int(request.POST.get('batch_size'), default=100, lower=1, upper=500)
    max_attempts = _parse_positive_int(request.POST.get('max_attempts'), default=6, lower=1, upper=20)
    result = NotificationDispatcher(max_attempts=max_attempts).dispatch_pending(batch_size=batch_size)
    messages.success(
        request,
        f'Processed {result["processed"]} notifications: {result["sent"]} sent, {result["failed"]} failed.',
    )
    return redirect('plants:notifications_center')


@require_POST
def test_telegram_notification_view(request):
    try:
        NotificationDispatcher().send_telegram_test_message()
    except Exception as exc:
        messages.error(request, f'Telegram test failed: {exc}')
    else:
        messages.success(request, 'Telegram test reminder sent successfully.')
    return redirect('plants:notifications_center')


@require_POST
def retry_notification_view(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id)
    notification.sent = False
    notification.sent_at = None
    notification.attempts = 0
    notification.last_error = ''
    notification.next_attempt_at = timezone.now()
    notification.save(update_fields=['sent', 'sent_at', 'attempts', 'last_error', 'next_attempt_at'])
    messages.success(request, f'Notification #{notification.id} reset for retry.')
    return redirect('plants:notifications_center')


def device_actions_center_view(request):
    state = request.GET.get('state', 'all').strip().lower()
    actions = DeviceAction.objects.select_related('device').all().order_by('-created_at')
    if state in {'pending', 'executed', 'failed'}:
        actions = actions.filter(status=state)

    context = {
        'state': state,
        'actions': actions[:300],
        'pending_count': DeviceAction.objects.filter(status='pending').count(),
        'executed_count': DeviceAction.objects.filter(status='executed').count(),
        'failed_count': DeviceAction.objects.filter(status='failed').count(),
    }
    return render(request, 'plants/device_actions_center.html', context)


@require_POST
def evaluate_automations_view(request):
    result = DeviceAutomationService().evaluate()
    messages.success(
        request,
        f'Evaluated {result["devices_evaluated"]} devices, created {result["actions_created"]} actions.',
    )
    return redirect('plants:device_actions_center')


@require_POST
def process_device_actions_view(request):
    batch_size = _parse_positive_int(request.POST.get('batch_size'), default=100, lower=1, upper=500)
    max_attempts = _parse_positive_int(request.POST.get('max_attempts'), default=6, lower=1, upper=20)
    result = DeviceActionDispatcher(max_attempts=max_attempts).dispatch_pending(batch_size=batch_size)
    messages.success(
        request,
        f'Processed {result["processed"]} actions: {result["executed"]} executed, {result["failed"]} failed.',
    )
    return redirect('plants:device_actions_center')


@require_POST
def retry_device_action_view(request, action_id):
    action = get_object_or_404(DeviceAction, pk=action_id)
    action.status = 'pending'
    action.attempts = 0
    action.last_error = ''
    action.executed_at = None
    action.next_attempt_at = timezone.now()
    action.save(update_fields=['status', 'attempts', 'last_error', 'executed_at', 'next_attempt_at'])
    messages.success(request, f'Action #{action.id} reset for retry.')
    return redirect('plants:device_actions_center')


def plant_detail_view(request, plant_id):
    plant = get_object_or_404(Plant, pk=plant_id)
    if request.method == 'POST':
        form = PlantForm(request.POST, instance=plant)
        if form.is_valid():
            plant = form.save()
            messages.success(request, f'Plant "{plant.name}" updated.')
            return redirect('plants:plant_detail', plant_id=plant.id)
    else:
        form = PlantForm(instance=plant)
    basic_fields, advanced_fields = _split_form_fields(
        form,
        advanced_names={
            'substrate_type',
            'pot_volume_liters',
            'drainage_class',
            'sun_exposure_hours',
            'individual_watering_interval_days',
            'individual_fertilization_interval_days',
            'individual_repotting_interval_days',
            'individual_requires_pre_watering',
            'pre_fertilization_water_gap_days',
            'spring_watering_interval_days',
            'summer_watering_interval_days',
            'fall_watering_interval_days',
            'winter_watering_interval_days',
            'indoor_watering_interval_days',
            'outdoor_watering_interval_days',
            'soil_moisture_wet_threshold',
            'soil_moisture_critical_threshold',
            'last_watered',
            'last_fertilized',
            'last_repotted',
        },
    )
    return render(
        request,
        'plants/plant_form.html',
        {'form': form, 'plant': plant, 'basic_fields': basic_fields, 'advanced_fields': advanced_fields},
    )


@require_POST
def plant_delete_view(request, plant_id):
    plant = get_object_or_404(Plant, pk=plant_id)
    name = plant.name
    plant.delete()
    messages.success(request, f'Plant "{name}" deleted.')
    return redirect('plants:dashboard')


def dashboard_view(request):
    planner = CareTaskPlanner(horizon_days=7, daily_limit=12)
    upcoming_tasks = planner.tasks_in_window()
    overdue = [task for task in upcoming_tasks if task.is_overdue]
    today = timezone.now().date()

    todays_work = [
        task for task in upcoming_tasks
        if task.scheduled_date <= today
    ]
    upcoming_next = [
        task for task in upcoming_tasks
        if task.scheduled_date > today
    ]

    context = {
        'garden_count': Garden.objects.count(),
        'plant_count': Plant.objects.count(),
        'device_count': Device.objects.count(),
        'pending_notifications': Notification.objects.filter(sent=False).count(),
        'pending_actions': DeviceAction.objects.filter(status='pending').count(),
        'open_incidents': PestIncident.objects.exclude(status='resolved').count(),
        'active_rules': PlantCareRule.objects.filter(enabled=True).count(),
        'upcoming_count': len(upcoming_tasks),
        'overdue_count': len(overdue),
        'todays_work': sorted(todays_work, key=lambda task: (not task.is_overdue, task.scheduled_date, task.event_type))[:12],
        'upcoming_next': sorted(upcoming_next, key=lambda task: (task.scheduled_date, task.event_type))[:8],
        'top_event_types': (
            CalendarEvent.objects.values('event_type')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        ),
    }
    return render(request, 'plants/dashboard_summary.html', context)


def calendar_view(request):
    horizon_days = _parse_positive_int(request.GET.get('days'), default=14, lower=1, upper=60)
    daily_limit = _parse_positive_int(request.GET.get('daily_limit'), default=6, lower=1, upper=30)
    optimize = str(request.GET.get('optimize', '')).lower() in {'1', 'true', 'yes', 'on'}

    planner = CareTaskPlanner(horizon_days=horizon_days, daily_limit=daily_limit)
    tasks = planner.tasks_in_window()
    if optimize:
        tasks = HeuristicTaskOptimizer(daily_limit=daily_limit).optimize(tasks, start_date=planner.start_date)

    grouped_tasks = {}
    for task in tasks:
        grouped_tasks.setdefault(task.scheduled_date, [])
        grouped_tasks[task.scheduled_date].append(task)

    days = []
    for offset in range(horizon_days):
        day = planner.start_date + timedelta(days=offset)
        days.append((day, grouped_tasks.get(day, [])))

    context = {
        'days': days,
        'horizon_days': horizon_days,
        'daily_limit': daily_limit,
        'optimize': optimize,
    }
    return render(request, 'plants/calendar.html', context)


def rules_center_view(request):
    if request.method == 'POST':
        scope = request.POST.get('scope', '').strip()
        name = request.POST.get('name', '').strip() or 'Custom Rule'
        target_plant_id = request.POST.get('plant_id')
        target_group_id = request.POST.get('group_id')

        if scope not in {'plant', 'group'}:
            messages.error(request, 'Rule scope must be plant or group.')
            return redirect('plants:rules_center')

        payload = {
            'name': name,
            'scope': scope,
            'enabled': True,
            'priority': _parse_positive_int(request.POST.get('priority'), default=100, lower=1, upper=1000),
            'notes': request.POST.get('notes', '').strip(),
        }
        if scope == 'plant':
            if not target_plant_id:
                messages.error(request, 'Choose a plant target for plant-scope rules.')
                return redirect('plants:rules_center')
            try:
                payload['plant_id'] = int(target_plant_id)
            except ValueError:
                messages.error(request, 'Invalid plant target.')
                return redirect('plants:rules_center')
        else:
            if not target_group_id:
                messages.error(request, 'Choose a group target for group-scope rules.')
                return redirect('plants:rules_center')
            try:
                payload['group_id'] = int(target_group_id)
            except ValueError:
                messages.error(request, 'Invalid group target.')
                return redirect('plants:rules_center')

        numeric_fields = [
            'watering_interval_days',
            'fertilization_interval_days',
            'repotting_interval_days',
            'pre_fertilization_water_gap_days',
            'soil_moisture_wet_threshold',
            'soil_moisture_dry_threshold',
        ]
        for field in numeric_fields:
            raw_value = request.POST.get(field, '').strip()
            if raw_value:
                try:
                    payload[field] = int(raw_value)
                except ValueError:
                    messages.error(request, f'Invalid value for {field}.')
                    return redirect('plants:rules_center')

        requires_pre = request.POST.get('requires_pre_watering', '').strip().lower()
        if requires_pre in {'true', '1', 'yes'}:
            payload['requires_pre_watering'] = True
        elif requires_pre in {'false', '0', 'no'}:
            payload['requires_pre_watering'] = False

        PlantCareRule.objects.create(**payload)
        messages.success(request, 'Care rule created.')
        return redirect('plants:rules_center')

    context = {
        'rules': PlantCareRule.objects.select_related('plant', 'group').all().order_by('priority', 'id'),
        'plants': Plant.objects.select_related('group').all().order_by('name'),
        'groups': PlantGroup.objects.select_related('garden').all().order_by('name'),
    }
    return render(request, 'plants/rules_center.html', context)


def rule_coverage_view(request):
    groups = (
        PlantGroup.objects
        .select_related('garden', 'plant_type')
        .annotate(active_group_rules_count=Count('care_rules', filter=Q(care_rules__enabled=True), distinct=True))
        .order_by('name')
    )
    plants = (
        Plant.objects
        .select_related('group__garden', 'group__plant_type')
        .annotate(active_plant_rules_count=Count('care_rules', filter=Q(care_rules__enabled=True), distinct=True))
        .annotate(active_group_rules_count=Count('group__care_rules', filter=Q(group__care_rules__enabled=True), distinct=True))
        .order_by('name')
    )

    plant_rows = []
    for plant in plants:
        if plant.active_plant_rules_count > 0:
            coverage = 'plant'
        elif plant.active_group_rules_count > 0:
            coverage = 'group'
        else:
            coverage = 'missing'
        plant_rows.append({'plant': plant, 'coverage': coverage})

    missing_plants = [row for row in plant_rows if row['coverage'] == 'missing']
    covered_by_plant = [row for row in plant_rows if row['coverage'] == 'plant']
    covered_by_group = [row for row in plant_rows if row['coverage'] == 'group']
    groups_without_rule = [group for group in groups if group.active_group_rules_count == 0]

    context = {
        'total_plants': len(plant_rows),
        'plants_covered': len(covered_by_plant) + len(covered_by_group),
        'plants_missing': len(missing_plants),
        'covered_by_plant_count': len(covered_by_plant),
        'covered_by_group_count': len(covered_by_group),
        'total_groups': len(groups),
        'groups_with_rule': len(groups) - len(groups_without_rule),
        'groups_without_rule': len(groups_without_rule),
        'missing_plants': missing_plants,
        'groups_without_rule_list': groups_without_rule,
    }
    return render(request, 'plants/rule_coverage.html', context)


def rule_detail_view(request, rule_id):
    rule = get_object_or_404(PlantCareRule, pk=rule_id)
    if request.method == 'POST':
        form = PlantCareRuleForm(request.POST, instance=rule)
        if form.is_valid():
            updated = form.save()
            messages.success(request, f'Rule "{updated.name}" updated.')
            return redirect('plants:rule_detail', rule_id=updated.id)
    else:
        form = PlantCareRuleForm(instance=rule)
    basic_fields, advanced_fields = _split_form_fields(
        form,
        advanced_names={'notes', 'requires_pre_watering', 'pre_fertilization_water_gap_days'},
    )
    return render(
        request,
        'plants/rule_form.html',
        {'form': form, 'rule': rule, 'basic_fields': basic_fields, 'advanced_fields': advanced_fields},
    )


class SensorReadingIngestView(APIView):
    """Ingest a device sensor reading with device-key auth and optional idempotency key."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SensorReadingIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        device_id = payload['device_id']
        device = Device.objects.filter(device_id=device_id).first()
        if not device:
            return Response({'detail': 'Unknown device_id.'}, status=status.HTTP_404_NOT_FOUND)

        provided_key = request.headers.get('X-Device-Key') or request.data.get('api_key') or ''
        if not constant_time_compare(provided_key, device.api_key):
            return Response({'detail': 'Invalid device key.'}, status=status.HTTP_401_UNAUTHORIZED)

        idempotency_key = (
            request.headers.get('X-Idempotency-Key')
            or payload.get('idempotency_key')
            or ''
        ).strip()
        if idempotency_key:
            existing = SensorIngestRecord.objects.select_related('reading').filter(
                device=device,
                idempotency_key=idempotency_key,
            ).first()
            if existing:
                return Response(
                    {
                        'status': 'accepted',
                        'reused': True,
                        'reading_id': existing.reading.id,
                        'device_id': device.device_id,
                        'timestamp': existing.reading.timestamp.isoformat(),
                    },
                    status=status.HTTP_200_OK,
                )

        reading = SensorReading.objects.create(
            device=device,
            temperature=payload.get('temperature'),
            humidity=payload.get('humidity'),
            soil_moisture=payload.get('soil_moisture'),
            light=payload.get('light'),
        )
        if idempotency_key:
            with transaction.atomic():
                ingest_record, created = SensorIngestRecord.objects.get_or_create(
                    device=device,
                    idempotency_key=idempotency_key,
                    defaults={'reading': reading},
                )
            if not created:
                reading.delete()
                reused_reading = ingest_record.reading
                return Response(
                    {
                        'status': 'accepted',
                        'reused': True,
                        'reading_id': reused_reading.id,
                        'device_id': device.device_id,
                        'timestamp': reused_reading.timestamp.isoformat(),
                    },
                    status=status.HTTP_200_OK,
                )
        return Response(
            {
                'status': 'accepted',
                'reused': False,
                'reading_id': reading.id,
                'device_id': device.device_id,
                'timestamp': reading.timestamp.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class GardenViewSet(viewsets.ModelViewSet):
    queryset = Garden.objects.all().order_by('name')
    serializer_class = GardenSerializer


class PlantTypeViewSet(viewsets.ModelViewSet):
    queryset = PlantType.objects.all().order_by('name')
    serializer_class = PlantTypeSerializer


class PlantGroupViewSet(viewsets.ModelViewSet):
    queryset = PlantGroup.objects.select_related('plant_type', 'garden').all().order_by('name')
    serializer_class = PlantGroupSerializer


class PlantViewSet(viewsets.ModelViewSet):
    queryset = Plant.objects.select_related('group__plant_type', 'group__garden').all().order_by('name')
    serializer_class = PlantSerializer


class PlantCareRuleViewSet(viewsets.ModelViewSet):
    queryset = PlantCareRule.objects.select_related('plant', 'group').all().order_by('priority', 'id')
    serializer_class = PlantCareRuleSerializer


class CalendarEventViewSet(viewsets.ModelViewSet):
    queryset = CalendarEvent.objects.select_related('plant').all().order_by('-date', 'id')
    serializer_class = CalendarEventSerializer


class DeviceViewSet(viewsets.ModelViewSet):
    queryset = Device.objects.select_related('garden').all().order_by('device_id')
    serializer_class = DeviceSerializer


class SensorReadingViewSet(viewsets.ModelViewSet):
    queryset = SensorReading.objects.select_related('device').all().order_by('-timestamp')
    serializer_class = SensorReadingSerializer


class PlantStatusLogViewSet(viewsets.ModelViewSet):
    queryset = PlantStatusLog.objects.select_related('plant').all()
    serializer_class = PlantStatusLogSerializer


class DeviceActionViewSet(viewsets.ModelViewSet):
    queryset = DeviceAction.objects.select_related('device').all().order_by('-created_at')
    serializer_class = DeviceActionSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Notification.objects.select_related('plant', 'event').all().order_by('sent', 'next_attempt_at')
    serializer_class = NotificationSerializer


class PestDiseaseProfileViewSet(viewsets.ModelViewSet):
    queryset = PestDiseaseProfile.objects.all().order_by('name')
    serializer_class = PestDiseaseProfileSerializer


class PestIncidentViewSet(viewsets.ModelViewSet):
    queryset = PestIncident.objects.select_related('plant', 'profile').all().order_by('-detected_on', '-id')
    serializer_class = PestIncidentSerializer


class DashboardSummaryAPIView(APIView):
    """Return high-level operations metrics for gardens, tasks, notifications, and incidents."""
    def get(self, request):
        horizon = _parse_positive_int(request.GET.get('days'), default=7, lower=1, upper=60)
        planner = CareTaskPlanner(horizon_days=horizon, daily_limit=12)
        tasks = planner.tasks_in_window()
        overdue = [task for task in tasks if task.is_overdue]

        data = {
            'gardens': Garden.objects.count(),
            'plants': Plant.objects.count(),
            'devices': Device.objects.count(),
            'active_rules': PlantCareRule.objects.filter(enabled=True).count(),
            'pending_notifications': Notification.objects.filter(sent=False).count(),
            'pending_actions': DeviceAction.objects.filter(status='pending').count(),
            'open_incidents': PestIncident.objects.exclude(status='resolved').count(),
            'upcoming_tasks': len(tasks),
            'overdue_tasks': len(overdue),
            'window_days': horizon,
        }
        return Response(data)


class OptimizedPlanAPIView(APIView):
    """Return a planned and load-balanced care task list for a configurable window."""
    def get(self, request):
        horizon_days = _parse_positive_int(request.GET.get('days'), default=14, lower=1, upper=60)
        daily_limit = _parse_positive_int(request.GET.get('daily_limit'), default=6, lower=1, upper=30)
        planner = CareTaskPlanner(horizon_days=horizon_days, daily_limit=daily_limit)
        tasks = planner.tasks_in_window()
        optimized = HeuristicTaskOptimizer(daily_limit=daily_limit).optimize(tasks, start_date=planner.start_date)

        payload = [
            {
                'plant_id': task.plant_id,
                'plant_name': task.plant_name,
                'garden_name': task.garden_name,
                'event_type': task.event_type,
                'due_date': task.due_date.isoformat(),
                'scheduled_date': task.scheduled_date.isoformat(),
                'is_overdue': task.is_overdue,
                'days_overdue': task.days_overdue,
                'adjustment_reason': task.adjustment_reason,
                'soil_moisture': task.soil_moisture,
            }
            for task in optimized
        ]
        return Response({'tasks': payload, 'days': horizon_days, 'daily_limit': daily_limit})


class WeatherForecastAPIView(APIView):
    """Proxy weather forecasts for a latitude/longitude using Open-Meteo."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        lat = request.GET.get('lat')
        lon = request.GET.get('lon')
        if not lat or not lon:
            return Response(
                {'detail': 'Provide lat and lon query params.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        query = urlparse.urlencode(
            {
                'latitude': lat,
                'longitude': lon,
                'daily': 'temperature_2m_max,temperature_2m_min,precipitation_sum',
                'timezone': 'auto',
            }
        )
        url = f'https://api.open-meteo.com/v1/forecast?{query}'
        try:
            with urlrequest.urlopen(url, timeout=10) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
        except (urlerror.URLError, json.JSONDecodeError) as exc:
            return Response(
                {'detail': f'Weather provider error: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(payload)


class AIAssistantComingSoonAPIView(APIView):
    """AI assistant placeholder endpoint for clients to detect upcoming capability."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                'feature': 'ai_assistant',
                'status': 'coming_soon',
                'message': 'AI gardening assistant is planned for a future release.',
                'planned_capabilities': [
                    'Personalized care recommendations',
                    'Plant issue triage from sensor + user data',
                    'Natural-language garden Q&A',
                ],
            },
            status=status.HTTP_200_OK,
        )


class AutomationEvaluateAPIView(APIView):
    """Evaluate latest sensor readings and queue automation actions."""
    def post(self, request):
        service = DeviceAutomationService()
        result = service.evaluate()
        return Response(result, status=status.HTTP_200_OK)


class DeviceActionDispatchAPIView(APIView):
    """Dispatch queued device actions, applying retry/backoff semantics."""
    def post(self, request):
        batch_size = _parse_positive_int(request.data.get('batch_size'), default=100, lower=1, upper=500)
        max_attempts = _parse_positive_int(request.data.get('max_attempts'), default=6, lower=1, upper=20)
        dispatcher = DeviceActionDispatcher(max_attempts=max_attempts)
        result = dispatcher.dispatch_pending(batch_size=batch_size)
        return Response(result, status=status.HTTP_200_OK)


class PestFollowupScheduleAPIView(APIView):
    """Generate follow-up events and notifications for open pest/disease incidents."""
    def post(self, request):
        horizon_days = _parse_positive_int(request.data.get('days'), default=3, lower=0, upper=30)
        service = PestIncidentService()
        result = service.schedule_followups(horizon_days=horizon_days)
        return Response(result, status=status.HTTP_200_OK)


@require_POST
def complete_task(request):
    plant_id = request.POST.get('plant_id')
    event_type = request.POST.get('event_type')
    scheduled_date = request.POST.get('scheduled_date')
    horizon_days = _parse_positive_int(request.POST.get('days'), default=14, lower=1, upper=60)
    daily_limit = _parse_positive_int(request.POST.get('daily_limit'), default=6, lower=1, upper=30)
    optimize = str(request.POST.get('optimize', '')).lower() in {'1', 'true', 'yes', 'on'}

    def _calendar_redirect():
        optimize_query = '&optimize=1' if optimize else ''
        return redirect(f"{reverse('plants:calendar')}?days={horizon_days}&daily_limit={daily_limit}{optimize_query}")

    try:
        plant_id = int(plant_id)
    except (TypeError, ValueError):
        messages.error(request, 'Invalid plant selected.')
        return _calendar_redirect()

    if event_type not in {'water', 'fertilize', 'repot'}:
        messages.error(request, 'Unsupported task type.')
        return _calendar_redirect()

    completed_on = timezone.now().date()
    if scheduled_date:
        try:
            completed_on = date.fromisoformat(scheduled_date)
        except ValueError:
            pass

    plant = get_object_or_404(Plant, pk=plant_id)

    if event_type == 'water':
        plant.last_watered = completed_on
        plant.save(update_fields=['last_watered'])
    elif event_type == 'fertilize':
        plant.last_fertilized = completed_on
        plant.save(update_fields=['last_fertilized'])
    else:
        plant.last_repotted = completed_on
        plant.save(update_fields=['last_repotted'])
        PlantStatusLog.objects.create(
            plant=plant,
            status='repotted',
            date=completed_on,
            notes='Repotted from planner task completion',
        )

    event, _ = CalendarEvent.objects.get_or_create(
        plant=plant,
        event_type=event_type,
        date=completed_on,
        defaults={'notes': 'Completed from care planner'},
    )
    Notification.objects.create(
        plant=plant,
        event=event,
        sent=False,
        next_attempt_at=timezone.now(),
    )

    messages.success(request, f'{plant.name}: marked {event_type} task as completed.')
    return _calendar_redirect()


@require_POST
def toggle_rule(request, rule_id):
    rule = get_object_or_404(PlantCareRule, pk=rule_id)
    rule.enabled = not rule.enabled
    rule.save(update_fields=['enabled'])
    messages.success(request, f'Rule "{rule.name}" is now {"enabled" if rule.enabled else "disabled"}.')
    return redirect('plants:rules_center')


@require_POST
def rule_delete_view(request, rule_id):
    rule = get_object_or_404(PlantCareRule, pk=rule_id)
    name = rule.name
    rule.delete()
    messages.success(request, f'Rule "{name}" deleted.')
    return redirect('plants:rules_center')
