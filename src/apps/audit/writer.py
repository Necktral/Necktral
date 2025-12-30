from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

from .contracts import (validate_event_type, validate_reason_code,
                        validate_subject)
from .models import AuditChainHead, AuditEvent


def _client_ip(request) -> str | None:
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    ip = request.META.get("REMOTE_ADDR")
    return ip or None


def _canon_json(obj: Any) -> str:
    """
    JSON canónico para hashing:
    - sort_keys=True para orden determinista
    - separators sin espacios para estabilidad
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _hmac_hex(message_hex: str) -> str:
    key = settings.AUDIT_HMAC_KEY.encode("utf-8")
    return hmac.new(key, message_hex.encode("utf-8"), hashlib.sha256).hexdigest()


def write_event(
    *,
    request,
    event_type: str,
    reason_code: str = "",
    actor_user=None,
    subject_type: str = "",
    subject_id: str = "",
    device_id: str = "",
    offline_mode: bool = False,
    metadata: dict | None = None,
    before_snapshot: dict | None = None,
    after_snapshot: dict | None = None,
) -> AuditEvent:
    """
    Writer contractual EAU v1:
    - valida catálogos
    - encadena prev_event_hash con AuditChainHead
    - calcula event_hash y signature (HMAC)
    """


    logger.debug(f"write_event llamado: event_type={event_type}, reason_code={reason_code}, subject_type={subject_type}, subject_id={subject_id}")
    validate_event_type(event_type)
    validate_reason_code(reason_code)
    validate_subject(subject_type, subject_id)

    metadata = metadata or {}
    before_snapshot = before_snapshot or {}
    after_snapshot = after_snapshot or {}

    ts: datetime = timezone.now()

    # Contexto de request
    ip = _client_ip(request)
    ua = (request.META.get("HTTP_USER_AGENT", "") if request else "") or ""
    path = (request.path if request else "") or ""
    method = (request.method if request else "") or ""

    with transaction.atomic():
        head, _ = AuditChainHead.objects.select_for_update().get_or_create(id=1)
        prev_hash = head.last_event_hash or ""

        # Payload canónico base (sin signature)
        payload = {
            "event_id": None,  # se llena luego de crear la instancia (UUID ya existe, pero mantenemos consistencia)
            "schema_version": settings.AUDIT_SCHEMA_VERSION,
            "module": settings.AUDIT_MODULE_NAME,

            "event_type": event_type,
            "reason_code": reason_code,

            "subject_type": subject_type,
            "subject_id": subject_id,

            "timestamp_server": ts.isoformat(),

            "actor_user_id": (str(actor_user.id) if actor_user else ""),

            "device_id": device_id,
            "ip_server_seen": (ip or ""),
            "offline_mode": bool(offline_mode),
            "user_agent": ua,
            "path": path,
            "method": method,

            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "metadata": metadata,

            "prev_event_hash": prev_hash,
        }

        # Creamos instancia primero para conocer event_id real (UUID)
        ev = AuditEvent(
            schema_version=settings.AUDIT_SCHEMA_VERSION,
            module=settings.AUDIT_MODULE_NAME,

            event_type=event_type,
            reason_code=reason_code,

            subject_type=subject_type,
            subject_id=subject_id,

            timestamp_server=ts,
            actor_user=actor_user,

            device_id=device_id,
            ip_server_seen=ip,
            offline_mode=bool(offline_mode),
            user_agent=ua,
            path=path,
            method=method,

            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            metadata=metadata,

            prev_event_hash=prev_hash,
        )

        # ya tiene UUID por default (no guardado aún, pero existe)
        payload["event_id"] = str(ev.event_id)

        canonical = _canon_json(payload)
        event_hash = _sha256_hex(canonical)
        signature = _hmac_hex(event_hash)

        ev.event_hash = event_hash
        ev.signature = signature
        ev.save()

        head.last_event_hash = event_hash
        head.save(update_fields=["last_event_hash", "updated_at"])

    return ev
