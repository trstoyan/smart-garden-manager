from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'plants'

router = DefaultRouter()
router.register('gardens', views.GardenViewSet, basename='garden')
router.register('plant-types', views.PlantTypeViewSet, basename='plant-type')
router.register('plant-groups', views.PlantGroupViewSet, basename='plant-group')
router.register('plants', views.PlantViewSet, basename='plant')
router.register('care-rules', views.PlantCareRuleViewSet, basename='care-rule')
router.register('calendar-events', views.CalendarEventViewSet, basename='calendar-event')
router.register('devices', views.DeviceViewSet, basename='device')
router.register('sensor-readings', views.SensorReadingViewSet, basename='sensor-reading')
router.register('plant-status-logs', views.PlantStatusLogViewSet, basename='plant-status-log')
router.register('device-actions', views.DeviceActionViewSet, basename='device-action')
router.register('notifications', views.NotificationViewSet, basename='notification')
router.register('pest-profiles', views.PestDiseaseProfileViewSet, basename='pest-profile')
router.register('pest-incidents', views.PestIncidentViewSet, basename='pest-incident')

urlpatterns = [
    path('welcome/', views.onboarding_wizard_view, name='onboarding_wizard'),
    path('setup/', views.setup_center_view, name='setup_center'),
    path('devices/', views.devices_center_view, name='devices_center'),
    path('devices/<int:device_id>/', views.device_detail_view, name='device_detail'),
    path('devices/<int:device_id>/delete/', views.device_delete_view, name='device_delete'),
    path('devices/<int:device_id>/rotate-key/', views.device_rotate_key_view, name='device_rotate_key'),
    path('sensor-readings/', views.sensor_readings_center_view, name='sensor_readings_center'),
    path('notifications/', views.notifications_center_view, name='notifications_center'),
    path('notifications/process/', views.process_notifications_view, name='process_notifications'),
    path('notifications/<int:notification_id>/retry/', views.retry_notification_view, name='retry_notification'),
    path('device-actions/', views.device_actions_center_view, name='device_actions_center'),
    path('device-actions/process/', views.process_device_actions_view, name='process_device_actions'),
    path('device-actions/evaluate/', views.evaluate_automations_view, name='evaluate_automations'),
    path('device-actions/<int:action_id>/retry/', views.retry_device_action_view, name='retry_device_action'),
    path('tutorial/', views.tools_tutorial_view, name='tools_tutorial'),
    path('ai-assistant/', views.ai_assistant_preview_view, name='ai_assistant_preview'),
    path('gardens/new/', views.garden_create_view, name='garden_create'),
    path('gardens/<int:garden_id>/', views.garden_detail_view, name='garden_detail'),
    path('gardens/<int:garden_id>/delete/', views.garden_delete_view, name='garden_delete'),
    path('plant-types/new/', views.plant_type_create_view, name='plant_type_create'),
    path('plant-types/<int:plant_type_id>/', views.plant_type_detail_view, name='plant_type_detail'),
    path('plant-types/<int:plant_type_id>/delete/', views.plant_type_delete_view, name='plant_type_delete'),
    path('plant-groups/new/', views.plant_group_create_view, name='plant_group_create'),
    path('plant-groups/<int:group_id>/', views.plant_group_detail_view, name='plant_group_detail'),
    path('plant-groups/<int:group_id>/delete/', views.plant_group_delete_view, name='plant_group_delete'),
    path('rules/', views.rules_center_view, name='rules_center'),
    path('rules/coverage/', views.rule_coverage_view, name='rule_coverage'),
    path('rules/<int:rule_id>/', views.rule_detail_view, name='rule_detail'),
    path('rules/<int:rule_id>/toggle/', views.toggle_rule, name='toggle_rule'),
    path('rules/<int:rule_id>/delete/', views.rule_delete_view, name='rule_delete'),
    path('plants/new/', views.plant_create_view, name='plant_create'),
    path('plants/<int:plant_id>/', views.plant_detail_view, name='plant_detail'),
    path('plants/<int:plant_id>/delete/', views.plant_delete_view, name='plant_delete'),
    path('plants/', views.plants_dashboard, name='dashboard'),
    path('dashboard/', views.dashboard_view, name='summary_dashboard'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('tasks/complete/', views.complete_task, name='complete_task'),
    path('api/sensor-data/', views.SensorReadingIngestView.as_view(), name='sensor_data_ingest'),
    path('api/dashboard/summary/', views.DashboardSummaryAPIView.as_view(), name='dashboard_summary_api'),
    path('api/planner/optimize/', views.OptimizedPlanAPIView.as_view(), name='optimized_plan_api'),
    path('api/weather/forecast/', views.WeatherForecastAPIView.as_view(), name='weather_forecast_api'),
    path('api/ai/assistant/', views.AIAssistantComingSoonAPIView.as_view(), name='ai_assistant_api'),
    path('api/automation/evaluate/', views.AutomationEvaluateAPIView.as_view(), name='automation_evaluate_api'),
    path('api/device-actions/dispatch/', views.DeviceActionDispatchAPIView.as_view(), name='device_action_dispatch_api'),
    path('api/pest/followups/schedule/', views.PestFollowupScheduleAPIView.as_view(), name='pest_followup_schedule_api'),
    path('api/', include(router.urls)),
]
