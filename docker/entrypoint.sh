#!/usr/bin/env bash
set -euo pipefail

cd /app/backend

: "${DJANGO_SETTINGS_MODULE:=config.settings.dev}"

# Compat: permite usar POSTGRES_HOST/PORT o DB_HOST/PORT
: "${POSTGRES_HOST:=${DB_HOST:-db}}"
: "${POSTGRES_PORT:=${DB_PORT:-5432}}"

export DJANGO_SETTINGS_MODULE

# Espera simple a Postgres (sin herramientas extra)
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

# Migraciones automáticas en dev
python src/manage.py migrate --noinput

# Arranque servidor
# - Por defecto: runserver (DX / hot-reload)
# - Para carga/QA: Gunicorn (mejor concurrencia y latencias más estables)
: "${USE_GUNICORN:=0}"

if [[ "${USE_GUNICORN}" == "1" || "${USE_GUNICORN}" == "true" ]]; then
    : "${GUNICORN_WORKERS:=4}"
    : "${GUNICORN_THREADS:=2}"
    : "${GUNICORN_TIMEOUT:=60}"
    : "${GUNICORN_LOG_LEVEL:=info}"
    : "${GUNICORN_KEEPALIVE:=5}"
    : "${GUNICORN_GRACEFUL_TIMEOUT:=30}"
    : "${GUNICORN_BACKLOG:=2048}"

    exec gunicorn config.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS}" \
        --threads "${GUNICORN_THREADS}" \
        --timeout "${GUNICORN_TIMEOUT}" \
        --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT}" \
        --keep-alive "${GUNICORN_KEEPALIVE}" \
        --backlog "${GUNICORN_BACKLOG}" \
        --log-level "${GUNICORN_LOG_LEVEL}" \
        --access-logfile - \
        --error-logfile -
fi

exec python src/manage.py runserver 0.0.0.0:8000
