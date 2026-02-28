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
   cd smart_garden
   python manage.py migrate
   ```
6. **Run the development server**:

   ```bash
   python manage.py runserver
   ```

---

## 📦 Project Structure

* `smart_garden/` — Django project root (`manage.py`, settings, app modules)
* `smart_garden/plants/` — Plant models, scheduling logic, tests, and views
* `templates/` — Shared templates used by dashboard and calendar pages
* `docs/` — Supporting documentation (device integration and guides)

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
cd smart_garden
python manage.py test
```

Manual workflow checks can also be run with:

```bash
python manage.py evaluate_automations
python manage.py process_device_actions --batch-size 100 --max-attempts 6
python manage.py process_notifications --batch-size 100 --max-attempts 6
```

You may add tests under `plants/tests/`, `core/tests/`, or relevant submodules.

---

## 🤖 CI/CD (Coming Soon)

* GitHub Actions is configured in `.github/workflows/ci.yml` for migration checks, Django checks, and tests
* Future additions: linting, Docker build, and release automation
* Optional device emulation tests (future)

---

## 🙌 Thanks for helping grow the Smart Garden Manager!
