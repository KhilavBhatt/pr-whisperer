"""
Celery application instance for PR Whisperer.

This is separate from settings.py — Django's settings hold Celery's
configuration values (broker URL, serializers, etc.), but Celery itself
needs an actual app object to register tasks against and to run the
worker process.
"""

import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

# Read CELERY_* settings from Django's settings.py, using the same
# naming convention so we don't duplicate config in two places.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks.py in every installed app (core, integrations, agents)
app.autodiscover_tasks()
