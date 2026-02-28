# Smart Garden Manager Tools Tutorial

This tutorial gives a practical path for operators and developers to use the platform day to day.

## 1. Use the UI dashboards

- Open `/welcome/` for a guided setup wizard (recommended for first-time users).
- Open `/setup/` to manage gardens, plant types, and plant groups (non-admin flow).
- Open `/devices/` to register and manage devices, including API key rotation.
- Open `/sensor-readings/` to review incoming telemetry.
- Open `/device-actions/` to evaluate automations and dispatch/retry actions.
- Open `/notifications/` to process and retry notifications.
- Open `/dashboard/` for an operations summary (pending actions, incidents, overdue tasks).
- Open `/calendar/` for care tasks (water/fertilize/repot).
- Open `/rules/` to define plant-level and group-level care rules.
- Mark tasks complete to update plant logs and notifications.

## 2. Send sensor data safely

Use:
- `POST /api/sensor-data/`
- Header `X-Device-Key: <device_api_key>`
- Optional header `X-Idempotency-Key: <unique_message_id>`

Example:

```bash
curl -X POST http://localhost:8000/api/sensor-data/ \
  -H "Content-Type: application/json" \
  -H "X-Device-Key: <device_api_key>" \
  -H "X-Idempotency-Key: reading-2026-02-27T23:00:00Z" \
  -d '{"device_id":"ESP32_001","temperature":23.5,"humidity":52,"soil_moisture":480,"light":190}'
```

## 3. Run automation loop

```bash
cd smart_garden
python manage.py evaluate_automations
python manage.py process_device_actions --batch-size 100 --max-attempts 6
```

## 4. Run care notification loop

```bash
cd smart_garden
python manage.py generate_upcoming_notifications --days 2 --daily-limit 12
python manage.py process_notifications --batch-size 100 --max-attempts 6
```

## 5. Run pest follow-up scheduler

```bash
cd smart_garden
python manage.py schedule_pest_followups --days 3
```

## 6. AI feature preview (coming soon)

- UI preview page: `/ai-assistant/`
- API placeholder: `GET /api/ai/assistant/`

The current AI endpoint returns a `coming_soon` response with planned capabilities.
