# Contributing to Smart Garden Manager

Thank you for your interest in contributing to **Smart Garden Manager**! This guide will help you get started with development, testing, and contributing features, fixes, or documentation.

---

## 🛠️ Getting Started

1. **Fork the repository**
2. **Clone your fork**:

   ```bash
   git clone https://github.com/yourusername/smart-garden-manager.git
   cd smart-garden-manager
   ```
3. **Create a virtual environment**:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
4. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```
5. **Run initial migrations**:

   ```bash
   python manage.py migrate
   ```
6. **Run the development server**:

   ```bash
   python manage.py runserver
   ```

---

## 📦 Project Structure

* `plants/` — Django app for plant models and scheduling logic
* `devices/` — Future module for device integration (ESP32, Raspberry Pi)
* `core/` — Core models for gardens, notifications, and calendar tasks
* `api/` — Django REST API endpoints
* `frontend/` — (Planned) front-end code for UI/dashboard

---

## 🌱 How to Contribute

### 🧪 Report Bugs

* Use [GitHub Issues](https://github.com/yourrepo/issues) and label it as `bug`

### 💡 Suggest Features

* Use `enhancement` label and describe the feature, use case, and scope

### 💻 Submit Pull Requests

1. Create a new branch:

   ```bash
   git checkout -b feature/my-feature
   ```
2. Make your changes
3. Run tests with `pytest` or `python manage.py test`
4. Commit and push:

   ```bash
   git commit -m "Add my feature"
   git push origin feature/my-feature
   ```
5. Open a PR on GitHub and link to related issues if any

---

## ✅ Code Guidelines

* Follow **PEP8** for Python code.
* Document methods and models clearly.
* Include basic tests for new logic.

---

## 🧪 Testing

Use Django's built-in testing tools or `pytest-django`.

```bash
python manage.py test
```

You may add tests under `plants/tests/`, `core/tests/`, or relevant submodules.

---

## 🤖 CI/CD (Coming Soon)

* GitHub Actions for linting, tests, and Docker build
* Optional device emulation tests (future)

---

## 🙌 Thanks for helping grow the Smart Garden Manager!
