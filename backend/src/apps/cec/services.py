from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.common.api_exceptions import ConflictError
from apps.integration.services import publish_outbox_event
from apps.payments.models import CashMovement, CashSession
from modulos.compras.models import PurchaseDocument, PurchaseDocStatus, PurchaseDocType
from modulos.facturacion.models import BillingDocument, BranchFiscalConfig, DocStatus, FiscalMode, FiscalStatus
from modulos.inventarios.models import StockBalance

from .models import CECException, CloseRun

TOLERANCE = Decimal("0.01")
SCORE_WEIGHTS: dict[str, int] = {
    CECException.Severity.CRITICAL: 40,
    CECException.Severity.HIGH: 20,
    CECException.Severity.MEDIUM: 10,
}
OPEN_EXCEPTION_STATUSES = (CECException.Status.OPEN, CECException.Status.IN_PROGRESS)


@dataclass(frozen=True)
class ExecuteCloseRunResult:
    run_id: str
    status: str
    consistency_score: int
    blocking_exceptions_count: int
    exceptions_opened_count: int
    gates: list[dict[str, Any]]
    output_manifest_hash: str


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fingerprint(*, run_id: str, code: str, related_object_type: str, related_object_id: str) -> str:
    raw = f"{run_id}|{code}|{related_object_type}|{related_object_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_close_run_blocking(*, code: str, strict: bool) -> bool:
    if code in ("CASH_DIFFERENCE_NONZERO", "NEGATIVE_STOCK"):
        return True
    if code in ("FISCAL_B_PRINT_FAILED", "FISCAL_B_CONTINGENCY_OPEN"):
        return True
    if code == "PROCUREMENT_STOCK_COST_INTEGRITY":
        return True
    if code in ("DOC_NUMBER_GAP", "BILLING_CASH_MISMATCH"):
        return bool(strict)
    if code == "FISCAL_B_RESERVED_STALE":
        return bool(strict)
    if code in ("PROCUREMENT_DOC_NUMBER_GAP", "PROCUREMENT_SUPPLIER_PAYMENT_MISMATCH"):
        return bool(strict)
    return False


def _register_exception(
    *,
    run: CloseRun,
    code: str,
    severity: str,
    strict: bool,
    related_object_type: str,
    related_object_id: str,
    details_json: dict[str, Any],
) -> tuple[CECException, bool]:
    fp = _fingerprint(
        run_id=str(run.run_id),
        code=code,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
    )
    is_blocking = _is_close_run_blocking(code=code, strict=strict)

    existing = (
        CECException.objects.select_for_update()
        .filter(
            close_run=run,
            fingerprint=fp,
            status__in=OPEN_EXCEPTION_STATUSES,
        )
        .first()
    )
    if existing:
        update_fields: list[str] = []
        if existing.severity != severity:
            existing.severity = severity
            update_fields.append("severity")
        if existing.details_json != details_json:
            existing.details_json = details_json
            update_fields.append("details_json")
        if existing.is_blocking != is_blocking:
            existing.is_blocking = is_blocking
            update_fields.append("is_blocking")
        if update_fields:
            existing.save(update_fields=update_fields)
        return existing, False

    created = CECException.objects.create(
        source_module="CEC",
        code=code,
        severity=severity,
        status=CECException.Status.OPEN,
        company=run.company,
        branch=run.branch,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
        details_json=details_json,
        fingerprint=fp,
        is_blocking=is_blocking,
        close_run=run,
    )
    return created, True


def _scope_filter(*, company, branch) -> dict[str, Any]:
    data = {"company": company}
    if branch is not None:
        data["branch"] = branch
    return data


