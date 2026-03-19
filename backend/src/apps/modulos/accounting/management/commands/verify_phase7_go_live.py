from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.certification_phase7 import (
    build_phase7_evidence,
    collect_phase7_operational_health,
    compare_phase7_env_manifests,
)


class Command(BaseCommand):
    help = "Gate real de go-live Fase 7A."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--staging-manifest", type=str, required=True)
        parser.add_argument("--prod-manifest", type=str, required=True)
        parser.add_argument("--happy-evidence", type=str, required=True)
        parser.add_argument("--blocked-evidence", type=str, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-unbalanced-entries", type=int, default=0)
        parser.add_argument("--max-missing-lines", type=int, default=0)
        parser.add_argument("--max-stale-revaluation", type=int, default=0)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    @staticmethod
    def _read_json(path: str) -> dict[str, Any]:
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

    @staticmethod
    def _validate_run_evidence(payload: dict[str, Any], expect_blocked: bool) -> list[str]:
        errors: list[str] = []
        if bool(payload.get("passed")) is not True:
            errors.append("passed debe ser true.")
        if bool(payload.get("go_live_passed")) is not True:
            errors.append("go_live_passed debe ser true.")
        if bool(payload.get("deterministic_replay")) is not True:
            errors.append("deterministic_replay debe ser true.")
        if bool(payload.get("blocked")) != bool(expect_blocked):
            errors.append("blocked no coincide con expectativa.")
        first_hash = str(payload.get("first_manifest_hash") or "")
        second_hash = str(payload.get("second_manifest_hash") or "")
        if not first_hash or not second_hash or first_hash != second_hash:
            errors.append("manifest hashes inválidos o no coinciden.")
        first_counts = payload.get("first_counts")
        second_counts = payload.get("second_counts")
        if not isinstance(first_counts, dict) or not isinstance(second_counts, dict) or first_counts != second_counts:
            errors.append("first_counts/second_counts inválidos o no coinciden.")
        safe_first_counts = first_counts if isinstance(first_counts, dict) else {}
        if expect_blocked:
            if str(payload.get("close_run_status") or "") != "REOPENED_EXCEPTION":
                errors.append("close_run_status esperado=REOPENED_EXCEPTION.")
        else:
            if str(payload.get("close_run_status") or "") != "PACKAGED":
                errors.append("close_run_status esperado=PACKAGED.")
            if int(safe_first_counts.get("journal_entry_lines") or 0) <= 0:
                errors.append("journal_entry_lines debe ser > 0 en happy path.")
        return errors

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        output = str(options.get("output") or "").strip()

        staging_manifest = self._read_json(options["staging_manifest"])
        prod_manifest = self._read_json(options["prod_manifest"])
        happy_evidence = self._read_json(options["happy_evidence"])
        blocked_evidence = self._read_json(options["blocked_evidence"])

        parity_mismatches = compare_phase7_env_manifests(left=staging_manifest, right=prod_manifest)
        happy_errors = self._validate_run_evidence(happy_evidence, expect_blocked=False)
        blocked_errors = self._validate_run_evidence(blocked_evidence, expect_blocked=True)
        health = collect_phase7_operational_health(company_id=company_id, consumer=consumer)

        checks = [
            {"name": "parity_no_drift", "passed": len(parity_mismatches) == 0, "detail": {"mismatches": len(parity_mismatches)}},
            {"name": "happy_evidence_valid", "passed": len(happy_errors) == 0, "detail": {"errors": happy_errors}},
            {"name": "blocked_evidence_valid", "passed": len(blocked_errors) == 0, "detail": {"errors": blocked_errors}},
            {
                "name": "inbox_failed_within_threshold",
                "passed": int(health["inbox_failed_count"]) <= int(options.get("max_inbox_failed") or 0),
                "detail": {"count": int(health["inbox_failed_count"]), "max_allowed": int(options.get("max_inbox_failed") or 0)},
            },
            {
                "name": "outbox_failed_within_threshold",
                "passed": int(health["outbox_failed_count"]) <= int(options.get("max_outbox_failed") or 0),
                "detail": {"count": int(health["outbox_failed_count"]), "max_allowed": int(options.get("max_outbox_failed") or 0)},
            },
            {
                "name": "unbalanced_entries_within_threshold",
                "passed": int(health["unbalanced_entries_count"]) <= int(options.get("max_unbalanced_entries") or 0),
                "detail": {
                    "count": int(health["unbalanced_entries_count"]),
                    "max_allowed": int(options.get("max_unbalanced_entries") or 0),
                },
            },
            {
                "name": "missing_lines_within_threshold",
                "passed": int(health["missing_lines_count"]) <= int(options.get("max_missing_lines") or 0),
                "detail": {"count": int(health["missing_lines_count"]), "max_allowed": int(options.get("max_missing_lines") or 0)},
            },
            {
                "name": "stale_revaluation_within_threshold",
                "passed": int(health["stale_revaluation_count"]) <= int(options.get("max_stale_revaluation") or 0),
                "detail": {
                    "count": int(health["stale_revaluation_count"]),
                    "max_allowed": int(options.get("max_stale_revaluation") or 0),
                },
            },
        ]
        go_live_passed = all(bool(x["passed"]) for x in checks)
        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"company_id": company_id},
            "consumer": consumer,
            "go_live_passed": bool(go_live_passed),
            "checks": checks,
            "parity_mismatches": parity_mismatches,
            "health": health,
            "evidence": {
                "happy_run_id": str(happy_evidence.get("run_id") or ""),
                "blocked_run_id": str(blocked_evidence.get("run_id") or ""),
            },
        }
        secret = str(os.getenv("PHASE7_EVIDENCE_SECRET", "")).strip()
        signed_report = build_phase7_evidence(payload=report, secret=secret)
        raw = json.dumps(signed_report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase7 go-live report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not go_live_passed:
            raise CommandError("phase7 go-live gate failed.")
