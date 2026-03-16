from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from apps.accounting.models import EconomicEvent, JournalDraft, JournalEntry, PostingRuleSet
from apps.accounting.services import (
    post_journal_drafts,
    project_shadow_ledger_for_run,
    seed_posting_rules_v1_for_company,
)
from apps.cec.models import CECException, CloseRun
from apps.iam.models import OrgUnit
from apps.integration.models import InboxEvent, OutboxEvent
from apps.integration.services import publish_outbox_event
from apps.rbac.models import Permission

from .models import PurchaseDocument, PurchaseDocStatus, PurchaseDocType
from .services import create_purchase_draft, post_purchase_document

OPEN_EXCEPTION_STATUSES = (CECException.Status.OPEN, CECException.Status.IN_PROGRESS)
PHASE10_REQUIRED_PERMISSIONS = [
    "procurement.doc.create",
    "procurement.doc.read",
    "procurement.doc.post",
    "procurement.doc.void",
]


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _signed_hash(payload: dict[str, Any], *, secret: str = "") -> tuple[str, str, str]:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    if secret:
        sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        return digest, sig, "hmac-sha256"
    return digest, digest, "sha256"


def build_phase10_evidence(*, payload: dict[str, Any], secret: str = "") -> dict[str, Any]:
    digest, signature, signature_type = _signed_hash(payload, secret=secret)
    return {
        **payload,
        "evidence_hash": digest,
        "signature": signature,
        "signature_type": signature_type,
    }


def _resolve_scope(*, company_id: int, branch_id: int) -> tuple[OrgUnit, OrgUnit]:
    company = OrgUnit.objects.filter(
        id=int(company_id),
        unit_type=OrgUnit.UnitType.COMPANY,
        is_active=True,
    ).first()
    if company is None:
        raise ValueError(f"company inválida o inactiva: {company_id}")
    branch = OrgUnit.objects.filter(
        id=int(branch_id),
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        is_active=True,
    ).first()
    if branch is None:
        raise ValueError(f"branch inválida o inactiva para company={company_id}: {branch_id}")
    return company, branch


def _system_request(*, company: OrgUnit, branch: OrgUnit, user, request_id: str):
    return SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        request_id=request_id,
        data={},
        META={},
        headers={},
        path="/management/certify_phase10_procurement_run",
        method="SYSTEM",
    )


def _ensure_system_user(*, company_id: int, branch_id: int):
    User = get_user_model()
    username = f"phase10_certifier_c{company_id}_b{branch_id}"
    existing = User.objects.filter(username=username).first()
    if existing is not None:
        return existing
    return User.objects.create_user(
        username=username,
        email=f"{username}@system.local",
        password=uuid.uuid4().hex,
    )


