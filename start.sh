#!/bin/bash
set -e

echo "Running database migrations..."
python manage.py migrate --settings=config.settings.production

# Seed data if SEED_DATA environment variable is set to "true"
if [ "$SEED_DATA" = "true" ]; then
    echo "Seeding database with sample data..."
    python manage.py seed_data --settings=config.settings.production
fi

echo "Starting gunicorn server..."
exec gunicorn --bind 0.0.0.0:8000 --workers 4 --timeout 120 config.wsgi:application
