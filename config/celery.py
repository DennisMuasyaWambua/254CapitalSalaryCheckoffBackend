"""
Celery configuration for 254 Capital Salary Check-Off Loan Management System.
"""

import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('salary_checkoff')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat schedule (periodic tasks)
app.conf.beat_schedule = {
    # Example: Send reminder for upcoming deductions (3 days before deduction date)
    'send-deduction-reminders': {
        'task': 'apps.notifications.tasks.send_deduction_reminders',
        'schedule': crontab(hour=9, minute=0),  # Daily at 9 AM
    },
    # Example: Generate daily reconciliation reports
    'generate-daily-reconciliation-report': {
        'task': 'apps.reconciliation.tasks.generate_daily_report',
        'schedule': crontab(hour=23, minute=0),  # Daily at 11 PM
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f'Request: {self.request!r}')
