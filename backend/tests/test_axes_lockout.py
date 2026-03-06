import pytest
from django.contrib.auth import get_user_model
from django.test.utils import override_settings
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent

User = get_user_model()


@pytest.mark.django_db
def test_axes_locks_out_and_creates_lockout_event(settings):
    middleware = list(getattr(settings, "MIDDLEWARE", []))
    if "axes.middleware.AxesMiddleware" not in middleware:
        middleware.append("axes.middleware.AxesMiddleware")

    # Política de test: lockout rápido y determinista
    with override_settings(
        AXES_ENABLED=True,
        AXES_FAILURE_LIMIT=15,
        AXES_COOLOFF_TIME=60,  # minutos (el valor exacto no afecta este test corto)
        MIDDLEWARE=middleware,
    ):
        User.objects.create_user(username="u4", password="pass12345")

        client = APIClient()

        # Fallos previos al lockout: esperamos 401 (credenciales inválidas)
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            r = client.post(
                "/api/auth/login/",
                {"username": "u4", "password": "bad"},
                format="json",
                HTTP_USER_AGENT="pytest",
            )
            assert r.status_code == 401

        # En el intento que alcanza el umbral, Axes puede bloquear inmediatamente.
        # Tu señal user_locked_out lo traduce a Throttled => 429.
        locked = client.post(
            "/api/auth/login/",
            {"username": "u4", "password": "bad"},
            format="json",
            HTTP_USER_AGENT="pytest",
        )
        assert locked.status_code in (401, 429)

        # Evento contractual de lockout
        assert AuditEvent.objects.filter(
            event_type="AUTH_LOCKOUT_TRIGGERED",
            reason_code="RATE_LIMITED",
            subject_id="u4",
        ).exists()
