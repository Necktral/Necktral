from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.certification_phase11 import (
    build_phase11_evidence,
    collect_phase11_operational_health,
    compare_phase11_env_manifests,
)


class Command(BaseCommand):
    help = "Gate final Fase 11 (intercompany avanzado + SLA)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--open-sla-hours", type=int, default=24)
        parser.add_argument("--dispute-sla-hours", type=int, default=24)
        parser.add_argument("--staging-manifest", type=str, default="")
        parser.add_argument("--prod-manifest", type=str, default="")
        parser.add_argument("--happy-evidence", type=str, default="")
        parser.add_argument("--blocked-evidence", type=str, default="")
        parser.add_argument("--certification", type=str, default="")
        parser.add_argument("--max-open-intercompany", type=int, default=0)
        parser.add_argument("--max-disputed-intercompany", type=int, default=0)
        parser.add_argument("--max-open-outside-sla", type=int, default=0)
        parser.add_argument("--max-disputed-outside-sla", type=int, default=0)
        parser.add_argument("--max-stale-confirmed-unclosed", type=int, default=0)
        parser.add_argument("--max-open-blocking-exceptions", type=int, default=0)
        parser.add_argument("--max-blocked-consolidation", type=int, default=0)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
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
    def _validate_run_evidence(payload: dict[str, Any], *, expect_blocked: bool) -> list[str]:
        errors: list[str] = []
        expected_settle_status = "DISPUTED" if expect_blocked else "CLOSED"
        if bool(payload.get("passed")) is not True:
            errors.append("passed debe ser true.")
        if bool(payload.get("go_live_passed")) is not True:
            errors.append("go_live_passed debe ser true.")
        if bool(payload.get("blocked")) != bool(expect_blocked):
            errors.append(f"blocked esperado={int(expect_blocked)}.")
        if bool(payload.get("deterministic_replay")) is not True:
            errors.append("deterministic_replay debe ser true.")
        if str(payload.get("dispute_status") or "") != "DISPUTED":
            errors.append("dispute_status esperado=DISPUTED.")
        if str(payload.get("settle_status") or "") != expected_settle_status:
            errors.append(f"settle_status esperado={expected_settle_status}.")
        second_hash = str(payload.get("second_cycle_hash") or "")
        third_hash = str(payload.get("third_cycle_hash") or "")
        if not second_hash or not third_hash or second_hash != third_hash:
            errors.append("second_cycle_hash y third_cycle_hash deben coincidir.")
        tx_open_blocking_count_raw = payload.get("tx_open_blocking_exception_count")
        if tx_open_blocking_count_raw is None:
            tx_open_blocking_count = int((payload.get("health") or {}).get("open_intercompany_blocking_exception_count") or 0)
        else:
            tx_open_blocking_count = int(tx_open_blocking_count_raw or 0)
        if expect_blocked and tx_open_blocking_count <= 0:
            errors.append("tx_open_blocking_exception_count debe ser > 0 para blocked.")
        if not expect_blocked and tx_open_blocking_count != 0:
            errors.append("tx_open_blocking_exception_count debe ser 0 para happy.")
        return errors

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        output = str(options.get("output") or "").strip()

        staging_manifest_path = str(options.get("staging_manifest") or "").strip()
        prod_manifest_path = str(options.get("prod_manifest") or "").strip()
        happy_path = str(options.get("happy_evidence") or "").strip()
        blocked_path = str(options.get("blocked_evidence") or "").strip()
        cert_path = str(options.get("certification") or "").strip()

        parity_mismatches: list[dict[str, str]] = []
        if staging_manifest_path and prod_manifest_path:
            staging_manifest = self._read_json(staging_manifest_path)
            prod_manifest = self._read_json(prod_manifest_path)
            parity_mismatches = compare_phase11_env_manifests(left=staging_manifest, right=prod_manifest)

        happy_errors: list[str] = []
        blocked_errors: list[str] = []
        evidence_refs: dict[str, str] = {"happy_tx_id": "", "blocked_tx_id": ""}
        if happy_path and blocked_path:
            happy_payload = self._read_json(happy_path)
            blocked_payload = self._read_json(blocked_path)
            happy_errors = self._validate_run_evidence(happy_payload, expect_blocked=False)
            blocked_errors = self._validate_run_evidence(blocked_payload, expect_blocked=True)
            evidence_refs = {
                "happy_tx_id": str(happy_payload.get("tx_id") or ""),
                "blocked_tx_id": str(blocked_payload.get("tx_id") or ""),
            }
        elif cert_path:
            cert_payload = self._read_json(cert_path)
            happy_errors = self._validate_run_evidence(cert_payload, expect_blocked=bool(cert_payload.get("blocked")))
            evidence_refs = {
                "happy_tx_id": str(cert_payload.get("tx_id") or ""),
                "blocked_tx_id": "",
            }
        else:
            raise CommandError("Debe proporcionar --certification o ambos --happy-evidence y --blocked-evidence.")

        health = collect_phase11_operational_health(
            company_id=company_id,
            consumer=consumer,
            open_sla_hours=int(options.get("open_sla_hours") or 24),
            dispute_sla_hours=int(options.get("dispute_sla_hours") or 24),
        )

        checks = [
            {
                "name": "parity_no_drift",
                "passed": len(parity_mismatches) == 0,
                "detail": {"mismatches_count": len(parity_mismatches)},
            },
            {"name": "happy_path_evidence_valid", "passed": len(happy_errors) == 0, "detail": {"errors": happy_errors}},
            {
                "name": "blocked_path_evidence_valid",
                "passed": len(blocked_errors) == 0,
                "detail": {"errors": blocked_errors},
            },
            {
                "name": "open_intercompany_within_threshold",
                "passed": int(health.get("open_intercompany_count") or 0) <= int(options.get("max_open_intercompany") or 0),
                "detail": {
                    "count": int(health.get("open_intercompany_count") or 0),
                    "max_allowed": int(options.get("max_open_intercompany") or 0),
                },
            },
            {
                "name": "disputed_intercompany_within_threshold",
                "passed": int(health.get("disputed_intercompany_count") or 0)
                <= int(options.get("max_disputed_intercompany") or 0),
                "detail": {
                    "count": int(health.get("disputed_intercompany_count") or 0),
                    "max_allowed": int(options.get("max_disputed_intercompany") or 0),
                },
            },
            {
                "name": "open_outside_sla_within_threshold",
                "passed": int(health.get("open_outside_sla_count") or 0) <= int(options.get("max_open_outside_sla") or 0),
                "detail": {
                    "count": int(health.get("open_outside_sla_count") or 0),
                    "max_allowed": int(options.get("max_open_outside_sla") or 0),
                },
            },
            {
                "name": "disputed_outside_sla_within_threshold",
                "passed": int(health.get("disputed_outside_sla_count") or 0)
                <= int(options.get("max_disputed_outside_sla") or 0),
                "detail": {
                    "count": int(health.get("disputed_outside_sla_count") or 0),
                    "max_allowed": int(options.get("max_disputed_outside_sla") or 0),
                },
            },
            {
                "name": "stale_confirmed_unclosed_within_threshold",
                "passed": int(health.get("stale_confirmed_unclosed_count") or 0)
                <= int(options.get("max_stale_confirmed_unclosed") or 0),
                "detail": {
                    "count": int(health.get("stale_confirmed_unclosed_count") or 0),
                    "max_allowed": int(options.get("max_stale_confirmed_unclosed") or 0),
                },
            },
            {
                "name": "open_blocking_exceptions_within_threshold",
                "passed": int(health.get("open_intercompany_blocking_exception_count") or 0)
                <= int(options.get("max_open_blocking_exceptions") or 0),
                "detail": {
                    "count": int(health.get("open_intercompany_blocking_exception_count") or 0),
                    "max_allowed": int(options.get("max_open_blocking_exceptions") or 0),
                },
            },
            {
                "name": "blocked_consolidation_within_threshold",
                "passed": int(health.get("blocked_consolidation_count") or 0)
                <= int(options.get("max_blocked_consolidation") or 0),
                "detail": {
                    "count": int(health.get("blocked_consolidation_count") or 0),
                    "max_allowed": int(options.get("max_blocked_consolidation") or 0),
                },
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
        ]
        go_live_passed = all(bool(item["passed"]) for item in checks)

        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"company_id": int(company_id)},
            "consumer": consumer,
            "go_live_passed": bool(go_live_passed),
            "checks": checks,
            "parity_mismatches": parity_mismatches,
            "health": health,
            "evidence": evidence_refs,
        }

        secret = str(os.getenv("PHASE11_EVIDENCE_SECRET", os.getenv("PHASE7B_EVIDENCE_SECRET", ""))).strip()
        signed = build_phase11_evidence(payload=report, secret=secret)
        raw = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase11 go-live report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not go_live_passed:
            raise CommandError("phase11 go-live gate failed.")
