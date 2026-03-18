from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from apps.cec.models import CECException
from apps.iam.models import OrgUnit
from apps.integration.models import InboxEvent, OutboxEvent

from .models import ConsolidationRun, IntercompanyTransaction
from .phase7b import run_consolidation

OPEN_EXCEPTION_STATUSES = (CECException.Status.OPEN, CECException.Status.IN_PROGRESS)


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


def build_phase7b_evidence(*, payload: dict[str, Any], secret: str = "") -> dict[str, Any]:
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


def collect_phase7b_operational_health(*, company_id: int, consumer: str = "accounting.projector") -> dict[str, int]:
    company = _resolve_company(company_id=company_id)
    open_intercompany_count = IntercompanyTransaction.objects.filter(
        source_company=company,
        status__in=[
            IntercompanyTransaction.Status.PENDING,
            IntercompanyTransaction.Status.DIFFERENCE,
            IntercompanyTransaction.Status.DISPUTED,
        ],
    ).count()
    disputed_count = IntercompanyTransaction.objects.filter(
        source_company=company,
        status=IntercompanyTransaction.Status.DISPUTED,
    ).count()
    blocked_consolidation_count = ConsolidationRun.objects.filter(
        parent_company=company,
        status=ConsolidationRun.Status.BLOCKED,
    ).count()
    open_consolidation_exception_count = CECException.objects.filter(
        source_module="ACCOUNTING",
        company=company,
        related_object_type="CONSOLIDATION_RUN",
        status__in=OPEN_EXCEPTION_STATUSES,
    ).count()
    inbox_failed_count = InboxEvent.objects.filter(consumer=consumer, status=InboxEvent.Status.FAILED).count()
    outbox_failed_count = OutboxEvent.objects.filter(company=company, status=OutboxEvent.Status.FAILED).count()
    return {
        "open_intercompany_count": int(open_intercompany_count),
        "disputed_intercompany_count": int(disputed_count),
        "blocked_consolidation_count": int(blocked_consolidation_count),
        "open_consolidation_exception_count": int(open_consolidation_exception_count),
        "inbox_failed_count": int(inbox_failed_count),
        "outbox_failed_count": int(outbox_failed_count),
    }


@dataclass(frozen=True)
class Phase7BConsolidationCertification:
    run_id: str
    passed: bool
    blocked: bool
    deterministic_replay: bool
    first_manifest_hash: str
    second_manifest_hash: str
    first_status: str
    second_status: str
    first_metrics: dict[str, Any]
    second_metrics: dict[str, Any]


def certify_phase7b_consolidation(
    *,
    parent_company_id: int,
    year: int,
    month: int,
    company_ids: list[int],
    expect_blocked: bool = False,
) -> Phase7BConsolidationCertification:
    first = run_consolidation(
        parent_company_id=parent_company_id,
        year=year,
        month=month,
        company_ids=company_ids,
        strict=True,
        actor_user=None,
    )
    second = run_consolidation(
        parent_company_id=parent_company_id,
        year=year,
        month=month,
        company_ids=company_ids,
        strict=True,
        actor_user=None,
    )
    first_metrics = dict((first.summary_json or {}).get("metrics") or {})
    second_metrics = dict((second.summary_json or {}).get("metrics") or {})
    deterministic = (
        str(first.manifest_hash) == str(second.manifest_hash)
        and str(first.status) == str(second.status)
        and first_metrics == second_metrics
    )
    blocked = str(first.status) == ConsolidationRun.Status.BLOCKED
    passed = bool(deterministic and (blocked == bool(expect_blocked)))
    return Phase7BConsolidationCertification(
        run_id=str(first.run_id),
        passed=bool(passed),
        blocked=bool(blocked),
        deterministic_replay=bool(deterministic),
        first_manifest_hash=str(first.manifest_hash),
        second_manifest_hash=str(second.manifest_hash),
        first_status=str(first.status),
        second_status=str(second.status),
        first_metrics=first_metrics,
        second_metrics=second_metrics,
    )


def build_phase7b_cycle_report(
    *,
    company_id: int,
    cycle_payload: dict[str, Any],
    consolidation_payload: dict[str, Any],
    health: dict[str, int],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": timezone.now().isoformat(),
        "pilot_scope": {"company_id": int(company_id)},
        "cycle": cycle_payload,
        "consolidation": consolidation_payload,
        "health": health,
        "manifest_hash": _json_hash(
            {
                "company_id": int(company_id),
                "cycle": cycle_payload,
                "consolidation": consolidation_payload,
                "health": health,
            }
        ),
    }