def collect_phase10_env_manifest(*, company_id: int, branch_id: int) -> dict[str, Any]:
    company, branch = _resolve_scope(company_id=company_id, branch_id=branch_id)

    migrations = list(MigrationRecorder(connection).migration_qs.values_list("app", "name").order_by("app", "name"))
    migration_ids = [f"{app}.{name}" for app, name in migrations]
    migrations_hash = hashlib.sha256("\n".join(migration_ids).encode("utf-8")).hexdigest()

    permissions_rows: list[dict[str, Any]] = []
    found_codes = set()
    for row in Permission.objects.filter(code__in=PHASE10_REQUIRED_PERMISSIONS).order_by("code"):
        found_codes.add(row.code)
        permissions_rows.append({"code": row.code, "is_active": bool(row.is_active)})
    for missing in sorted(set(PHASE10_REQUIRED_PERMISSIONS) - found_codes):
        permissions_rows.append({"code": missing, "is_active": False})
    permissions_hash = _json_hash({"rows": permissions_rows})

    rules_rows = list(
        PostingRuleSet.objects.filter(scope_company=company, status=PostingRuleSet.Status.ACTIVE)
        .order_by("code", "-version", "-updated_at")
        .values("code", "version", "status", "scope_company_id")
    )
    rules_hash = _json_hash({"rows": rules_rows})

    procurement_state = {
        "docs_total": int(PurchaseDocument.objects.filter(company=company, branch=branch).count()),
        "docs_draft": int(
            PurchaseDocument.objects.filter(company=company, branch=branch, status=PurchaseDocStatus.DRAFT).count()
        ),
        "docs_posted": int(
            PurchaseDocument.objects.filter(company=company, branch=branch, status=PurchaseDocStatus.POSTED).count()
        ),
        "docs_voided": int(
            PurchaseDocument.objects.filter(company=company, branch=branch, status=PurchaseDocStatus.VOIDED).count()
        ),
    }
    procurement_state["hash"] = _json_hash(procurement_state)

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(dt_timezone.utc).isoformat(),
        "pilot_scope": {"company_id": int(company.id), "branch_id": int(branch.id)},
        "migrations": {"count": len(migration_ids), "hash": migrations_hash},
        "required_permissions": {"count": len(permissions_rows), "hash": permissions_hash, "items": permissions_rows},
        "posting_rules": {"count": len(rules_rows), "hash": rules_hash, "items": rules_rows},
        "procurement_state": procurement_state,
    }
    manifest["parity_fingerprint"] = _json_hash(
        {
            "migrations_hash": migrations_hash,
            "permissions_hash": permissions_hash,
            "rules_hash": rules_hash,
            "procurement_state_hash": procurement_state["hash"],
        }
    )
    return manifest


def compare_phase10_env_manifests(*, left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, str]]:
    checks = [
        ("migrations.hash", (left.get("migrations") or {}).get("hash"), (right.get("migrations") or {}).get("hash")),
        (
            "required_permissions.hash",
            (left.get("required_permissions") or {}).get("hash"),
            (right.get("required_permissions") or {}).get("hash"),
        ),
        ("posting_rules.hash", (left.get("posting_rules") or {}).get("hash"), (right.get("posting_rules") or {}).get("hash")),
        (
            "procurement_state.hash",
            (left.get("procurement_state") or {}).get("hash"),
            (right.get("procurement_state") or {}).get("hash"),
        ),
        ("parity_fingerprint", left.get("parity_fingerprint"), right.get("parity_fingerprint")),
    ]
    mismatches: list[dict[str, str]] = []
    for field, lval, rval in checks:
        if lval != rval:
            mismatches.append({"field": field, "left": str(lval), "right": str(rval)})
    return mismatches


def collect_phase10_operational_health(
    *,
    company_id: int,
    branch_id: int,
    consumer: str = "accounting.projector",
) -> dict[str, int]:
    company, branch = _resolve_scope(company_id=company_id, branch_id=branch_id)
    inbox_failed_count = InboxEvent.objects.filter(consumer=consumer, status=InboxEvent.Status.FAILED).count()
    outbox_failed_count = OutboxEvent.objects.filter(
        company=company,
        branch=branch,
        source_module__in=["PROCUREMENT", "ACCOUNTING", "CEC"],
        status=OutboxEvent.Status.FAILED,
    ).count()
    open_procurement_drafts_count = PurchaseDocument.objects.filter(
        company=company,
        branch=branch,
        status=PurchaseDocStatus.DRAFT,
    ).count()
    open_procurement_blocking_exceptions_count = CECException.objects.filter(
        company=company,
        branch=branch,
        source_module="ACCOUNTING",
        status__in=OPEN_EXCEPTION_STATUSES,
        is_blocking=True,
        code__in=["SHADOW_RULE_NOT_FOUND", "SHADOW_DRAFT_INVALID", "SHADOW_RULESET_NOT_FOUND"],
    ).count()
    return {
        "inbox_failed_count": int(inbox_failed_count),
        "outbox_failed_count": int(outbox_failed_count),
        "open_procurement_drafts_count": int(open_procurement_drafts_count),
        "open_procurement_blocking_exceptions_count": int(open_procurement_blocking_exceptions_count),
    }


