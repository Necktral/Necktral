#!/usr/bin/env bash
set -euo pipefail

cd /app/backend

# En PROD: settings prod (tienes fail-fast de llaves en config.settings.prod)
: "${DJANGO_SETTINGS_MODULE:=config.settings.prod}"

# Compat: permite usar POSTGRES_HOST/PORT o DB_HOST/PORT (igual que DEV)
: "${POSTGRES_HOST:=${DB_HOST:-db}}"
: "${POSTGRES_PORT:=${DB_PORT:-5432}}"

export DJANGO_SETTINGS_MODULE

echo "Waiting for postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
python - <<'PY'
import os, time, socket
host = os.getenv("POSTGRES_HOST", "db")
port = int(os.getenv("POSTGRES_PORT", "5432"))
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print("Postgres is up.")
            raise SystemExit(0)
    except OSError:
        time.sleep(1)
print("Postgres not reachable within 60s.")
raise SystemExit(1)
PY

# Migraciones
python src/manage.py migrate --noinput

# Static (Django admin + whitenoise manifest)
python src/manage.py collectstatic --noinput

# Preflight (te detecta cosas de prod rápido)
python src/manage.py check --deploy || true

# Gunicorn
: "${GUNICORN_WORKERS:=3}"
: "${GUNICORN_TIMEOUT:=60}"

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS}" \
  --timeout "${GUNICORN_TIMEOUT}" \
  --access-logfile - \
  --error-logfile -
