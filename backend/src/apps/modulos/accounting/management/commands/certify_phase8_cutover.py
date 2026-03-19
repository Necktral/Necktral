from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.phase8 import (
    build_phase8_evidence,
    collect_phase8_operational_health,
    compare_phase8_env_manifests,
)


class Command(BaseCommand):
    help = "Certifica cutover F8 (paridad + gates F6/F7A/F7B + salud operativa)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--parent-company-id", type=int, required=True)
        parser.add_argument("--company-ids", type=int, nargs="+", required=True)
        parser.add_argument("--staging-manifest", type=str, required=True)
        parser.add_argument("--prod-manifest", type=str, required=True)
        parser.add_argument("--phase6-gate", type=str, required=True)
        parser.add_argument("--phase7-gate", type=str, required=True)
        parser.add_argument("--phase7b-gate", type=str, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--stale-minutes", type=int, default=30)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-missing-lines", type=int, default=0)
        parser.add_argument("--max-stale-revaluation", type=int, default=0)
        parser.add_argument("--max-open-intercompany", type=int, default=0)
        parser.add_argument("--max-disputed-intercompany", type=int, default=0)
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
    def _validate_gate(payload: dict[str, Any], label: str) -> list[str]:
        errors: list[str] = []
        if bool(payload.get("go_live_passed")) is not True:
            errors.append(f"{label}.go_live_passed debe ser true")
        checks = payload.get("checks")
        if not isinstance(checks, list) or not checks:
            errors.append(f"{label}.checks inválido")
        return errors

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        parent_company_id = int(options["parent_company_id"])
        company_ids = [int(x) for x in (options.get("company_ids") or [])]
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        stale_minutes = int(options.get("stale_minutes") or 30)
        output = str(options.get("output") or "").strip()

        staging_manifest = self._read_json(options["staging_manifest"])
        prod_manifest = self._read_json(options["prod_manifest"])
        phase6_gate = self._read_json(options["phase6_gate"])
        phase7_gate = self._read_json(options["phase7_gate"])
        phase7b_gate = self._read_json(options["phase7b_gate"])

        parity_mismatches = compare_phase8_env_manifests(left=staging_manifest, right=prod_manifest)
        phase6_errors = self._validate_gate(phase6_gate, "phase6")
        phase7_errors = self._validate_gate(phase7_gate, "phase7")
        phase7b_errors = self._validate_gate(phase7b_gate, "phase7b")

        health = collect_phase8_operational_health(
            company_id=company_id,
            branch_id=branch_id,
            parent_company_id=parent_company_id,
            consumer=consumer,
            stale_minutes=stale_minutes,
        )
        phase6 = dict(health.get("phase6") or {})
        phase7a = dict(health.get("phase7a") or {})
        phase7b = dict(health.get("phase7b") or {})

        checks = [
            {"name": "parity_no_drift", "passed": len(parity_mismatches) == 0, "detail": {"count": len(parity_mismatches)}},
            {"name": "phase6_gate_valid", "passed": len(phase6_errors) == 0, "detail": {"errors": phase6_errors}},
            {"name": "phase7_gate_valid", "passed": len(phase7_errors) == 0, "detail": {"errors": phase7_errors}},
            {"name": "phase7b_gate_valid", "passed": len(phase7b_errors) == 0, "detail": {"errors": phase7b_errors}},
            {
                "name": "inbox_failed_within_threshold",
                "passed": max(
                    int(phase6.get("inbox_failed_count") or 0),
                    int(phase7a.get("inbox_failed_count") or 0),
                    int(phase7b.get("inbox_failed_count") or 0),
                ) <= int(options.get("max_inbox_failed") or 0),
                "detail": {
                    "phase6": int(phase6.get("inbox_failed_count") or 0),
                    "phase7a": int(phase7a.get("inbox_failed_count") or 0),
                    "phase7b": int(phase7b.get("inbox_failed_count") or 0),
                    "max_allowed": int(options.get("max_inbox_failed") or 0),
                },
            },
            {
                "name": "outbox_failed_within_threshold",
                "passed": max(
                    int(phase6.get("outbox_failed_count") or 0),
                    int(phase7a.get("outbox_failed_count") or 0),
                    int(phase7b.get("outbox_failed_count") or 0),
                ) <= int(options.get("max_outbox_failed") or 0),
                "detail": {
                    "phase6": int(phase6.get("outbox_failed_count") or 0),
                    "phase7a": int(phase7a.get("outbox_failed_count") or 0),
                    "phase7b": int(phase7b.get("outbox_failed_count") or 0),
                    "max_allowed": int(options.get("max_outbox_failed") or 0),
                },
            },
            {
                "name": "missing_lines_within_threshold",
                "passed": int(phase7a.get("missing_lines_count") or 0) <= int(options.get("max_missing_lines") or 0),
                "detail": {
                    "count": int(phase7a.get("missing_lines_count") or 0),
                    "max_allowed": int(options.get("max_missing_lines") or 0),
                },
            },
            {
                "name": "stale_revaluation_within_threshold",
                "passed": int(phase7a.get("stale_revaluation_count") or 0)
                <= int(options.get("max_stale_revaluation") or 0),
                "detail": {
                    "count": int(phase7a.get("stale_revaluation_count") or 0),
                    "max_allowed": int(options.get("max_stale_revaluation") or 0),
                },
            },
            {
                "name": "open_intercompany_within_threshold",
                "passed": int(phase7b.get("open_intercompany_count") or 0)
                <= int(options.get("max_open_intercompany") or 0),
                "detail": {
                    "count": int(phase7b.get("open_intercompany_count") or 0),
                    "max_allowed": int(options.get("max_open_intercompany") or 0),
                },
            },
            {
                "name": "disputed_intercompany_within_threshold",
                "passed": int(phase7b.get("disputed_intercompany_count") or 0)
                <= int(options.get("max_disputed_intercompany") or 0),
                "detail": {
                    "count": int(phase7b.get("disputed_intercompany_count") or 0),
                    "max_allowed": int(options.get("max_disputed_intercompany") or 0),
                },
            },
        ]

        cutover_passed = all(bool(row["passed"]) for row in checks)
        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {
                "company_id": company_id,
                "branch_id": branch_id,
                "parent_company_id": parent_company_id,
                "company_ids": sorted({int(x) for x in company_ids}),
            },
            "consumer": consumer,
            "cutover_passed": bool(cutover_passed),
            "checks": checks,
            "parity_mismatches": parity_mismatches,
            "health": health,
            "evidence": {
                "phase6_gate_hash": str(phase6_gate.get("evidence_hash") or ""),
                "phase7_gate_hash": str(phase7_gate.get("evidence_hash") or ""),
                "phase7b_gate_hash": str(phase7b_gate.get("evidence_hash") or ""),
            },
            "cutover_window": {
                "executed_at": timezone.now().isoformat(),
            },
        }

        secret = str(os.getenv("PHASE8_EVIDENCE_SECRET", "")).strip()
        signed = build_phase8_evidence(payload=report, secret=secret)
        raw = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase8 cutover certification exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not cutover_passed:
            raise CommandError("phase8 cutover gate failed")