def _projection_counts(*, company: OrgUnit, run_id: str) -> dict[str, int]:
    economic_events = EconomicEvent.objects.filter(company=company, close_run_id=str(run_id), source_module="PROCUREMENT")
    drafts = JournalDraft.objects.filter(close_run_id=str(run_id), economic_event__source_module="PROCUREMENT")
    posted_entries = JournalEntry.objects.filter(company=company, draft__in=drafts, is_posted=True)
    open_blocking = CECException.objects.filter(
        close_run__run_id=run_id,
        source_module="ACCOUNTING",
        status__in=OPEN_EXCEPTION_STATUSES,
        is_blocking=True,
    )
    return {
        "economic_events": int(economic_events.count()),
        "journal_drafts_total": int(drafts.count()),
        "journal_drafts_validated": int(drafts.filter(state=JournalDraft.State.VALIDATED).count()),
        "journal_drafts_exception": int(drafts.filter(state=JournalDraft.State.EXCEPTION).count()),
        "journal_entries_posted": int(posted_entries.count()),
        "blocking_exceptions": int(open_blocking.count()),
    }


def _cert_manifest_hash(*, run: CloseRun, counts: dict[str, int]) -> str:
    payload = {
        "run_id": str(run.run_id),
        "close_run_status": str(run.status),
        "output_manifest_hash": str(run.output_manifest_hash or ""),
        "counts": counts,
    }
    return _json_hash(payload)


@dataclass(frozen=True)
class Phase10CertificationResult:
    run_id: str
    passed: bool
    blocked: bool
    deterministic_replay: bool
    close_run_status: str
    first_manifest_hash: str
    second_manifest_hash: str
    first_counts: dict[str, int]
    second_counts: dict[str, int]
    posting_first: dict[str, Any]
    posting_second: dict[str, Any]
    projection_first: dict[str, int]
    projection_second: dict[str, int]
    pilot_scope: dict[str, int]
    go_live_passed: bool
    doc_type: str


