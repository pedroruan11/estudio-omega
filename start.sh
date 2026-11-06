#!/usr/bin/env bash
# Comando de início no Render: bash start.sh
set -e
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn omega.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60
