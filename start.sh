#!/bin/bash
set -e

echo "Running database migrations..."
python manage.py migrate --settings=config.settings.production

echo "Starting gunicorn server..."
exec gunicorn --bind 0.0.0.0:8000 --workers 4 --timeout 120 config.wsgi:application
