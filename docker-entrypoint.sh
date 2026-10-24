#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn --bind 0.0.0.0:8000 --workers "${WEB_CONCURRENCY:-3}" --access-logfile - --error-logfile - shiftr.wsgi:application
