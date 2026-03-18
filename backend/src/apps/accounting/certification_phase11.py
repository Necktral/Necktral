from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import Any

from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from apps.cec.models import CECException
from django.db.models import Q

from apps.iam.models import CompanyLink, LinkGrant, OrgUnit
from apps.iam.selectors import has_intercompany_grant
from apps.integration.models import InboxEvent, OutboxEvent
from apps.rbac.models import Permission

from .certification_phase7b import collect_phase7b_operational_health
from .models import IntercompanyDisputeCase, IntercompanyDisputeReason, IntercompanyTransaction
from .phase7b import (
    IntercompanyActionResult,
    create_intercompany_transaction,
    dispute_intercompany_transaction,
    enforce_intercompany_sla,
    run_intercompany_cycle,
    settle_intercompany_transaction,
)

OPEN_EXCEPTION_STATUSES = (CECException.Status.OPEN, CECException.Status.IN_PROGRESS)
F11_REQUIRED_PERMISSIONS = [
    "accounting.intercompany.read",
    "accounting.intercompany.write",
    "accounting.intercompany.reconcile",
    "accounting.intercompany.dispute",
    "accounting.intercompany.settle",
    "accounting.consolidation.read",
    "accounting.consolidation.run",
]
F11_REQUIRED_MATRIX_PERMISSIONS = [
    "accounting.intercompany.write",
    "accounting.intercompany.reconcile",
    "accounting.intercompany.dispute",
    "accounting.intercompany.settle",
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


def build_phase11_evidence(*, payload: dict[str, Any], secret: str = "") -> dict[str, Any]:
    digest, signature, signature_type = _signed_hash(payload, secret=secret)
    return {
        **payload,
        "evidence_hash": digest,
        "signature": signature,
        "signature_type": signature_type,
    }


def _resolve_company(*, company_id: int) -> OrgUnit:
    company = OrgUnit.objects.filter(id=int(company_id), unit_type=OrgUnit.UnitType.COMPANY, is_active=True).first()
    if company is None:
        raise ValueError(f"company inválida o inactiva: {company_id}")
    return company


def _resolve_branch(*, company: OrgUnit, branch_id: int) -> OrgUnit:
    branch = OrgUnit.objects.filter(
        id=int(branch_id),
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        is_active=True,
    ).first()
    if branch is None:
        raise ValueError(f"branch inválida o inactiva para company={company.id}: {branch_id}")
    return branch


def _resolve_target_company_from_matrix(*, source_company: OrgUnit, target_company_id: int | None = None) -> OrgUnit:
    if target_company_id is not None:
        target = _resolve_company(company_id=int(target_company_id))
        if int(target.id) == int(source_company.id):
            raise ValueError("target_company_id debe ser distinto de source_company.")
        candidate_companies = [target]
    else:
        candidate_companies = [
            row.from_company
            for row in CompanyLink.objects.select_related("from_company")
            .filter(to_company=source_company, is_active=True, status=CompanyLink.Status.ACTIVE)
            .order_by("from_company_id")
        ]

    for candidate in candidate_companies:
        if int(candidate.id) == int(source_company.id):
            continue
        if all(
            has_intercompany_grant(
                from_company=candidate,
                to_company=source_company,
                permission_code=perm,
                mode=LinkGrant.AccessMode.WRITE,
                scope_branch=None,
            )
            for perm in F11_REQUIRED_MATRIX_PERMISSIONS
        ):
            return candidate
    raise ValueError(
        "No existe contraparte intercompany autorizada por matriz explícita "
        f"para company={source_company.id} con permisos WRITE/RECONCILE/DISPUTE/SETTLE."
    )


def _resolve_default_dispute_reason(*, company: OrgUnit) -> IntercompanyDisputeReason:
    existing = (
        IntercompanyDisputeReason.objects.filter(company=company, is_active=True)
        .order_by("-version", "-id")
        .first()
    )
    if existing is None:
        raise ValueError(
            f"No existe catálogo activo de dispute reasons para company={company.id}. "
            "Registrar al menos un IntercompanyDisputeReason antes de certificar F11."
        )
    return existing


def collect_phase11_env_manifest(*, company_id: int, branch_id: int) -> dict[str, Any]:
    company = _resolve_company(company_id=company_id)
    branch = _resolve_branch(company=company, branch_id=branch_id)

    migrations = list(MigrationRecorder(connection).migration_qs.values_list("app", "name").order_by("app", "name"))
    migration_ids = [f"{app}.{name}" for app, name in migrations]
    migrations_hash = hashlib.sha256("\n".join(migration_ids).encode("utf-8")).hexdigest()

    permission_rows: list[dict[str, Any]] = []
    found_codes = set()
    for row in Permission.objects.filter(code__in=F11_REQUIRED_PERMISSIONS).order_by("code"):
        found_codes.add(row.code)
        permission_rows.append({"code": row.code, "is_active": bool(row.is_active)})
    for missing in sorted(set(F11_REQUIRED_PERMISSIONS) - found_codes):
        permission_rows.append({"code": missing, "is_active": False})
    permissions_hash = _json_hash({"rows": permission_rows})

    link_rows = list(
        CompanyLink.objects.filter(is_active=True, status=CompanyLink.Status.ACTIVE)
        .filter(Q(from_company=company) | Q(to_company=company))
        .values("from_company_id", "to_company_id", "status", "is_active")
        .order_by("from_company_id", "to_company_id")
    )
    links_hash = _json_hash({"rows": link_rows})

    write_grants_rows = list(
        LinkGrant.objects.filter(
            Q(link__from_company=company) | Q(link__to_company=company),
            is_active=True,
            access_mode=LinkGrant.AccessMode.WRITE,
        )
        .values("link__from_company_id", "link__to_company_id", "permission__code", "scope_org_unit_id")
        .order_by("link__from_company_id", "link__to_company_id", "permission__code")
    )
    write_grants_hash = _json_hash({"rows": write_grants_rows})

    reason_rows = list(
        IntercompanyDisputeReason.objects.filter(company=company, is_active=True)
        .values("code", "version", "severity", "requires_evidence", "is_active")
        .order_by("code", "-version")
    )
    reasons_hash = _json_hash({"rows": reason_rows})

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(dt_timezone.utc).isoformat(),
        "pilot_scope": {"company_id": int(company.id), "branch_id": int(branch.id)},
        "migrations": {"count": int(len(migration_ids)), "hash": migrations_hash},
        "required_permissions": {
            "count": int(len(permission_rows)),
            "hash": permissions_hash,
            "items": permission_rows,
        },
        "company_links": {"count": int(len(link_rows)), "hash": links_hash, "items": link_rows},
        "write_grants": {"count": int(len(write_grants_rows)), "hash": write_grants_hash, "items": write_grants_rows},
        "dispute_reasons": {"count": int(len(reason_rows)), "hash": reasons_hash, "items": reason_rows},
    }
    manifest["parity_fingerprint"] = _json_hash(
        {
            "migrations_hash": migrations_hash,
            "permissions_hash": permissions_hash,
            "links_hash": links_hash,
            "write_grants_hash": write_grants_hash,
            "reasons_hash": reasons_hash,
        }
    )
    return manifest