def certify_phase10_procurement_run(
    *,
    company_id: int,
    branch_id: int,
    expect_blocked: bool = False,
) -> Phase10CertificationResult:
    company, branch = _resolve_scope(company_id=company_id, branch_id=branch_id)
    cert_user = _ensure_system_user(company_id=int(company.id), branch_id=int(branch.id))
    seed_posting_rules_v1_for_company(company=company)

    request = _system_request(
        company=company,
        branch=branch,
        user=cert_user,
        request_id=f"phase10-cert-{uuid.uuid4().hex[:12]}",
    )

    doc_type = PurchaseDocType.ADJUSTMENT if expect_blocked else PurchaseDocType.SUPPLIER_INVOICE
    doc_seed = uuid.uuid4().hex[:12]
    draft = create_purchase_draft(
        request=request,
        actor=cert_user,
        doc_type=doc_type,
        series="P",
        currency="NIO",
        supplier_name=f"PROC-CERT-{doc_seed}",
        supplier_ref=f"SUP-{doc_seed}",
        external_ref=f"EXT-{doc_seed}",
        subtotal=Decimal("100.00"),
        tax_total=Decimal("15.00"),
        total=Decimal("115.00"),
        idempotency_key=f"phase10-cert-{doc_seed}",
    )
    post_purchase_document(request=request, actor=cert_user, doc_id=int(draft.doc_id))
    doc = PurchaseDocument.objects.get(id=int(draft.doc_id))

    now = timezone.now()
    anchor = doc.posted_at or now
    window_start = anchor - timedelta(seconds=1)
    window_end = anchor + timedelta(seconds=1)
    run = CloseRun.objects.create(
        company=company,
        branch=branch,
        run_type=CloseRun.RunType.DAILY,
        status=CloseRun.Status.PACKAGED,
        window_start=window_start,
        window_end=window_end,
        output_manifest_hash="",
        summary_json={
            "schema_version": 1,
            "source": "phase10_certification",
            "doc_id": int(doc.id),
            "window_anchor": anchor.isoformat(),
        },
        created_by=cert_user,
    )
    publish_outbox_event(
        source_module="CEC",
        event_type="CloseRunPackaged",
        payload={"run_id": str(run.run_id), "output_manifest_hash": str(run.output_manifest_hash or "")},
        company=company,
        branch=branch,
        actor_user=cert_user,
    )

    first_counts: dict[str, int]
    second_counts: dict[str, int]
    first_posting_payload: dict[str, Any]
    second_posting_payload: dict[str, Any]
    first_projection_payload: dict[str, Any]
    second_projection_payload: dict[str, Any]
    first_manifest_hash: str
    second_manifest_hash: str
    blocked: bool
    deterministic: bool
    scenario_ok: bool

    try:
        if expect_blocked:
            # Bloqueo controlado: desactivar reglas activas para esta compañía,
            # forzando SHADOW_RULESET_NOT_FOUND en la proyección.
            PostingRuleSet.objects.filter(
                scope_company=company,
                status=PostingRuleSet.Status.ACTIVE,
            ).update(status=PostingRuleSet.Status.DEPRECATED)

        projection_first = project_shadow_ledger_for_run(run_id=str(run.run_id), company_id=int(company.id))
        run.refresh_from_db()
        if expect_blocked:
            first_posting_payload = {
                "attempted": 0,
                "approved": 0,
                "posted": 0,
                "skipped": 0,
                "failed": 0,
                "errors": [],
            }
        else:
            if run.status == CloseRun.Status.PACKAGED:
                posting_first = post_journal_drafts(
                    company_id=int(company.id),
                    run_id=str(run.run_id),
                    limit=5000,
                    require_approved=False,
                    auto_approve=False,
                )
                first_posting_payload = {
                    "attempted": int(posting_first.attempted),
                    "approved": int(posting_first.approved),
                    "posted": int(posting_first.posted),
                    "skipped": int(posting_first.skipped),
                    "failed": int(posting_first.failed),
                    "errors": posting_first.errors,
                }
            else:
                first_posting_payload = {
                    "attempted": 0,
                    "approved": 0,
                    "posted": 0,
                    "skipped": 0,
                    "failed": 0,
                    "errors": [f"SKIPPED_NON_PACKAGED:{run.status}"],
                }
        first_counts = _projection_counts(company=company, run_id=str(run.run_id))
        first_projection_payload = {
            "run_id": str(projection_first.run_id),
            "close_run_status": str(projection_first.close_run_status),
            "economic_events_created": int(projection_first.economic_events_created),
            "journal_drafts_generated": int(projection_first.journal_drafts_generated),
            "exceptions_opened": int(projection_first.exceptions_opened),
            "blocked": bool(projection_first.blocked),
        }
        first_manifest_hash = _cert_manifest_hash(run=run, counts=first_counts)

        if expect_blocked:
            # El run ya no está PACKAGED después del bloqueo; segunda pasada se valida
            # con re-lectura de estado/cuentas (no reproyección).
            run.refresh_from_db()
            second_counts = _projection_counts(company=company, run_id=str(run.run_id))
            second_posting_payload = {
                "attempted": 0,
                "approved": 0,
                "posted": 0,
                "skipped": 0,
                "failed": 0,
                "errors": [],
            }
            second_projection_payload = {
                "run_id": str(run.run_id),
                "close_run_status": str(run.status),
                "economic_events_created": 0,
                "journal_drafts_generated": 0,
                "exceptions_opened": 0,
                "blocked": bool(run.status == CloseRun.Status.REOPENED_EXCEPTION),
            }
            second_manifest_hash = _cert_manifest_hash(run=run, counts=second_counts)
            deterministic = (
                first_counts == second_counts
                and first_manifest_hash == second_manifest_hash
                and int(second_posting_payload.get("posted") or 0) == 0
                and int(second_posting_payload.get("failed") or 0) == 0
            )
        else:
            run.refresh_from_db()
            if run.status == CloseRun.Status.PACKAGED:
                projection_second = project_shadow_ledger_for_run(run_id=str(run.run_id), company_id=int(company.id))
                run.refresh_from_db()
                posting_second = post_journal_drafts(
                    company_id=int(company.id),
                    run_id=str(run.run_id),
                    limit=5000,
                    require_approved=False,
                    auto_approve=False,
                )
                second_posting_payload = {
                    "attempted": int(posting_second.attempted),
                    "approved": int(posting_second.approved),
                    "posted": int(posting_second.posted),
                    "skipped": int(posting_second.skipped),
                    "failed": int(posting_second.failed),
                    "errors": posting_second.errors,
                }
                projection_second_created = int(projection_second.economic_events_created)
                projection_second_drafts = int(projection_second.journal_drafts_generated)
                projection_second_exceptions = int(projection_second.exceptions_opened)
                posting_second_posted = int(posting_second.posted)
                posting_second_failed = int(posting_second.failed)
                second_projection_payload = {
                    "run_id": str(projection_second.run_id),
                    "close_run_status": str(projection_second.close_run_status),
                    "economic_events_created": int(projection_second.economic_events_created),
                    "journal_drafts_generated": int(projection_second.journal_drafts_generated),
                    "exceptions_opened": int(projection_second.exceptions_opened),
                    "blocked": bool(projection_second.blocked),
                }
            else:
                second_posting_payload = {
                    "attempted": 0,
                    "approved": 0,
                    "posted": 0,
                    "skipped": 0,
                    "failed": 0,
                    "errors": [f"SKIPPED_NON_PACKAGED:{run.status}"],
                }
                projection_second_created = 0
                projection_second_drafts = 0
                projection_second_exceptions = 0
                posting_second_posted = 0
                posting_second_failed = 0
                second_projection_payload = {
                    "run_id": str(run.run_id),
                    "close_run_status": str(run.status),
                    "economic_events_created": 0,
                    "journal_drafts_generated": 0,
                    "exceptions_opened": 0,
                    "blocked": bool(run.status == CloseRun.Status.REOPENED_EXCEPTION),
                }
            second_counts = _projection_counts(company=company, run_id=str(run.run_id))
            second_manifest_hash = _cert_manifest_hash(run=run, counts=second_counts)
            deterministic = (
                first_counts == second_counts
                and first_manifest_hash == second_manifest_hash
                and int(projection_second_created) == 0
                and int(projection_second_drafts) == 0
                and int(projection_second_exceptions) == 0
                and int(posting_second_posted) == 0
                and int(posting_second_failed) == 0
            )

        blocked = run.status == CloseRun.Status.REOPENED_EXCEPTION

        if expect_blocked:
            scenario_ok = (
                blocked
                and int(first_counts.get("blocking_exceptions") or 0) > 0
                and str(second_projection_payload.get("close_run_status") or "") == CloseRun.Status.REOPENED_EXCEPTION
            )
        else:
            doc.refresh_from_db()
            operational_accounting_ok = (
                str(doc.accounting_status or "") in {"DRAFT_VALIDATED", "POSTED"}
                and (doc.accounting_journal_draft_id is not None or doc.accounting_journal_entry_id is not None)
            )
            scenario_ok = (
                not blocked
                and int(first_counts.get("blocking_exceptions") or 0) == 0
                and (
                    (
                        int(first_counts.get("journal_drafts_total") or 0) > 0
                        and int(first_counts.get("journal_entries_posted") or 0) > 0
                    )
                    or operational_accounting_ok
                )
            )
        passed = bool(deterministic and scenario_ok)
    finally:
        if expect_blocked:
            # Restablece reglas activas para no contaminar el entorno operativo.
            seed_posting_rules_v1_for_company(company=company)

    return Phase10CertificationResult(
        run_id=str(run.run_id),
        passed=bool(passed),
        blocked=bool(blocked),
        deterministic_replay=bool(deterministic),
        close_run_status=str(run.status),
        first_manifest_hash=first_manifest_hash,
        second_manifest_hash=second_manifest_hash,
        first_counts=first_counts,
        second_counts=second_counts,
        posting_first=first_posting_payload,
        posting_second=second_posting_payload,
        projection_first=first_projection_payload,
        projection_second=second_projection_payload,
        pilot_scope={"company_id": int(company.id), "branch_id": int(branch.id)},
        go_live_passed=bool(passed),
        doc_type=str(doc_type),
    )
