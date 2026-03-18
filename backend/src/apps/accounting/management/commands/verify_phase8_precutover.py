from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.phase8 import (
    build_phase8_evidence,
    collect_phase8_operational_health,
    compare_phase8_env_manifests,
)


class Command(BaseCommand):
    help = "Gate de pre-corte F8 (paridad + preflight + snapshot + seguridad vigente)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--parent-company-id", type=int, required=True)
        parser.add_argument("--company-ids", type=int, nargs="+", required=True)
        parser.add_argument("--staging-manifest", type=str, required=True)
        parser.add_argument("--prod-manifest", type=str, required=True)
        parser.add_argument("--release-baseline", type=str, required=True)
        parser.add_argument("--preflight-report", type=str, required=True)
        parser.add_argument("--snapshot-report", type=str, required=True)
        parser.add_argument("--security-summary", type=str, required=True)
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
    def _check_gate_payload(payload: dict[str, Any], field_name: str, gate_key: str) -> tuple[bool, dict[str, Any]]:
        passed = bool(payload.get(gate_key))
        return (
            passed,
            {
                "file": field_name,
                gate_key: passed,
                "evidence_hash": str(payload.get("evidence_hash") or ""),
            },
        )

    @staticmethod
    def _check_security_summary(payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        checks = dict(payload.get("checks") or {})
        gate_keys = (
            "gitleaks_clean",
            "pip_audit_blocking_clean",
            "npm_audit_blocking_clean",
            "manage_check_pass",
            "audit_chain_pass",
            "security_pytest_pass",
        )
        details: dict[str, Any] = {"status": str(payload.get("status") or ""), "checks": {}}
        passed = str(payload.get("status") or "").upper() == "PASS"
        for key in gate_keys:
            key_passed = bool(checks.get(key))
            details["checks"][key] = key_passed
            passed = passed and key_passed
        return passed, details

    @staticmethod
    def _check_release_baseline(payload: dict[str, Any], prod_manifest: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        baseline_hashes = dict(payload.get("baseline_hashes") or {})
        phase6 = dict(prod_manifest.get("phase6") or {})
        phase7 = dict(prod_manifest.get("phase7") or {})
        expected = {
            "phase6_migrations_hash": str(phase6.get("migrations_hash") or ""),
            "phase6_required_permissions_hash": str(phase6.get("required_permissions_hash") or ""),
            "phase6_branch_fiscal_config_hash": str(phase6.get("branch_fiscal_config_hash") or ""),
            "phase7_migrations_hash": str(phase7.get("migrations_hash") or ""),
            "phase7_required_permissions_hash": str(phase7.get("required_permissions_hash") or ""),
            "phase7_accounting_config_hash": str(phase7.get("accounting_config_hash") or ""),
            "phase7_chart_of_accounts_hash": str(phase7.get("chart_of_accounts_hash") or ""),
            "phase8_parity_fingerprint": str(prod_manifest.get("parity_fingerprint") or ""),
        }
        mismatches: list[dict[str, str]] = []
        for key, value in expected.items():
            left = str(baseline_hashes.get(key) or "")
            right = str(value or "")
            if left != right:
                mismatches.append({"field": key, "baseline": left, "manifest": right})
        return len(mismatches) == 0, {"mismatches": mismatches, "count": len(mismatches)}

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        parent_company_id = int(options["parent_company_id"])
        company_ids = sorted({int(x) for x in (options.get("company_ids") or [])})
        output = str(options.get("output") or "").strip()
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"

        staging_manifest = self._read_json(options["staging_manifest"])
        prod_manifest = self._read_json(options["prod_manifest"])
        release_baseline = self._read_json(options["release_baseline"])
        preflight_report = self._read_json(options["preflight_report"])
        snapshot_report = self._read_json(options["snapshot_report"])
        security_summary = self._read_json(options["security_summary"])

        parity_mismatches = compare_phase8_env_manifests(left=staging_manifest, right=prod_manifest)

        preflight_passed, preflight_detail = self._check_gate_payload(
            preflight_report,
            field_name=str(options["preflight_report"]),
            gate_key="preflight_passed",
        )
        snapshot_passed, snapshot_detail = self._check_gate_payload(
            snapshot_report,
            field_name=str(options["snapshot_report"]),
            gate_key="snapshot_passed",
        )
        baseline_passed, baseline_detail = self._check_release_baseline(release_baseline, prod_manifest)
        security_passed, security_detail = self._check_security_summary(security_summary)

        health = collect_phase8_operational_health(
            company_id=company_id,
            branch_id=branch_id,
            parent_company_id=parent_company_id,
            consumer=consumer,
            stale_minutes=int(options.get("stale_minutes") or 30),
        )
        phase6 = dict(health.get("phase6") or {})
        phase7a = dict(health.get("phase7a") or {})
        phase7b = dict(health.get("phase7b") or {})

        checks = [
            {
                "name": "parity_no_drift",
                "passed": len(parity_mismatches) == 0,
                "detail": {"count": len(parity_mismatches)},
            },
            {
                "name": "preflight_passed",
                "passed": bool(preflight_passed),
                "detail": preflight_detail,
            },
            {
                "name": "snapshot_passed",
                "passed": bool(snapshot_passed),
                "detail": snapshot_detail,
            },
            {
                "name": "release_baseline_matches_manifest",
                "passed": bool(baseline_passed),
                "detail": baseline_detail,
            },
            {
                "name": "security_summary_passed",
                "passed": bool(security_passed),
                "detail": security_detail,
            },
            {
                "name": "inbox_failed_within_threshold",
                "passed": max(
                    int(phase6.get("inbox_failed_count") or 0),
                    int(phase7a.get("inbox_failed_count") or 0),
                    int(phase7b.get("inbox_failed_count") or 0),
                )
                <= int(options.get("max_inbox_failed") or 0),
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
                )
                <= int(options.get("max_outbox_failed") or 0),
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
        precutover_passed = all(bool(row["passed"]) for row in checks)
        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {
                "company_id": company_id,
                "branch_id": branch_id,
                "parent_company_id": parent_company_id,
                "company_ids": company_ids,
            },
            "consumer": consumer,
            "precutover_passed": bool(precutover_passed),
            "checks": checks,
            "parity_mismatches": parity_mismatches,
            "health": health,
            "references": {
                "staging_manifest": str(options["staging_manifest"]),
                "prod_manifest": str(options["prod_manifest"]),
                "release_baseline": str(options["release_baseline"]),
                "preflight_report": str(options["preflight_report"]),
                "snapshot_report": str(options["snapshot_report"]),
                "security_summary": str(options["security_summary"]),
            },
        }

        secret = str(os.getenv("PHASE8_EVIDENCE_SECRET", "")).strip()
        signed = build_phase8_evidence(payload=report, secret=secret)
        raw = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase8 pre-cutover report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not precutover_passed:
            raise CommandError("phase8 pre-cutover gate failed")