def compare_phase11_env_manifests(*, left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, str]]:
    checks = [
        ("migrations.hash", (left.get("migrations") or {}).get("hash"), (right.get("migrations") or {}).get("hash")),
        (
            "required_permissions.hash",
            (left.get("required_permissions") or {}).get("hash"),
            (right.get("required_permissions") or {}).get("hash"),
        ),
        ("company_links.hash", (left.get("company_links") or {}).get("hash"), (right.get("company_links") or {}).get("hash")),
        ("write_grants.hash", (left.get("write_grants") or {}).get("hash"), (right.get("write_grants") or {}).get("hash")),
        (
            "dispute_reasons.hash",
            (left.get("dispute_reasons") or {}).get("hash"),
            (right.get("dispute_reasons") or {}).get("hash"),
        ),
        ("parity_fingerprint", left.get("parity_fingerprint"), right.get("parity_fingerprint")),
    ]
    mismatches: list[dict[str, str]] = []
    for field, lval, rval in checks:
        if lval != rval:
            mismatches.append({"field": field, "left": str(lval), "right": str(rval)})
    return mismatches


def collect_phase11_operational_health(
    *,
    company_id: int,
    consumer: str = "accounting.projector",
    open_sla_hours: int = 24,
    dispute_sla_hours: int = 24,
) -> dict[str, int]:
    company = _resolve_company(company_id=company_id)
    base = collect_phase7b_operational_health(company_id=company_id, consumer=consumer)
    now = timezone.now()
    open_cutoff = now - timedelta(hours=max(1, int(open_sla_hours)))
    dispute_cutoff = now - timedelta(hours=max(1, int(dispute_sla_hours)))

    scope_qs = IntercompanyTransaction.objects.filter(source_company=company)
    open_outside_sla = scope_qs.filter(
        status__in=[IntercompanyTransaction.Status.PENDING, IntercompanyTransaction.Status.DIFFERENCE],
        created_at__lte=open_cutoff,
    ).count()
    disputed_outside_sla = scope_qs.filter(
        status=IntercompanyTransaction.Status.DISPUTED,
        updated_at__lte=dispute_cutoff,
    ).count()
    stale_confirmed_unclosed = scope_qs.filter(
        status=IntercompanyTransaction.Status.CONFIRMED,
        updated_at__lte=open_cutoff,
    ).count()
    blocking_exceptions = CECException.objects.filter(
        source_module="ACCOUNTING",
        company=company,
        related_object_type="INTERCOMPANY_TX",
        status__in=OPEN_EXCEPTION_STATUSES,
        is_blocking=True,
    ).count()
    open_dispute_cases = IntercompanyDisputeCase.objects.filter(
        transaction__source_company=company,
        status__in=["OPEN", "UNDER_REVIEW", "APPROVED"],
    ).count()
    inbox_failed_count = InboxEvent.objects.filter(consumer=consumer, status=InboxEvent.Status.FAILED).count()
    outbox_failed_count = OutboxEvent.objects.filter(company=company, status=OutboxEvent.Status.FAILED).count()

    return {
        **base,
        "open_outside_sla_count": int(open_outside_sla),
        "disputed_outside_sla_count": int(disputed_outside_sla),
        "stale_confirmed_unclosed_count": int(stale_confirmed_unclosed),
        "open_intercompany_blocking_exception_count": int(blocking_exceptions),
        "open_dispute_case_count": int(open_dispute_cases),
        "inbox_failed_count": int(inbox_failed_count),
        "outbox_failed_count": int(outbox_failed_count),
    }


