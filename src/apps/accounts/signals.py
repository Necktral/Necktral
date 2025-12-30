import logging

from axes.signals import user_locked_out
from django.dispatch import receiver

from apps.audit.writer import write_event

logger = logging.getLogger(__name__)


@receiver(user_locked_out)
def axes_locked_out_handler(*args, **kwargs):

    request = kwargs.get("request")
    creds = kwargs.get("credentials") or {}

    username = ""
    if request is not None:
        # 1) request.POST (siempre presente en Axes, pero puede venir vacío en JSON)
        try:
            username = request.POST.get("username", "") or ""
        except Exception:
            username = ""
        # 2) request.data (DRF Request, útil para JSON)
        if not username:
            try:
                username = getattr(request, "data", {}).get("username", "") or ""
            except Exception:
                username = ""

    # 3) Fallback: credentials del signal (puede variar por configuración)
    if not username and isinstance(creds, dict):
        username = str(creds.get("username") or creds.get("user") or "")

    logger.debug(f"axes_locked_out_handler: username extraído: {username}")
    logger.debug(f"axes_locked_out_handler: request: {request}")
    logger.debug(f"axes_locked_out_handler: creds: {creds}")

    # Registrar evento contractual
    ev = write_event(
        request=request,
        event_type="AUTH_LOCKOUT_TRIGGERED",
        reason_code="RATE_LIMITED",
        actor_user=None,
        subject_type="USER",
        subject_id=username,
        metadata={"stage": "lockout"},
    )
    logger.debug(f"axes_locked_out_handler: Evento de lockout escrito: {ev}")

    # Importante: NO lanzar excepción aquí.
    # Axes ya está respondiendo 429 en tu sistema (se ve en el log).
