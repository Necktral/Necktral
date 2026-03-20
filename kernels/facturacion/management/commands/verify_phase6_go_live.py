from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from kernels.facturacion.certification import (
    build_phase6_evidence,
    collect_phase6_operational_health,
    compare_phase6_env_manifests,
)


class Command(BaseCommand):
    help = "Gate real de go-live Fase 6 (paridad + evidencia + salud operativa)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--staging-manifest", type=str, required=True)
        parser.add_argument("--prod-manifest", type=str, required=True)
        parser.add_argument("--happy-evidence", type=str, required=True)
        parser.add_argument("--blocked-evidence", type=str, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--stale-minutes", type=int, default=30)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-failed-jobs", type=int, default=0)
        parser.add_argument("--max-retry-overdue", type=int, default=0)
        parser.add_argument("--max-contingency-open", type=int, default=0)
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
        if bool(payload.get("go_live_passed")) is not True:
            errors.append("go_live_passed debe ser true.")
        if bool(payload.get("blocked")) != bool(expect_blocked):
            errors.append(f"blocked esperado={int(expect_blocked)}.")
        if str(payload.get("close_run_status") or "") != expected_status:
            errors.append(f"close_run_status esperado={expected_status}.")
        if bool(payload.get("deterministic_replay")) is not True:
            errors.append("deterministic_replay debe ser true.")

        first_manifest_hash = str(payload.get("first_manifest_hash") or "").strip()
        second_manifest_hash = str(payload.get("second_manifest_hash") or "").strip()
        manifest_hash = str(payload.get("manifest_hash") or "").strip()
        if not first_manifest_hash or not second_manifest_hash or not manifest_hash:
            errors.append("manifest hashes vacíos.")
        elif first_manifest_hash != second_manifest_hash or first_manifest_hash != manifest_hash:
            errors.append("manifest hashes no coinciden.")

        first_counts = payload.get("first_counts")
        second_counts = payload.get("second_counts")
        if not isinstance(first_counts, dict) or not isinstance(second_counts, dict):
            errors.append("first_counts/second_counts inválidos.")
            return errors
        if first_counts != second_counts:
            errors.append("first_counts y second_counts no coinciden.")

        job_counts = payload.get("job_counts")
        if not isinstance(job_counts, dict):
            errors.append("job_counts inválido.")
        elif int(job_counts.get("total") or 0) <= 0:
            errors.append("job_counts.total debe ser > 0.")

        if not expect_blocked and int(first_counts.get("print_jobs_printed") or 0) <= 0:
            errors.append("print_jobs_printed debe ser > 0 en happy path.")
        if expect_blocked and int(first_counts.get("contingency_docs_open") or 0) <= 0:
            errors.append("contingency_docs_open debe ser > 0 en blocked path.")
        if expect_blocked and int(payload.get("cec_blocking_exceptions") or 0) <= 0:
            errors.append("cec_blocking_exceptions debe ser > 0 en blocked path.")

        return errors

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        stale_minutes = int(options.get("stale_minutes") or 30)
        max_inbox_failed = int(options.get("max_inbox_failed") or 0)
        max_outbox_failed = int(options.get("max_outbox_failed") or 0)
        max_failed_jobs = int(options.get("max_failed_jobs") or 0)
        max_retry_overdue = int(options.get("max_retry_overdue") or 0)
        max_contingency_open = int(options.get("max_contingency_open") or 0)
        output = str(options.get("output") or "").strip()

        staging_manifest = self._read_json(options["staging_manifest"])
        prod_manifest = self._read_json(options["prod_manifest"])
        happy_evidence = self._read_json(options["happy_evidence"])
        blocked_evidence = self._read_json(options["blocked_evidence"])

        parity_mismatches = compare_phase6_env_manifests(left=staging_manifest, right=prod_manifest)
        happy_errors = self._validate_run_evidence(payload=happy_evidence, expect_blocked=False)
        blocked_errors = self._validate_run_evidence(payload=blocked_evidence, expect_blocked=True)

        health = collect_phase6_operational_health(
            company_id=company_id,
            branch_id=branch_id,
            consumer=consumer,
            stale_minutes=stale_minutes,
        )
        checks = [
            {
                "name": "parity_no_drift",
                "passed": len(parity_mismatches) == 0,
                "detail": {"mismatches_count": len(parity_mismatches)},
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
                "name": "inbox_failed_within_threshold",
                "passed": health["inbox_failed_count"] <= max_inbox_failed,
                "detail": {
                    "consumer": consumer,
                    "failed_count": int(health["inbox_failed_count"]),
                    "max_allowed": int(max_inbox_failed),
                },
            },
            {
                "name": "outbox_failed_within_threshold",
                "passed": health["outbox_failed_count"] <= max_outbox_failed,
                "detail": {
                    "failed_count": int(health["outbox_failed_count"]),
                    "max_allowed": int(max_outbox_failed),
                },
            },
            {
                "name": "failed_jobs_within_threshold",
                "passed": health["failed_jobs_count"] <= max_failed_jobs,
                "detail": {
                    "failed_jobs_count": int(health["failed_jobs_count"]),
                    "max_allowed": int(max_failed_jobs),
                },
            },
            {
                "name": "retry_overdue_within_threshold",
                "passed": health["retry_overdue_count"] <= max_retry_overdue,
                "detail": {
                    "retry_overdue_count": int(health["retry_overdue_count"]),
                    "max_allowed": int(max_retry_overdue),
                },
            },
            {
                "name": "open_contingency_within_threshold",
                "passed": health["contingency_open_count"] <= max_contingency_open,
                "detail": {
                    "contingency_open_count": int(health["contingency_open_count"]),
                    "max_allowed": int(max_contingency_open),
                },
            },
        ]
        gate_passed = all(bool(row["passed"]) for row in checks)

        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"company_id": company_id, "branch_id": branch_id},
            "consumer": consumer,
            "go_live_passed": bool(gate_passed),
            "checks": checks,
            "parity_mismatches": parity_mismatches,
            "health": health,
            "evidence": {
                "happy_run_id": str(happy_evidence.get("run_id") or ""),
                "blocked_run_id": str(blocked_evidence.get("run_id") or ""),
            },
        }
        secret = str(os.getenv("PHASE6_EVIDENCE_SECRET", "")).strip()
        signed_report = build_phase6_evidence(payload=report, secret=secret)
        raw = json.dumps(signed_report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase6 go-live report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not gate_passed:
            raise CommandError("phase6 go-live gate failed.")
