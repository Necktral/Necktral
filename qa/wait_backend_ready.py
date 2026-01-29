import os
import time


def main() -> int:
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        os.getenv("DJANGO_SETTINGS_MODULE", "config.settings.dev"),
    )

    import django

    django.setup()

    from django.db import connection

    deadline = time.time() + 300  # 5 minutos para entornos CI lentos
    while True:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.audit_auditevent')")
                exists = cursor.fetchone()[0] is not None

            if exists:
                print("backend ready (audit_auditevent exists)")
                return 0
        except Exception:
            pass

        if time.time() > deadline:
            print("timeout waiting for backend/migrations")
            return 1

        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