@dataclass(frozen=True)
class Phase11CertificationResult:
    passed: bool
    blocked: bool
    deterministic_replay: bool
    tx_id: str
    create_status: str
    dispute_status: str
    settle_status: str
    first_cycle_hash: str
    second_cycle_hash: str
    third_cycle_hash: str
    first_cycle_open_items: int
    second_cycle_open_items: int
    third_cycle_open_items: int
    tx_open_blocking_exception_count: int
    health: dict[str, int]
    go_live_passed: bool
    pilot_scope: dict[str, int]


def _action_status(result: IntercompanyActionResult) -> str:
    return str(result.status or "")


def certify_phase11_intercompany_sla(
    *,
    company_id: int,
    target_company_id: int | None = None,
    consumer: str = "accounting.projector",
    open_sla_hours: int = 24,
    dispute_sla_hours: int = 24,
    expect_blocked: bool = False,
) -> Phase11CertificationResult:
    source_company = _resolve_company(company_id=company_id)
    target_company = _resolve_target_company_from_matrix(
        source_company=source_company,
        target_company_id=target_company_id,
    )
    reason = _resolve_default_dispute_reason(company=source_company)

    tx = create_intercompany_transaction(
        source_company_id=int(source_company.id),
        target_company_id=int(target_company.id),
        amount=Decimal("100.00"),
        currency="NIO",
        source_account_code="1101",
        target_account_code="2101",
        description=f"phase11-cert-{uuid.uuid4().hex[:8]}",
        reference_code=f"P11-{uuid.uuid4().hex[:8]}",
        actor_user=None,
        effective_company_id=int(source_company.id),
    )
    create_status = str(tx.status)

    dispute_result = dispute_intercompany_transaction(
        tx_id=str(tx.tx_id),
        source_amount=Decimal("100.00"),
        target_amount=Decimal("95.00"),
        reason_code=str(reason.code),
        evidence_refs=[f"phase11://evidence/{uuid.uuid4().hex}"],
        actor_user=None,
        note="phase11 dispute test",
        effective_company_id=int(source_company.id),
    )

    if expect_blocked:
        settle_result = settle_intercompany_transaction(
            tx_id=str(tx.tx_id),
            source_amount=Decimal("100.00"),
            target_amount=Decimal("95.00"),
            actor_user=None,
            note="phase11 blocked settlement mismatch",
            close_when_confirmed=True,
            allow_difference=False,
            effective_company_id=int(source_company.id),
        )
        stale_dt = timezone.now() - timedelta(hours=max(25, int(dispute_sla_hours) + 1))
        IntercompanyTransaction.objects.filter(tx_id=tx.tx_id).update(updated_at=stale_dt)
        IntercompanyDisputeCase.objects.filter(transaction__tx_id=tx.tx_id).update(
            opened_at=stale_dt,
            updated_at=stale_dt,
            sla_due_at=stale_dt,
        )
    else:
        settle_result = settle_intercompany_transaction(
            tx_id=str(tx.tx_id),
            source_amount=Decimal("100.00"),
            target_amount=Decimal("100.00"),
            actor_user=None,
            note="phase11 settle test",
            close_when_confirmed=True,
            allow_difference=False,
            effective_company_id=int(source_company.id),
        )

    first_cycle = run_intercompany_cycle(
        company_id=int(source_company.id),
        limit=200,
        strict=False,
        actor_user=None,
    )
    enforce_intercompany_sla(
        company_id=int(source_company.id),
        open_sla_hours=open_sla_hours,
        dispute_sla_hours=dispute_sla_hours,
        actor_user=None,
    )
    second_cycle = run_intercompany_cycle(
        company_id=int(source_company.id),
        limit=200,
        strict=False,
        actor_user=None,
    )
    enforce_intercompany_sla(
        company_id=int(source_company.id),
        open_sla_hours=open_sla_hours,
        dispute_sla_hours=dispute_sla_hours,
        actor_user=None,
    )
    third_cycle = run_intercompany_cycle(
        company_id=int(source_company.id),
        limit=200,
        strict=False,
        actor_user=None,
    )

    health = collect_phase11_operational_health(
        company_id=int(source_company.id),
        consumer=consumer,
        open_sla_hours=open_sla_hours,
        dispute_sla_hours=dispute_sla_hours,
    )
    tx_open_exceptions = CECException.objects.filter(
        source_module="ACCOUNTING",
        related_object_type="INTERCOMPANY_TX",
        related_object_id=str(tx.tx_id),
        status__in=OPEN_EXCEPTION_STATUSES,
        is_blocking=True,
    ).count()
    tx_row = IntercompanyTransaction.objects.filter(tx_id=tx.tx_id).first()

    first_sig = {
        "processed": int(first_cycle.processed),
        "confirmed": int(first_cycle.confirmed),
        "differences": int(first_cycle.differences),
        "disputed": int(first_cycle.disputed),
        "closed": int(first_cycle.closed),
        "open_items": int(first_cycle.open_items),
        "issues_count": int((first_cycle.report or {}).get("issues_count") or 0),
    }
    second_sig = {
        "processed": int(second_cycle.processed),
        "confirmed": int(second_cycle.confirmed),
        "differences": int(second_cycle.differences),
        "disputed": int(second_cycle.disputed),
        "closed": int(second_cycle.closed),
        "open_items": int(second_cycle.open_items),
        "issues_count": int((second_cycle.report or {}).get("issues_count") or 0),
    }
    third_sig = {
        "processed": int(third_cycle.processed),
        "confirmed": int(third_cycle.confirmed),
        "differences": int(third_cycle.differences),
        "disputed": int(third_cycle.disputed),
        "closed": int(third_cycle.closed),
        "open_items": int(third_cycle.open_items),
        "issues_count": int((third_cycle.report or {}).get("issues_count") or 0),
    }
    deterministic = bool(second_sig == third_sig)
    expected_settle_status = IntercompanyTransaction.Status.DISPUTED if expect_blocked else IntercompanyTransaction.Status.CLOSED
    scenario_ok = bool(
        _action_status(dispute_result) == IntercompanyTransaction.Status.DISPUTED
        and _action_status(settle_result) == expected_settle_status
    )
    blocked = bool(int(tx_open_exceptions) > 0 and tx_row is not None and str(tx_row.status) == IntercompanyTransaction.Status.DISPUTED)
    if expect_blocked:
        sla_ok = blocked
    else:
        sla_ok = bool(
            int(tx_open_exceptions) == 0
            and tx_row is not None
            and str(tx_row.status) == IntercompanyTransaction.Status.CLOSED
        )

    passed = bool(deterministic and scenario_ok and sla_ok and (blocked == bool(expect_blocked)))

    return Phase11CertificationResult(
        passed=bool(passed),
        blocked=bool(blocked),
        deterministic_replay=bool(deterministic),
        tx_id=str(tx.tx_id),
        create_status=create_status,
        dispute_status=_action_status(dispute_result),
        settle_status=_action_status(settle_result),
        # Hash determinista de firma canónica de ciclo (evita ruido temporal del report completo).
        first_cycle_hash=_json_hash(first_sig),
        second_cycle_hash=_json_hash(second_sig),
        third_cycle_hash=_json_hash(third_sig),
        first_cycle_open_items=int(first_cycle.open_items),
        second_cycle_open_items=int(second_cycle.open_items),
        third_cycle_open_items=int(third_cycle.open_items),
        tx_open_blocking_exception_count=int(tx_open_exceptions),
        health=health,
        go_live_passed=bool(passed),
        pilot_scope={
            "company_id": int(source_company.id),
            "target_company_id": int(target_company.id),
        },
    )
