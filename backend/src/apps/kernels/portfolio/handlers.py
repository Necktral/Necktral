"""
Financial Portfolio Kernel - Event Handlers

Consumers de eventos de integración que crean obligaciones financieras
automáticamente desde módulos operacionales (Billing, Procurement).

Diseñado para el patrón Outbox/Inbox del Integration Layer.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.modulos.integration.models import InboxEvent, OutboxEvent
from apps.modulos.integration.services import create_or_get_inbox_event
from apps.modulos.parties.models import Party

from .models import PortfolioSettings
from .services import create_payable, create_receivable

logger = logging.getLogger(__name__)

CONSUMER_NAME = "PORTFOLIO"


# ============================================================================
# PROCUREMENT → PAYABLE
# ============================================================================


def handle_procurement_document_posted(event: OutboxEvent) -> dict[str, Any]:
    """
    Consume ProcurementDocumentPosted y crea Payable (CxP).

    Reglas:
    - Solo procesa si PortfolioSettings.sync_with_procurement = True
    - Requiere supplier_party_id en el payload
    - Idempotente via InboxEvent
    """
    inbox, created = create_or_get_inbox_event(
        event=event,
        consumer=CONSUMER_NAME,
        status=InboxEvent.Status.RECEIVED,
    )

    if not created and inbox.status == InboxEvent.Status.PROCESSED:
        return {"ok": True, "already_processed": True, "inbox_id": inbox.id}

    payload = _extract_event_data(event)
    company = event.company
    branch = event.branch

    # Verificar configuración
    settings = PortfolioSettings.get_or_create_for_company(company)
    if not settings.sync_with_procurement:
        _mark_inbox_skipped(inbox, reason="sync_with_procurement=False")
        return {"ok": True, "skipped": True, "reason": "sync_with_procurement disabled"}

    # Validar datos requeridos
    supplier_party_id = payload.get("supplier_party_id")
    if not supplier_party_id:
        _mark_inbox_skipped(inbox, reason="no supplier_party_id in payload")
        return {"ok": True, "skipped": True, "reason": "no supplier_party_id"}

    total = _safe_decimal(payload.get("total"))
    if not total or total <= 0:
        _mark_inbox_error(inbox, error="invalid or zero total amount")
        return {"ok": False, "error": "invalid total amount"}

    # Obtener party
    party = Party.objects.filter(id=int(supplier_party_id), company=company).first()
    if party is None:
        _mark_inbox_error(inbox, error=f"supplier_party {supplier_party_id} not found")
        return {"ok": False, "error": "supplier_party not found"}

    # Calcular fechas
    doc_id = int(payload.get("doc_id", 0))
    issue_date = timezone.localdate()
    credit_days = int(settings.settings_json.get("default_payable_credit_days", 30))
    due_date = issue_date + timedelta(days=credit_days)

    # Crear Payable dentro de transacción
    with transaction.atomic():
        payable = create_payable(
            company=company,
            party=party,
            reference_type="PROCUREMENT",
            reference_id=doc_id,
            principal_amount=total,
            currency=str(payload.get("currency", "NIO")),
            issue_date=issue_date,
            due_date=due_date,
            branch=branch,
            supplier_invoice_number=str(payload.get("supplier_ref", "")),
            metadata={
                "source_event_id": str(event.event_id),
                "procurement_doc_id": doc_id,
                "procurement_series": payload.get("series", ""),
                "procurement_number": payload.get("number"),
            },
        )
        _mark_inbox_processed(inbox, result_id=str(payable.obligation_id))

    logger.info(
        "Portfolio: Created Payable %s from ProcurementDocumentPosted (doc_id=%s)",
        payable.obligation_id,
        doc_id,
    )

    return {
        "ok": True,
        "payable_id": str(payable.obligation_id),
        "amount": str(total),
        "party_id": party.id,
    }


# ============================================================================
# BILLING → RECEIVABLE
# ============================================================================


def handle_billing_document_issued(event: OutboxEvent) -> dict[str, Any]:
    """
    Consume BILLING.DocumentIssued y crea Receivable (CxC).

    Reglas:
    - Solo procesa si PortfolioSettings.sync_with_billing = True
    - Requiere customer_party_id en el payload
    - Solo facturas a crédito (payment_method != CASH/CARD directo)
    - Idempotente via InboxEvent
    """
    inbox, created = create_or_get_inbox_event(
        event=event,
        consumer=CONSUMER_NAME,
        status=InboxEvent.Status.RECEIVED,
    )

    if not created and inbox.status == InboxEvent.Status.PROCESSED:
        return {"ok": True, "already_processed": True, "inbox_id": inbox.id}

    payload = _extract_event_data(event)
    company = event.company
    branch = event.branch

    # Verificar configuración
    settings = PortfolioSettings.get_or_create_for_company(company)
    if not settings.sync_with_billing:
        _mark_inbox_skipped(inbox, reason="sync_with_billing=False")
        return {"ok": True, "skipped": True, "reason": "sync_with_billing disabled"}

    # Verificar si es venta a crédito
    payment_method = str(payload.get("payment_method", "")).strip().upper()
    cash_methods = {"CASH", "CARD", "EFECTIVO", "TARJETA"}
    if payment_method in cash_methods:
        _mark_inbox_skipped(inbox, reason=f"payment_method={payment_method} (cash sale)")
        return {"ok": True, "skipped": True, "reason": "cash sale, no receivable needed"}

    # Validar customer_party_id
    customer_party_id = payload.get("customer_party_id")
    if not customer_party_id:
        _mark_inbox_skipped(inbox, reason="no customer_party_id in payload")
        return {"ok": True, "skipped": True, "reason": "no customer_party_id"}

    total = _safe_decimal(payload.get("total"))
    if not total or total <= 0:
        _mark_inbox_error(inbox, error="invalid or zero total amount")
        return {"ok": False, "error": "invalid total amount"}

    # Obtener party
    party = Party.objects.filter(id=int(customer_party_id), company=company).first()
    if party is None:
        _mark_inbox_error(inbox, error=f"customer_party {customer_party_id} not found")
        return {"ok": False, "error": "customer_party not found"}

    # Calcular fechas
    doc_id = int(payload.get("doc_id", 0))
    issue_date = timezone.localdate()
    credit_days = int(settings.settings_json.get("default_receivable_credit_days", 30))
    due_date = issue_date + timedelta(days=credit_days)

    # Crear Receivable dentro de transacción
    with transaction.atomic():
        receivable = create_receivable(
            company=company,
            party=party,
            reference_type="BILLING",
            reference_id=doc_id,
            principal_amount=total,
            currency=str(payload.get("currency", "NIO")),
            issue_date=issue_date,
            due_date=due_date,
            branch=branch,
            invoice_number=f"{payload.get('series', '')}-{payload.get('number', '')}",
            credit_days=credit_days,
            metadata={
                "source_event_id": str(event.event_id),
                "billing_doc_id": doc_id,
                "billing_series": payload.get("series", ""),
                "billing_number": payload.get("number"),
                "payment_method": payment_method,
                "is_fiscal": payload.get("is_fiscal", False),
            },
        )
        _mark_inbox_processed(inbox, result_id=str(receivable.obligation_id))

    logger.info(
        "Portfolio: Created Receivable %s from DocumentIssued (doc_id=%s)",
        receivable.obligation_id,
        doc_id,
    )

    return {
        "ok": True,
        "receivable_id": str(receivable.obligation_id),
        "amount": str(total),
        "party_id": party.id,
    }


# ============================================================================
# DISPATCH REGISTRY
# ============================================================================

EVENT_HANDLERS: dict[tuple[str, str], Any] = {
    ("PROCUREMENT", "ProcurementDocumentPosted"): handle_procurement_document_posted,
    ("BILLING", "DocumentIssued"): handle_billing_document_issued,
}


def dispatch_portfolio_event(event: OutboxEvent) -> dict[str, Any] | None:
    """
    Punto de entrada único para despachar eventos al Portfolio.

    Returns None si el evento no es de interés para el Portfolio.
    """
    key = (str(event.source_module or ""), str(event.event_type or ""))
    handler = EVENT_HANDLERS.get(key)
    if handler is None:
        return None
    return handler(event)


# ============================================================================
# HELPERS
# ============================================================================


def _extract_event_data(event: OutboxEvent) -> dict[str, Any]:
    """Extrae el dict de datos del payload canónico del OutboxEvent."""
    payload = event.payload
    if isinstance(payload, dict):
        return payload.get("data", payload)
    return {}


def _safe_decimal(value) -> Decimal | None:
    """Convierte un valor a Decimal de forma segura."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _mark_inbox_processed(inbox: InboxEvent, *, result_id: str = "") -> None:
    """Marca InboxEvent como procesado exitosamente."""
    inbox.status = InboxEvent.Status.PROCESSED
    inbox.processed_at = timezone.now()
    inbox.last_error = ""
    inbox.save(update_fields=["status", "processed_at", "last_error"])


def _mark_inbox_skipped(inbox: InboxEvent, *, reason: str = "") -> None:
    """Marca InboxEvent como saltado (no aplica)."""
    inbox.status = InboxEvent.Status.PROCESSED
    inbox.processed_at = timezone.now()
    inbox.last_error = f"SKIPPED: {reason}"
    inbox.save(update_fields=["status", "processed_at", "last_error"])


def _mark_inbox_error(inbox: InboxEvent, *, error: str = "") -> None:
    """Marca InboxEvent como fallido."""
    inbox.status = InboxEvent.Status.FAILED
    inbox.processed_at = timezone.now()
    inbox.last_error = (error or "")[:255]
    inbox.save(update_fields=["status", "processed_at", "last_error"])
