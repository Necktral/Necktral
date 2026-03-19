from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.certification import build_phase4_evidence, compare_phase4_env_manifests
from apps.modulos.accounting.models import PostingRuleSet
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import InboxEvent


class Command(BaseCommand):
    help = "Gate real de go-live Fase 4A (paridad + evidencia + salud operativa)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--staging-manifest", type=str, required=True)
        parser.add_argument("--prod-manifest", type=str, required=True)
        parser.add_argument("--happy-evidence", type=str, required=True)
        parser.add_argument("--blocked-evidence", type=str, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def _read_json(self, path: str) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            raise CommandError(f"archivo no encontrado: {p}")
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"JSON inválido en {p}: {exc}") from exc
        if not isinstance(payload, dict):
            raise CommandError(f"JSON inválido en {p}: se esperaba objeto")
        return payload

    def _validate_run_evidence(self, *, payload: dict[str, Any], expect_blocked: bool) -> list[str]:
        errors: list[str] = []
        expected_status = "REOPENED_EXCEPTION" if expect_blocked else "PACKAGED"

        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            errors.append("run_id vacío.")
        if bool(payload.get("passed")) is not True:
            errors.append("passed debe ser true.")
        if bool(payload.get("blocked")) != bool(expect_blocked):
            errors.append(f"blocked esperado={int(expect_blocked)}.")
        if str(payload.get("close_run_status") or "") != expected_status:
            errors.append(f"close_run_status esperado={expected_status}.")
        if not expect_blocked and bool(payload.get("replay_performed")) is not True:
            errors.append("replay_performed debe ser true en happy path.")
        if bool(payload.get("deterministic_replay")) is not True:
            errors.append("deterministic_replay debe ser true.")

        first_manifest_hash = str(payload.get("first_manifest_hash") or "").strip()
        second_manifest_hash = str(payload.get("second_manifest_hash") or "").strip()
        if not first_manifest_hash or not second_manifest_hash:
            errors.append("manifest hashes vacíos.")
        elif first_manifest_hash != second_manifest_hash:
            errors.append("first_manifest_hash y second_manifest_hash no coinciden.")

        first_counts = payload.get("first_counts")
        second_counts = payload.get("second_counts")
        if not isinstance(first_counts, dict) or not isinstance(second_counts, dict):
            errors.append("first_counts/second_counts inválidos.")
            return errors
        if first_counts != second_counts:
            errors.append("first_counts y second_counts no coinciden.")

        drafts_count = int(first_counts.get("journal_drafts") or 0)
        open_ex_count = int(first_counts.get("open_accounting_exceptions") or 0)
        if not expect_blocked and drafts_count <= 0:
            errors.append("journal_drafts debe ser > 0 en happy path.")
        if expect_blocked and open_ex_count <= 0:
            errors.append("open_accounting_exceptions debe ser > 0 en blocked path.")

        return errors

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        max_inbox_failed = int(options.get("max_inbox_failed") or 0)
        output = str(options.get("output") or "").strip()

        company = OrgUnit.objects.filter(
            id=company_id,
            unit_type=OrgUnit.UnitType.COMPANY,
            is_active=True,
        ).first()
        if company is None:
            raise CommandError(f"company inválida o inactiva: {company_id}")

        staging_manifest = self._read_json(options["staging_manifest"])
        prod_manifest = self._read_json(options["prod_manifest"])
        happy_evidence = self._read_json(options["happy_evidence"])
        blocked_evidence = self._read_json(options["blocked_evidence"])

        parity_mismatches = compare_phase4_env_manifests(left=staging_manifest, right=prod_manifest)
        happy_errors = self._validate_run_evidence(payload=happy_evidence, expect_blocked=False)
        blocked_errors = self._validate_run_evidence(payload=blocked_evidence, expect_blocked=True)

        active_ruleset_count = PostingRuleSet.objects.filter(
            code="shadow_ledger_v1",
            scope_company=company,
            status=PostingRuleSet.Status.ACTIVE,
        ).count()
        inbox_failed_count = InboxEvent.objects.filter(
            consumer=consumer,
            status=InboxEvent.Status.FAILED,
        ).count()

        checks = [
            {
                "name": "parity_no_drift",
                "passed": len(parity_mismatches) == 0,
                "detail": {"mismatches_count": len(parity_mismatches)},
            },
            {
                "name": "active_ruleset_present",
                "passed": int(active_ruleset_count) > 0,
                "detail": {"active_ruleset_count": int(active_ruleset_count)},
            },
            {
                "name": "happy_path_evidence_valid",
                "passed": len(happy_errors) == 0,
                "detail": {"errors": happy_errors},
            },
            {
                "name": "blocked_path_evidence_valid",
                "passed": len(blocked_errors) == 0,
                "detail": {"errors": blocked_errors},
            },
            {
                "name": "projector_inbox_failed_within_threshold",
                "passed": int(inbox_failed_count) <= int(max_inbox_failed),
                "detail": {
                    "consumer": consumer,
                    "failed_count": int(inbox_failed_count),
                    "max_allowed": int(max_inbox_failed),
                },
            },
        ]

        gate_passed = all(bool(row["passed"]) for row in checks)
        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "company_id": int(company.id),
            "company_name": company.name,
            "consumer": consumer,
            "max_inbox_failed": int(max_inbox_failed),
            "go_live_passed": bool(gate_passed),
            "checks": checks,
            "parity_mismatches": parity_mismatches,
            "evidence": {
                "happy_run_id": str(happy_evidence.get("run_id") or ""),
                "blocked_run_id": str(blocked_evidence.get("run_id") or ""),
            },
        }
        secret = str(os.getenv("PHASE4_EVIDENCE_SECRET", "")).strip()
        signed_report = build_phase4_evidence(payload=report, secret=secret)
        raw = json.dumps(signed_report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase4 go-live report exported: {path}"))
        else:
            self.stdout.write(raw)

        if not gate_passed and strict:
            raise CommandError("phase4 go-live gate failed.")

