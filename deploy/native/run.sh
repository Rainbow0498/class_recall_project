#!/usr/bin/env bash
set -euo pipefail
# Explicit production values apply to both the service and maintenance commands.
export DEBUG=0 DATA_DIR=/var/lib/biology-workspace PYTHONDONTWRITEBYTECODE=1
app_dir=/opt/biology-workspace
cd "$app_dir"
if [[ "${1:-}" == serve ]]; then
    shift
    exec "$app_dir/.venv/bin/gunicorn" config.wsgi:application \
        --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 60 \
        --access-logfile - --error-logfile - "$@"
fi
exec "$app_dir/.venv/bin/python" manage.py "$@"
