#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "config.settings.dev"))

import django  # noqa: E402


def main() -> int:
    django.setup()

    from django.db import connection

    required = {
        ("org", "0004_user_fuel_uom_preference"),
        ("rbac", "0004_role_permission_active_indexes"),
        ("facturacion", "0005_bill_number_unique_nonzero"),
        ("sync_engine", "0001_initial"),
    }

    timeout_seconds = int(os.getenv("WAIT_SCHEMA_TIMEOUT_SECONDS", "90"))
    sleep_seconds = float(os.getenv("WAIT_SCHEMA_SLEEP_SECONDS", "2"))
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT app, name FROM django_migrations")
            rows = {(str(app), str(name)) for app, name in cursor.fetchall()}

        if required.issubset(rows):
            print("backend schema ready")
            return 0

        missing = sorted(required - rows)
        print(f"waiting backend schema... missing={missing}")
        time.sleep(sleep_seconds)

    print("backend schema wait timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