def _collect_doc_number_gap_issues(*, run: CloseRun, window_start, window_end) -> list[dict[str, Any]]:
    qs = BillingDocument.objects.filter(
        **_scope_filter(company=run.company, branch=run.branch),
        status__in=[DocStatus.ISSUED, DocStatus.VOIDED],
        issued_at__gte=window_start,
        issued_at__lte=window_end,
        number__gt=0,
    )

    issues: list[dict[str, Any]] = []
    grouped_numbers: dict[tuple[str, str], list[int]] = {}
    for row in qs.values("doc_type", "series", "number").order_by("doc_type", "series", "number"):
        grouped_numbers.setdefault((row["doc_type"], row["series"]), []).append(int(row["number"]))

    for (doc_type, series), numbers in grouped_numbers.items():
        if not numbers:
            continue
        unique_numbers = sorted(set(numbers))
        if len(unique_numbers) <= 1:
            continue
        expected = set(range(unique_numbers[0], unique_numbers[-1] + 1))
        missing = sorted(expected - set(unique_numbers))
        if not missing:
            continue
        issues.append(
            {
                "code": "DOC_NUMBER_GAP",
                "severity": CECException.Severity.HIGH,
                "related_object_type": "BILLING_SEQUENCE",
                "related_object_id": f"{doc_type}:{series}",
                "details_json": {
                    "doc_type": doc_type,
                    "series": series,
                    "missing_numbers": missing,
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                },
            }
        )

    duplicates = (
        qs.values("doc_type", "series", "number")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
        .order_by("doc_type", "series", "number")
    )
    for dup in duplicates:
        issues.append(
            {
                "code": "DOC_NUMBER_GAP",
                "severity": CECException.Severity.HIGH,
                "related_object_type": "BILLING_SEQUENCE",
                "related_object_id": f"{dup['doc_type']}:{dup['series']}",
                "details_json": {
                    "doc_type": dup["doc_type"],
                    "series": dup["series"],
                    "duplicate_number": int(dup["number"]),
                    "row_count": int(dup["row_count"]),
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                },
            }
        )

    return issues


def _collect_cash_difference_issues(*, run: CloseRun, window_start, window_end) -> list[dict[str, Any]]:
    qs = CashSession.objects.filter(
        **_scope_filter(company=run.company, branch=run.branch),
        status=CashSession.Status.CLOSED,
        closed_at__gte=window_start,
        closed_at__lte=window_end,
    ).exclude(difference_amount=Decimal("0.00"))

    issues: list[dict[str, Any]] = []
    for session in qs.order_by("id"):
        if abs(Decimal(session.difference_amount)) <= TOLERANCE:
            continue
        issues.append(
            {
                "code": "CASH_DIFFERENCE_NONZERO",
                "severity": CECException.Severity.HIGH,
                "related_object_type": "CASH_SESSION",
                "related_object_id": str(session.id),
                "details_json": {
                    "session_id": session.id,
                    "expected_amount": str(session.expected_amount),
                    "counted_amount": str(session.counted_amount),
                    "difference_amount": str(session.difference_amount),
                },
            }
        )
    return issues


def _collect_billing_cash_mismatch_issues(*, run: CloseRun, window_start, window_end) -> tuple[list[dict[str, Any]], dict[str, str]]:
    doc_filters = {
        **_scope_filter(company=run.company, branch=run.branch),
        "status": DocStatus.ISSUED,
        "issued_at__gte": window_start,
        "issued_at__lte": window_end,
    }
    billing_total = (
        BillingDocument.objects.filter(**doc_filters).aggregate(total=Coalesce(Sum("total"), Value(Decimal("0.00"))))["total"]
        or Decimal("0.00")
    )

    cash_qs = CashMovement.objects.filter(
        session__company=run.company,
        created_at__gte=window_start,
        created_at__lte=window_end,
    )
    if run.branch is not None:
        cash_qs = cash_qs.filter(session__branch=run.branch)

    cash_agg = cash_qs.aggregate(
        income=Coalesce(
            Sum("amount", filter=Q(movement_type=CashMovement.MovementType.INCOME)),
            Value(Decimal("0.00")),
        ),
        expense=Coalesce(
            Sum("amount", filter=Q(movement_type=CashMovement.MovementType.EXPENSE)),
            Value(Decimal("0.00")),
        ),
        refund=Coalesce(
            Sum("amount", filter=Q(movement_type=CashMovement.MovementType.REFUND)),
            Value(Decimal("0.00")),
        ),
    )

    income = Decimal(cash_agg["income"] or Decimal("0.00"))
    expense = Decimal(cash_agg["expense"] or Decimal("0.00"))
    refund = Decimal(cash_agg["refund"] or Decimal("0.00"))
    cash_total = income - expense - refund
    diff = billing_total - cash_total

    metrics = {
        "billing_total": str(billing_total),
        "cash_total": str(cash_total),
        "difference": str(diff),
    }
    if abs(diff) <= TOLERANCE:
        return [], metrics

    return (
        [
            {
                "code": "BILLING_CASH_MISMATCH",
                "severity": CECException.Severity.HIGH,
                "related_object_type": "CLOSE_WINDOW",
                "related_object_id": str(run.run_id),
                "details_json": {
                    **metrics,
                    "tolerance": str(TOLERANCE),
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                },
            }
        ],
        metrics,
    )


