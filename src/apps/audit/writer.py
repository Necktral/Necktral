from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

from .contracts import (validate_event_type, validate_reason_code,
                        validate_subject)
from .models import AuditChainHeadV2, AuditEvent


def _chain_partition_key(request) -> str:
    # Soporta DRF Request (request._request) o request normal
    base_req = getattr(request, "_request", request)
    company = getattr(base_req, "company", None) or getattr(request, "company", None)
    if not company:
        return "SYSTEM"
    return f"COMPANY:{company.id}"


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
    module: str | None = None,   # <-- NUEVO
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

    partition_key = _chain_partition_key(request)
    metadata = metadata or {}
    metadata.setdefault("_chain_partition", partition_key)
    base_req = getattr(request, "_request", request)
    company = getattr(base_req, "company", None) or getattr(request, "company", None)
    branch = getattr(base_req, "branch", None) or getattr(request, "branch", None)
    if company and "company_id" not in metadata:
        metadata["company_id"] = str(company.id)
    if branch and "branch_id" not in metadata:
        metadata["branch_id"] = str(branch.id)
    before_snapshot = before_snapshot or {}
    after_snapshot = after_snapshot or {}

    ts: datetime = timezone.now()

    # Contexto de request
    ip = _client_ip(request)
    ua = (request.META.get("HTTP_USER_AGENT", "") if request else "") or ""
    path = (request.path if request else "") or ""
    method = (request.method if request else "") or ""


    resolved_module = module or settings.AUDIT_MODULE_NAME

    with transaction.atomic():
        try:
            head, _ = AuditChainHeadV2.objects.select_for_update().get_or_create(
                partition_key=partition_key
            )
        except IntegrityError:
            head = AuditChainHeadV2.objects.select_for_update().get(
                partition_key=partition_key
            )
        prev_hash = head.last_event_hash or ""

        payload = {
            "event_id": None,
            "schema_version": settings.AUDIT_SCHEMA_VERSION,
            "module": resolved_module,
            "event_type": event_type,
            "reason_code": reason_code,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "partition_key": partition_key,
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

        ev = AuditEvent(
            schema_version=settings.AUDIT_SCHEMA_VERSION,
            module=resolved_module,
            event_type=event_type,
            reason_code=reason_code,
            subject_type=subject_type,
            subject_id=subject_id,
            partition_key=partition_key,
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
