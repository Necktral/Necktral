from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from django.db.models import Q
from django.utils import timezone

from apps.common.domain_errors import IntegrationError

from .models import InboxEvent, OutboxEvent

OPERATIONAL_ACCOUNTING_CONTRACT_EVENTS = {
    ("BILLING", "DocumentIssued"),
    ("BILLING", "DocumentVoided"),
    ("INVENTORY", "InventoryMovementPosted"),
    ("INVENTORY", "InventoryAdjusted"),
    ("INVENTORY", "InventoryTransferCompleted"),
    ("PROCUREMENT", "ProcurementDocumentPosted"),
    ("PROCUREMENT", "ProcurementDocumentVoided"),
}


def _normalize_operational_contract_payload(*, source_module: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    if (str(source_module or ""), str(event_type or "")) not in OPERATIONAL_ACCOUNTING_CONTRACT_EVENTS:
        return data

    # Contrato canónico para reconciliación/gates: campos de fuente y referencias contables siempre presentes.
    defaults: dict[str, Any] = {
        "source_module": "",
        "source_type": "",
        "source_id": "",
        "accounting_status": "",
        "accounting_error": "",
        "economic_event_id": None,
        "journal_draft_id": None,
        "journal_entry_id": None,
    }
    for key, default_value in defaults.items():
        data.setdefault(key, default_value)
    return data


def publish_outbox_event(
    *,
    source_module: str,
    event_type: str,
    payload: dict[str, Any],
    request=None,
    company=None,
    branch=None,
    actor_user=None,
    correlation_id: str = "",
    causation_id: str = "",
    device_id: str = "",
    schema_version: int = 1,
) -> OutboxEvent:
    req = request
    effective_company = company or (getattr(req, "company", None) if req is not None else None)
    effective_branch = branch or (getattr(req, "branch", None) if req is not None else None)
    effective_actor = actor_user
    if effective_actor is None and req is not None:
        user = getattr(req, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            effective_actor = user

    corr = correlation_id or (getattr(req, "request_id", "") if req is not None else "")
    cause = causation_id or corr
    req_headers = getattr(req, "headers", {}) if req is not None else {}
    req_meta = getattr(req, "META", {}) if req is not None else {}
    header_device_id = ""
    if hasattr(req_headers, "get"):
        header_device_id = req_headers.get("X-Device-Id", "") or ""
    if not header_device_id and hasattr(req_meta, "get"):
        header_device_id = req_meta.get("HTTP_X_DEVICE_ID", "") or ""
    dev = device_id or header_device_id

    normalized_payload = _normalize_operational_contract_payload(
        source_module=str(source_module or ""),
        event_type=str(event_type or ""),
        payload=payload,
    )

    occurred_at = timezone.now()
    canonical_payload = {
        "schema_version": int(schema_version),
        "contract_version": "1.0",
        "occurred_at": occurred_at.isoformat(),
        "scope": {
            "company_id": getattr(effective_company, "id", None),
            "branch_id": getattr(effective_branch, "id", None),
        },
        "actor": {"user_id": getattr(effective_actor, "id", None)},
        "correlation_id": corr,
        "causation_id": cause,
        "data": normalized_payload,
    }

    return OutboxEvent.objects.create(
        source_module=source_module,
        event_type=event_type,
        schema_version=int(schema_version),
        company=effective_company,
        branch=effective_branch,
        actor_user=effective_actor,
        device_id=dev,
        correlation_id=corr,
        causation_id=cause,
        payload=canonical_payload,
        occurred_at=occurred_at,
    )


def create_or_get_inbox_event(
    *,
    event: OutboxEvent,
    consumer: str,
    status: str = InboxEvent.Status.RECEIVED,
) -> tuple[InboxEvent, bool]:
    """Idempotent inbox upsert that always returns the persisted row."""
    existing = InboxEvent.objects.filter(event_id=event.event_id, consumer=consumer).first()
    if existing is not None:
        return existing, False

    InboxEvent.objects.bulk_create(
        [
            InboxEvent(
                event_id=event.event_id,
                consumer=consumer,
                source_module=event.source_module,
                event_type=event.event_type,
                schema_version=int(event.schema_version or 1),
                payload=event.payload if isinstance(event.payload, dict) else {},
                status=status,
            )
        ],
        ignore_conflicts=True,
    )

    persisted = InboxEvent.objects.filter(event_id=event.event_id, consumer=consumer).first()
    if persisted is None:
        raise IntegrationError(
            "Cannot create or recover InboxEvent.",
            code="INBOX_UPSERT_FAILED",
            context={
                "event_id": str(event.event_id),
                "consumer": str(consumer),
                "source_module": str(event.source_module),
                "event_type": str(event.event_type),
            },
        )
    return persisted, True


def mark_outbox_event_sent(*, event: OutboxEvent, published_at=None) -> OutboxEvent:
    ts = published_at or timezone.now()
    event.status = OutboxEvent.Status.SENT
    event.published_at = ts
    event.last_error = ""
    event.next_attempt_at = None
    event.attempt_count = int(event.attempt_count) + 1
    event.save(update_fields=["status", "published_at", "last_error", "next_attempt_at", "attempt_count"])
    return event


def mark_outbox_event_retry(
    *,
    event: OutboxEvent,
    error: str,
    now=None,
    max_attempts: int = 5,
) -> OutboxEvent:
    ts = now or timezone.now()
    next_attempt_count = int(event.attempt_count) + 1
    event.attempt_count = next_attempt_count
    event.last_error = (error or "")[:255]

    if next_attempt_count >= int(max_attempts):
        event.status = OutboxEvent.Status.FAILED
        event.next_attempt_at = None
        event.save(update_fields=["status", "attempt_count", "last_error", "next_attempt_at"])
        return event

    backoff_minutes = min(2**next_attempt_count, 60)
    event.status = OutboxEvent.Status.PENDING
    event.next_attempt_at = ts + timedelta(minutes=backoff_minutes)
    event.save(update_fields=["status", "attempt_count", "last_error", "next_attempt_at"])
    return event


@dataclass(frozen=True)
class DispatchSummary:
    attempted: int
    sent: int
    retried: int
    failed: int


def dispatch_outbox_events(
    *,
    sender: Callable[[OutboxEvent], None] | None = None,
    limit: int = 100,
    now=None,
    source_module: str = "",
) -> DispatchSummary:
    clock = now or timezone.now()
    publish_fn = sender or (lambda _: None)

    qs = OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING).filter(
        Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=clock)
    )
    if source_module:
        qs = qs.filter(source_module=source_module)
    rows = list(qs.order_by("occurred_at", "id")[: int(limit)])

    attempted = sent = retried = failed = 0
    for row in rows:
        attempted += 1
        try:
            publish_fn(row)
            mark_outbox_event_sent(event=row, published_at=clock)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            mark_outbox_event_retry(event=row, error=str(exc), now=clock, max_attempts=5)
            if row.status == OutboxEvent.Status.FAILED:
                failed += 1
            else:
                retried += 1

    return DispatchSummary(attempted=attempted, sent=sent, retried=retried, failed=failed)