def _collect_negative_stock_issues(*, run: CloseRun) -> list[dict[str, Any]]:
    qs = StockBalance.objects.filter(company=run.company, qty_on_hand__lt=Decimal("0.0000"))
    if run.branch is not None:
        qs = qs.filter(branch=run.branch)

    issues: list[dict[str, Any]] = []
    for bal in qs.select_related("warehouse", "item").order_by("id"):
        issues.append(
            {
                "code": "NEGATIVE_STOCK",
                "severity": CECException.Severity.CRITICAL,
                "related_object_type": "STOCK_BALANCE",
                "related_object_id": str(bal.id),
                "details_json": {
                    "stock_balance_id": bal.id,
                    "warehouse_id": bal.warehouse_id,
                    "item_id": bal.item_id,
                    "qty_on_hand": str(bal.qty_on_hand),
                    "avg_cost": str(bal.avg_cost),
                },
            }
        )
    return issues


def _procurement_docs_in_window(*, run: CloseRun, window_start, window_end):
    return PurchaseDocument.objects.filter(
        **_scope_filter(company=run.company, branch=run.branch),
        status__in=[PurchaseDocStatus.POSTED, PurchaseDocStatus.VOIDED],
        posted_at__isnull=False,
        posted_at__gte=window_start,
        posted_at__lte=window_end,
    )


def _has_procurement_docs(*, run: CloseRun, window_start, window_end) -> bool:
    return _procurement_docs_in_window(run=run, window_start=window_start, window_end=window_end).exists()


def _collect_procurement_doc_number_gap_issues(*, run: CloseRun, window_start, window_end) -> list[dict[str, Any]]:
    qs = _procurement_docs_in_window(run=run, window_start=window_start, window_end=window_end).filter(number__gt=0)

    issues: list[dict[str, Any]] = []
    grouped_numbers: dict[tuple[str, str], list[int]] = {}
    for row in qs.values("doc_type", "series", "number").order_by("doc_type", "series", "number"):
        grouped_numbers.setdefault((row["doc_type"], row["series"]), []).append(int(row["number"]))

    for (doc_type, series), numbers in grouped_numbers.items():
        if not numbers:
            continue
        unique_numbers = sorted(set(numbers))
        if len(unique_numbers) <= 1:
            continue
        expected = set(range(unique_numbers[0], unique_numbers[-1] + 1))
        missing = sorted(expected - set(unique_numbers))
        if not missing:
            continue
        issues.append(
            {
                "code": "PROCUREMENT_DOC_NUMBER_GAP",
                "severity": CECException.Severity.HIGH,
                "related_object_type": "PROCUREMENT_SEQUENCE",
                "related_object_id": f"{doc_type}:{series}",
                "details_json": {
                    "doc_type": doc_type,
                    "series": series,
                    "missing_numbers": missing,
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                },
            }
        )

    duplicates = (
        qs.values("doc_type", "series", "number")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
        .order_by("doc_type", "series", "number")
    )
    for dup in duplicates:
        issues.append(
            {
                "code": "PROCUREMENT_DOC_NUMBER_GAP",
                "severity": CECException.Severity.HIGH,
                "related_object_type": "PROCUREMENT_SEQUENCE",
                "related_object_id": f"{dup['doc_type']}:{dup['series']}",
                "details_json": {
                    "doc_type": dup["doc_type"],
                    "series": dup["series"],
                    "duplicate_number": int(dup["number"]),
                    "row_count": int(dup["row_count"]),
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                },
            }
        )
    return issues


