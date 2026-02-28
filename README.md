# 🌿 Smart Garden Manager

**Smart Garden Manager** is a Django-based application designed to intelligently monitor and manage the needs of plants across one or multiple gardens. It allows precise tracking of watering schedules, fertilization, environmental conditions, and plant life cycles, while supporting automation with DIY smart devices like ESP32 and Raspberry Pi.

---

## 🌱 Features

- **Plant Categorization**
  - Organize plants by type, group, or as individual entities.
  - Assign specific care rules per type, group, or individual plant.
  - Store species/cultivar profiles with USDA zone preferences.

- **Smart Watering Scheduler**
  - Track watering intervals and custom water preparation needs.
  - Automatically balance watering schedules across large numbers of plants.
  - Adjust based on individual plant needs and availability of caretakers.
  - Account for substrate, pot size, drainage, sensor trend, and zone profile.
  - Apply explicit rule overrides per plant and per group.

- **Calendar & Notifications**
  - Calendar views for upcoming care tasks: watering, fertilization, repotting, etc.
  - Digest and individual notifications when tasks are near due.
  - Dynamic scheduling based on care rules and environmental data.

- **Multi-Garden Support**
  - Manage multiple gardens (e.g., fruits, flowers) independently.
  - Segmented task and statistics tracking per garden.

- **Device Integration**
  - Integrate with ESP32, Raspberry Pi, and similar devices.
  - Collect data from sensors (temperature, humidity, light).
  - Trigger actions such as:
    - Automatic watering
    - Grow lights
    - Ventilation systems for greenhouses

- **Plant Status Logging**
  - Track lifecycle events: blooming, dormancy, repotting, and fertilizing.
  - Maintain historical logs of each plant's condition and growth milestones.
  - Track pest/disease incidents with follow-up workflows.

---

## 🚧 Roadmap

### ✅ MVP (v0.1)
- [x] Django models for plants, types, groups, and gardens.
- [x] CRUD interface for adding and editing plant data.
- [x] Basic watering schedule logic.
- [x] Static calendar view for task scheduling.
- [x] Support for multiple gardens.

### 🔜 Upcoming Features (v0.2+)
- [x] Dynamic water preparation rules by plant/group/type.
- [x] Fertilization and repotting calendar integration.
- [x] Notifications (email/webhook-ready pipeline) for upcoming tasks.
- [x] Load balancing of plant care tasks across days.
- [x] Plant status tracking (e.g., flowering, dormancy, pest incidents).
- [x] Environmental data logging via connected devices (ESP32/RPi).
- [x] Automation triggers based on sensor data.
- [x] Dashboard with care analytics and upcoming tasks.

### 🧪 Advanced Features (v0.3+)
- [x] Adaptive scheduling using environmental + plant feedback.
- [x] Task optimization using planning logic (heuristic optimizer).
- [x] Mobile app or PWA integration.
- [x] Integration with external APIs for weather/forecasting.
- [x] Open API for external device and app communication.

---

## 🛠️ Tech Stack

- **Backend**: Django / Django REST Framework  
- **Frontend**: (To be defined — could use React, Vue, or Django templates)  
- **Devices**: ESP32, Raspberry Pi (Python-based sensor/automation integration)

---

## ⚙️ Automation Jobs

- Generate upcoming notifications:
  - `cd smart_garden && python manage.py generate_upcoming_notifications --days 2 --daily-limit 12`
- Process pending notifications with retry/backoff:
  - `cd smart_garden && python manage.py process_notifications --batch-size 100 --max-attempts 6`
- Evaluate device automations from latest readings:
  - `cd smart_garden && python manage.py evaluate_automations`
- Process queued device actions with retry/backoff:
  - `cd smart_garden && python manage.py process_device_actions --batch-size 100 --max-attempts 6`
- Schedule pest/disease follow-up reminders:
  - `cd smart_garden && python manage.py schedule_pest_followups --days 3`
- Celery periodic schedules are configured in settings for:
  - Hourly upcoming notification generation
  - 5-minute notification dispatch processing
  - 10-minute automation evaluation
  - 5-minute device action dispatch processing

---

## 🧭 Tools Tutorial

- Web tutorial page: `GET /tutorial/`
- Markdown guide: `docs/tools_tutorial.md`
- Guided onboarding wizard: `GET /welcome/`
- Setup center for non-technical users: `GET /setup/`
- Device management UI: `GET /devices/`
- Sensor monitor UI: `GET /sensor-readings/`
- Device action operations UI: `GET /device-actions/`
- Notifications operations UI: `GET /notifications/`
- Rules center: `GET /rules/` with rule API at `/api/care-rules/`

---

## 🔌 API Highlights

- Sensor ingest: `POST /api/sensor-data/` (`X-Device-Key` required, optional `X-Idempotency-Key`)
- CRUD APIs: `/api/gardens/`, `/api/plant-types/`, `/api/plant-groups/`, `/api/plants/`, `/api/devices/`, etc.
- Care profile extensions: species/cultivar + zone fields in `/api/plant-types/`
- Dashboard summary: `GET /api/dashboard/summary/`
- Optimized care plan: `GET /api/planner/optimize/?days=<n>&daily_limit=<n>`
- Automation run trigger: `POST /api/automation/evaluate/`
- Device action dispatch trigger: `POST /api/device-actions/dispatch/`
- Pest workflows: `/api/pest-profiles/`, `/api/pest-incidents/`, `POST /api/pest/followups/schedule/`
- Weather proxy: `GET /api/weather/forecast/?lat=<lat>&lon=<lon>`
- AI assistant preview (coming soon): `GET /api/ai/assistant/`
- OpenAPI schema: `GET /api/schema/`

---

## 📜 License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## 🤝 Contributions

Contributions are welcome! Feel free to submit issues, feature requests, or pull requests.

## ✅ CI

GitHub Actions CI is configured in `.github/workflows/ci.yml` and runs:
- `python manage.py makemigrations --check --dry-run`
- `python manage.py check`
- `python manage.py test`

---

## 🌐 Future Vision

Imagine a fully automated smart garden system that reacts to plant needs in real-time, adjusts schedules based on growth patterns, and even controls its own environment — that’s the goal.
