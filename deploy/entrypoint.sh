#!/bin/sh
set -eu
if [ "$#" -gt 0 ]; then
    exec "$@"
fi
python manage.py migrate --noinput
python manage.py init_teacher
python manage.py check --deploy --fail-level WARNING
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 60 --access-logfile - --error-logfile -