def _collect_procurement_stock_cost_integrity_issues(*, run: CloseRun, window_start, window_end) -> list[dict[str, Any]]:
    qs = _procurement_docs_in_window(run=run, window_start=window_start, window_end=window_end).filter(
        doc_type__in=[PurchaseDocType.GOODS_RECEIPT, PurchaseDocType.SUPPLIER_INVOICE]
    )
    issues: list[dict[str, Any]] = []
    for doc in qs.order_by("id"):
        total = Decimal(doc.total or Decimal("0.00"))
        if total > Decimal("0.00"):
            continue
        issues.append(
            {
                "code": "PROCUREMENT_STOCK_COST_INTEGRITY",
                "severity": CECException.Severity.CRITICAL,
                "related_object_type": "PROCUREMENT_DOC",
                "related_object_id": str(doc.id),
                "details_json": {
                    "doc_id": int(doc.id),
                    "doc_type": doc.doc_type,
                    "series": doc.series,
                    "number": int(doc.number),
                    "total": str(doc.total),
                    "message": "Documento de compra de stock/costo con total no positivo.",
                },
            }
        )
    return issues


def _collect_procurement_supplier_payment_mismatch_issues(
    *,
    run: CloseRun,
    window_start,
    window_end,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    qs = _procurement_docs_in_window(run=run, window_start=window_start, window_end=window_end)
    invoice_total = (
        qs.filter(doc_type=PurchaseDocType.SUPPLIER_INVOICE).aggregate(
            total=Coalesce(Sum("total"), Value(Decimal("0.00")))
        )["total"]
        or Decimal("0.00")
    )
    credit_total = (
        qs.filter(doc_type=PurchaseDocType.SUPPLIER_CREDIT_NOTE).aggregate(
            total=Coalesce(Sum("total"), Value(Decimal("0.00")))
        )["total"]
        or Decimal("0.00")
    )
    payment_total = (
        qs.filter(doc_type=PurchaseDocType.SUPPLIER_PAYMENT).aggregate(
            total=Coalesce(Sum("total"), Value(Decimal("0.00")))
        )["total"]
        or Decimal("0.00")
    )
    expected_payable = Decimal(invoice_total) - Decimal(credit_total)
    diff = Decimal(expected_payable) - Decimal(payment_total)

    metrics = {
        "supplier_invoice_total": str(invoice_total),
        "supplier_credit_total": str(credit_total),
        "supplier_payment_total": str(payment_total),
        "expected_payable": str(expected_payable),
        "difference": str(diff),
    }
    if abs(diff) <= TOLERANCE:
        return [], metrics

    return (
        [
            {
                "code": "PROCUREMENT_SUPPLIER_PAYMENT_MISMATCH",
                "severity": CECException.Severity.HIGH,
                "related_object_type": "CLOSE_WINDOW",
                "related_object_id": str(run.run_id),
                "details_json": {
                    **metrics,
                    "tolerance": str(TOLERANCE),
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                },
            }
        ],
        metrics,
    )


def _branch_uses_fiscal_mode_b(*, run: CloseRun) -> bool:
    if run.branch is None:
        return BranchFiscalConfig.objects.filter(company=run.company, fiscal_mode=FiscalMode.B, is_active=True).exists()
    return BranchFiscalConfig.objects.filter(
        company=run.company,
        branch=run.branch,
        fiscal_mode=FiscalMode.B,
        is_active=True,
    ).exists()


def _fiscal_b_docs_in_window(*, run: CloseRun, window_start, window_end):
    qs = BillingDocument.objects.filter(
        **_scope_filter(company=run.company, branch=run.branch),
        status=DocStatus.ISSUED,
        fiscal_mode_resolved=FiscalMode.B,
        issued_at__gte=window_start,
        issued_at__lte=window_end,
    )
    return qs


def _has_fiscal_b_docs(*, run: CloseRun, window_start, window_end) -> bool:
    return _fiscal_b_docs_in_window(run=run, window_start=window_start, window_end=window_end).exists()


def _collect_fiscal_b_print_failed_issues(*, run: CloseRun, window_start, window_end) -> list[dict[str, Any]]:
    qs = _fiscal_b_docs_in_window(run=run, window_start=window_start, window_end=window_end).filter(
        fiscal_status=FiscalStatus.FAILED_PRINT
    )
    issues: list[dict[str, Any]] = []
    for doc in qs.order_by("id"):
        issues.append(
            {
                "code": "FISCAL_B_PRINT_FAILED",
                "severity": CECException.Severity.HIGH,
                "related_object_type": "BILLING_DOC",
                "related_object_id": str(doc.id),
                "details_json": {
                    "doc_id": doc.id,
                    "series": doc.series,
                    "number": doc.number,
                    "fiscal_status": doc.fiscal_status,
                    "last_print_error": doc.last_print_error,
                },
            }
        )
    return issues


def _collect_fiscal_b_contingency_open_issues(*, run: CloseRun, window_start, window_end) -> list[dict[str, Any]]:
    qs = _fiscal_b_docs_in_window(run=run, window_start=window_start, window_end=window_end).filter(
        fiscal_status=FiscalStatus.CONTINGENCY
    )
    issues: list[dict[str, Any]] = []
    for doc in qs.order_by("id"):
        issues.append(
            {
                "code": "FISCAL_B_CONTINGENCY_OPEN",
                "severity": CECException.Severity.HIGH,
                "related_object_type": "BILLING_DOC",
                "related_object_id": str(doc.id),
                "details_json": {
                    "doc_id": doc.id,
                    "series": doc.series,
                    "number": doc.number,
                    "fiscal_status": doc.fiscal_status,
                    "contingency_reason": doc.contingency_reason,
                    "contingency_at": doc.contingency_at.isoformat() if doc.contingency_at else "",
                },
            }
        )
    return issues


def _collect_fiscal_b_reserved_stale_issues(*, run: CloseRun, window_start, window_end) -> list[dict[str, Any]]:
    qs = _fiscal_b_docs_in_window(run=run, window_start=window_start, window_end=window_end).filter(
        fiscal_status=FiscalStatus.NUMBER_RESERVED
    )
    issues: list[dict[str, Any]] = []
    for doc in qs.order_by("id"):
        stale_minutes = 0
        if doc.issued_at:
            delta = window_end - doc.issued_at
            stale_minutes = int(delta.total_seconds() // 60)
        issues.append(
            {
                "code": "FISCAL_B_RESERVED_STALE",
                "severity": CECException.Severity.HIGH,
                "related_object_type": "BILLING_DOC",
                "related_object_id": str(doc.id),
                "details_json": {
                    "doc_id": doc.id,
                    "series": doc.series,
                    "number": doc.number,
                    "fiscal_status": doc.fiscal_status,
                    "stale_minutes": stale_minutes,
                },
            }
        )
    return issues


def _build_consistency_score(*, run: CloseRun) -> int:
    severity_counts = (
        CECException.objects.filter(close_run=run, status__in=OPEN_EXCEPTION_STATUSES)
        .values("severity")
        .annotate(cnt=Count("id"))
    )
    score = 100
    for row in severity_counts:
        severity = row["severity"]
        row_count = int(row["cnt"])
        score -= SCORE_WEIGHTS.get(severity, 0) * row_count
    return max(0, score)


def _build_summary(
    *,
    run: CloseRun,
    final_status: str,
    window_start,
    window_end,
    strict: bool,
    gates: list[dict[str, Any]],
    billing_cash_metrics: dict[str, str],
    procurement_metrics: dict[str, str],
) -> dict[str, Any]:
    active_exceptions: list[dict[str, Any]] = [
        dict(row)
        for row in CECException.objects.filter(close_run=run, status__in=OPEN_EXCEPTION_STATUSES).values(
            "exception_id",
            "code",
            "severity",
            "is_blocking",
            "fingerprint",
        )
    ]
    for ex in active_exceptions:
        ex["exception_id"] = str(ex["exception_id"])
    active_exceptions.sort(key=lambda x: (x.get("fingerprint") or "", x.get("code") or ""))
    return {
        "schema_version": 1,
        "contract_version": "1.0",
        "run_id": str(run.run_id),
        "status": final_status,
        "strict": bool(strict),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "consistency_score": int(run.consistency_score),
        "blocking_exceptions_count": int(run.blocking_exceptions_count),
        "gates": gates,
        "metrics": {
            "billing_cash": billing_cash_metrics,
            "procurement": procurement_metrics,
        },
        "active_exceptions": active_exceptions,
    }


def advance_close_run_state(
    *,
    run: CloseRun,
    target_status: str,
    output_manifest_hash: str | None = None,
    summary_json: dict[str, Any] | None = None,
) -> CloseRun:
    if not run.can_transition_to(target_status):
        raise ConflictError(
            f"Transition not allowed: {run.status} -> {target_status}",
            code="CONFLICT",
        )

    run.status = target_status
    update_fields = ["status", "updated_at"]
    if output_manifest_hash is not None:
        run.output_manifest_hash = output_manifest_hash
        update_fields.append("output_manifest_hash")
    if summary_json is not None:
        run.summary_json = summary_json
        update_fields.append("summary_json")
    if target_status == CloseRun.Status.DELIVERED:
        from django.utils import timezone

        run.completed_at = timezone.now()
        update_fields.append("completed_at")
    run.save(update_fields=update_fields)
    return run


def execute_close_run(
    *,
    run: CloseRun,
    request,
    actor,
    window_start,
    window_end,
    strict: bool = True,
) -> ExecuteCloseRunResult:
    if window_start >= window_end:
        raise ValueError("window_start debe ser menor que window_end")

    with transaction.atomic():
        run = CloseRun.objects.select_for_update().get(pk=run.pk)
        if run.status not in (CloseRun.Status.CREATED, CloseRun.Status.REOPENED_EXCEPTION):
            raise ConflictError(
                "CloseRun solo puede ejecutarse desde CREATED o REOPENED_EXCEPTION.",
                code="CONFLICT",
            )

        run.window_start = window_start
        run.window_end = window_end
        run.save(update_fields=["window_start", "window_end", "updated_at"])
        advance_close_run_state(run=run, target_status=CloseRun.Status.GATHERED)

        doc_gap_issues = _collect_doc_number_gap_issues(run=run, window_start=window_start, window_end=window_end)
        cash_diff_issues = _collect_cash_difference_issues(run=run, window_start=window_start, window_end=window_end)
        mismatch_issues, billing_cash_metrics = _collect_billing_cash_mismatch_issues(
            run=run, window_start=window_start, window_end=window_end
        )
        negative_stock_issues = _collect_negative_stock_issues(run=run)
        procurement_doc_gap_issues: list[dict[str, Any]] = []
        procurement_stock_cost_issues: list[dict[str, Any]] = []
        procurement_payment_mismatch_issues: list[dict[str, Any]] = []
        procurement_metrics: dict[str, str] = {
            "supplier_invoice_total": "0.00",
            "supplier_credit_total": "0.00",
            "supplier_payment_total": "0.00",
            "expected_payable": "0.00",
            "difference": "0.00",
        }
        procurement_enabled = _has_procurement_docs(run=run, window_start=window_start, window_end=window_end)
        if procurement_enabled:
            procurement_doc_gap_issues = _collect_procurement_doc_number_gap_issues(
                run=run,
                window_start=window_start,
                window_end=window_end,
            )
            procurement_stock_cost_issues = _collect_procurement_stock_cost_integrity_issues(
                run=run,
                window_start=window_start,
                window_end=window_end,
            )
            procurement_payment_mismatch_issues, procurement_metrics = _collect_procurement_supplier_payment_mismatch_issues(
                run=run,
                window_start=window_start,
                window_end=window_end,
            )
        fiscal_b_print_failed_issues: list[dict[str, Any]] = []
        fiscal_b_contingency_open_issues: list[dict[str, Any]] = []
        fiscal_b_reserved_stale_issues: list[dict[str, Any]] = []
        fiscal_b_enabled = _branch_uses_fiscal_mode_b(run=run) or _has_fiscal_b_docs(
            run=run,
            window_start=window_start,
            window_end=window_end,
        )
        if fiscal_b_enabled:
            fiscal_b_print_failed_issues = _collect_fiscal_b_print_failed_issues(
                run=run,
                window_start=window_start,
                window_end=window_end,
            )
            fiscal_b_contingency_open_issues = _collect_fiscal_b_contingency_open_issues(
                run=run,
                window_start=window_start,
                window_end=window_end,
            )
            fiscal_b_reserved_stale_issues = _collect_fiscal_b_reserved_stale_issues(
                run=run,
                window_start=window_start,
                window_end=window_end,
            )

        gates = [
            {
                "name": "billing_doc_integrity",
                "passed": len(doc_gap_issues) == 0,
                "severity": CECException.Severity.HIGH,
                "metric": {"issues": len(doc_gap_issues)},
            },
            {
                "name": "cash_session_discipline",
                "passed": len(cash_diff_issues) == 0,
                "severity": CECException.Severity.HIGH,
                "metric": {"issues": len(cash_diff_issues)},
            },
            {
                "name": "billing_vs_cash_reconciliation",
                "passed": len(mismatch_issues) == 0,
                "severity": CECException.Severity.HIGH,
                "metric": billing_cash_metrics,
            },
            {
                "name": "inventory_negative_stock",
                "passed": len(negative_stock_issues) == 0,
                "severity": CECException.Severity.CRITICAL,
                "metric": {"issues": len(negative_stock_issues)},
            },
            {
                "name": "procurement_doc_integrity",
                "passed": len(procurement_doc_gap_issues) == 0,
                "severity": CECException.Severity.HIGH,
                "metric": {"issues": len(procurement_doc_gap_issues), "enabled": procurement_enabled},
            },
            {
                "name": "procurement_stock_cost_integrity",
                "passed": len(procurement_stock_cost_issues) == 0,
                "severity": CECException.Severity.CRITICAL,
                "metric": {"issues": len(procurement_stock_cost_issues), "enabled": procurement_enabled},
            },
            {
                "name": "procurement_supplier_payment_reconciliation",
                "passed": len(procurement_payment_mismatch_issues) == 0,
                "severity": CECException.Severity.HIGH,
                "metric": {**procurement_metrics, "enabled": procurement_enabled},
            },
            {
                "name": "fiscal_b_print_failed",
                "passed": len(fiscal_b_print_failed_issues) == 0,
                "severity": CECException.Severity.HIGH,
                "metric": {"issues": len(fiscal_b_print_failed_issues), "enabled": fiscal_b_enabled},
            },
            {
                "name": "fiscal_b_contingency_open",
                "passed": len(fiscal_b_contingency_open_issues) == 0,
                "severity": CECException.Severity.HIGH,
                "metric": {"issues": len(fiscal_b_contingency_open_issues), "enabled": fiscal_b_enabled},
            },
            {
                "name": "fiscal_b_reserved_stale",
                "passed": len(fiscal_b_reserved_stale_issues) == 0,
                "severity": CECException.Severity.HIGH,
                "metric": {"issues": len(fiscal_b_reserved_stale_issues), "enabled": fiscal_b_enabled},
            },
        ]

        issues = (
            doc_gap_issues
            + cash_diff_issues
            + mismatch_issues
            + negative_stock_issues
            + procurement_doc_gap_issues
            + procurement_stock_cost_issues
            + procurement_payment_mismatch_issues
            + fiscal_b_print_failed_issues
            + fiscal_b_contingency_open_issues
            + fiscal_b_reserved_stale_issues
        )
        exceptions_opened_count = 0
        for issue in issues:
            _, created = _register_exception(
                run=run,
                code=issue["code"],
                severity=issue["severity"],
                strict=bool(strict),
                related_object_type=issue["related_object_type"],
                related_object_id=issue["related_object_id"],
                details_json=issue["details_json"],
            )
            if created:
                exceptions_opened_count += 1

        advance_close_run_state(run=run, target_status=CloseRun.Status.VALIDATED)

        active_exceptions = CECException.objects.filter(close_run=run, status__in=OPEN_EXCEPTION_STATUSES)
        blocking_count = active_exceptions.filter(is_blocking=True).count()
        run.blocking_exceptions_count = int(blocking_count)
        run.consistency_score = _build_consistency_score(run=run)
        run.save(update_fields=["blocking_exceptions_count", "consistency_score", "updated_at"])

        final_status = CloseRun.Status.PACKAGED
        if blocking_count > 0:
            final_status = CloseRun.Status.REOPENED_EXCEPTION

        summary_payload = _build_summary(
            run=run,
            final_status=final_status,
            window_start=window_start,
            window_end=window_end,
            strict=bool(strict),
            gates=gates,
            billing_cash_metrics=billing_cash_metrics,
            procurement_metrics=procurement_metrics,
        )
        output_manifest_hash = _json_hash(summary_payload)
        advance_close_run_state(
            run=run,
            target_status=final_status,
            output_manifest_hash=output_manifest_hash,
            summary_json=summary_payload,
        )

        publish_outbox_event(
            request=request,
            source_module="CEC",
            event_type="CloseRunExecuted",
            payload={
                "run_id": str(run.run_id),
                "status": run.status,
                "strict": bool(strict),
                "consistency_score": int(run.consistency_score),
                "blocking_exceptions_count": int(run.blocking_exceptions_count),
                "output_manifest_hash": run.output_manifest_hash,
            },
            actor_user=actor,
            company=run.company,
            branch=run.branch,
        )
        if run.status == CloseRun.Status.REOPENED_EXCEPTION:
            publish_outbox_event(
                request=request,
                source_module="CEC",
                event_type="CloseRunBlocked",
                payload={
                    "run_id": str(run.run_id),
                    "blocking_exceptions_count": int(run.blocking_exceptions_count),
                    "consistency_score": int(run.consistency_score),
                },
                actor_user=actor,
                company=run.company,
                branch=run.branch,
            )
        if run.status == CloseRun.Status.PACKAGED:
            publish_outbox_event(
                request=request,
                source_module="CEC",
                event_type="CloseRunPackaged",
                payload={
                    "run_id": str(run.run_id),
                    "output_manifest_hash": run.output_manifest_hash,
                    "consistency_score": int(run.consistency_score),
                },
                actor_user=actor,
                company=run.company,
                branch=run.branch,
            )

        return ExecuteCloseRunResult(
            run_id=str(run.run_id),
            status=run.status,
            consistency_score=int(run.consistency_score),
            blocking_exceptions_count=int(run.blocking_exceptions_count),
            exceptions_opened_count=int(exceptions_opened_count),
            gates=gates,
            output_manifest_hash=run.output_manifest_hash,
        )
