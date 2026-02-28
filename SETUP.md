# Setting Up the Development Environment

This guide will help you set up a virtual environment and install the required dependencies for the Smart Garden Manager project.

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

## Setting Up a Virtual Environment

1. **Create a virtual environment**:

   ```bash
   # Navigate to the project directory
   cd smart-garden-manager
   
   # Create a virtual environment
   python -m venv .venv
   ```

2. **Activate the virtual environment**:

   On Windows:
   ```bash
   .venv\Scripts\activate
   ```

   On macOS/Linux:
   ```bash
   source .venv/bin/activate
   ```

   You should see the virtual environment name in your terminal prompt, indicating it's active.

3. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

4. **Run migrations**:

   ```bash
   cd smart_garden
   python manage.py migrate
   ```

## Deactivating the Virtual Environment

When you're done working on the project, you can deactivate the virtual environment:

```bash
deactivate
```

## Adding New Dependencies

If you need to add a new dependency to the project:

1. Install it with pip while the virtual environment is active:
   ```bash
   pip install package-name
   ```

2. Update the requirements.txt file:
   ```bash
   pip freeze > requirements.txt
   ```

## Next Steps

Once your environment is set up, refer to the CONTRIBUTING.md file for information on how to start the development server and contribute to the project.

## Optional: Run Background Workers

If you want periodic notification generation/dispatch in development:

```bash
# from smart_garden/
celery -A smart_garden worker -l info
celery -A smart_garden beat -l info
```

You can also run the automation/notification jobs manually:

```bash
python manage.py generate_upcoming_notifications --days 2 --daily-limit 12
python manage.py process_notifications --batch-size 100 --max-attempts 6
python manage.py evaluate_automations
python manage.py process_device_actions --batch-size 100 --max-attempts 6
python manage.py schedule_pest_followups --days 3
```
