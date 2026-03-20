from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from kernels.compras.certification_phase10 import (
    build_phase10_evidence,
    collect_phase10_operational_health,
    compare_phase10_env_manifests,
)


class Command(BaseCommand):
    help = "Gate final de go-live Fase 10 (procurement 4B)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--staging-manifest", type=str, required=True)
        parser.add_argument("--prod-manifest", type=str, required=True)
        parser.add_argument("--certification", type=str, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-open-procurement-drafts", type=int, default=0)
        parser.add_argument("--max-open-procurement-blocking-exceptions", type=int, default=0)
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
    def _validate_certification(payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if bool(payload.get("passed")) is not True:
            errors.append("passed debe ser true.")
        if bool(payload.get("go_live_passed")) is not True:
            errors.append("go_live_passed debe ser true.")
        if bool(payload.get("deterministic_replay")) is not True:
            errors.append("deterministic_replay debe ser true.")
        first_hash = str(payload.get("first_manifest_hash") or "")
        second_hash = str(payload.get("second_manifest_hash") or "")
        if not first_hash or not second_hash or first_hash != second_hash:
            errors.append("first_manifest_hash y second_manifest_hash deben coincidir.")
        if str(payload.get("close_run_status") or "") != "PACKAGED":
            errors.append("close_run_status esperado=PACKAGED.")
        counts = payload.get("first_counts") or {}
        if int(counts.get("journal_entries_posted") or 0) <= 0:
            errors.append("journal_entries_posted debe ser > 0.")
        return errors

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        output = str(options.get("output") or "").strip()

        staging_manifest = self._read_json(options["staging_manifest"])
        prod_manifest = self._read_json(options["prod_manifest"])
        certification = self._read_json(options["certification"])

        parity_mismatches = compare_phase10_env_manifests(left=staging_manifest, right=prod_manifest)
        cert_errors = self._validate_certification(certification)
        health = collect_phase10_operational_health(company_id=company_id, branch_id=branch_id, consumer=consumer)

        checks = [
            {
                "name": "parity_no_drift",
                "passed": len(parity_mismatches) == 0,
                "detail": {"mismatches_count": len(parity_mismatches)},
            },
            {
                "name": "certification_valid",
                "passed": len(cert_errors) == 0,
                "detail": {"errors": cert_errors},
            },
            {
                "name": "inbox_failed_within_threshold",
                "passed": int(health.get("inbox_failed_count") or 0) <= int(options.get("max_inbox_failed") or 0),
                "detail": {
                    "count": int(health.get("inbox_failed_count") or 0),
                    "max_allowed": int(options.get("max_inbox_failed") or 0),
                },
            },
            {
                "name": "outbox_failed_within_threshold",
                "passed": int(health.get("outbox_failed_count") or 0) <= int(options.get("max_outbox_failed") or 0),
                "detail": {
                    "count": int(health.get("outbox_failed_count") or 0),
                    "max_allowed": int(options.get("max_outbox_failed") or 0),
                },
            },
            {
                "name": "open_procurement_drafts_within_threshold",
                "passed": int(health.get("open_procurement_drafts_count") or 0)
                <= int(options.get("max_open_procurement_drafts") or 0),
                "detail": {
                    "count": int(health.get("open_procurement_drafts_count") or 0),
                    "max_allowed": int(options.get("max_open_procurement_drafts") or 0),
                },
            },
            {
                "name": "open_procurement_blocking_exceptions_within_threshold",
                "passed": int(health.get("open_procurement_blocking_exceptions_count") or 0)
                <= int(options.get("max_open_procurement_blocking_exceptions") or 0),
                "detail": {
                    "count": int(health.get("open_procurement_blocking_exceptions_count") or 0),
                    "max_allowed": int(options.get("max_open_procurement_blocking_exceptions") or 0),
                },
            },
        ]
        go_live_passed = all(bool(item["passed"]) for item in checks)

        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"company_id": company_id, "branch_id": branch_id},
            "consumer": consumer,
            "go_live_passed": bool(go_live_passed),
            "checks": checks,
            "parity_mismatches": parity_mismatches,
            "health": health,
            "certification_ref": {
                "run_id": str(certification.get("run_id") or ""),
                "manifest_hash": str(certification.get("second_manifest_hash") or ""),
            },
        }

        secret = str(os.getenv("PHASE10_EVIDENCE_SECRET", "")).strip()
        signed_report = build_phase10_evidence(payload=report, secret=secret)
        raw = json.dumps(signed_report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase10 go-live report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not go_live_passed:
            raise CommandError("phase10 go-live gate failed.")

