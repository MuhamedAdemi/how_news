#!/bin/bash
set -e

python manage.py migrate --noinput

if [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py createsuperuser --noinput || echo "Superuser already exists, skipping."
fi

exec gunicorn how_news.wsgi:application --bind "0.0.0.0:${PORT}" --workers 2 --timeout 120
