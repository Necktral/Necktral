from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.certification_phase12 import (
    FX_BLOCKED_POLICY_BLOCK,
    build_phase12_evidence,
    collect_phase12_operational_health,
    compare_phase12_env_manifests,
    normalize_fx_blocked_policy,
)


class Command(BaseCommand):
    help = "Gate final Fase 12 (paridad + determinismo + SLO + salud operativa)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--staging-manifest", type=str, default="")
        parser.add_argument("--prod-manifest", type=str, default="")
        parser.add_argument("--determinism-evidence", type=str, required=True)
        parser.add_argument("--slo-evidence", type=str, required=True)
        parser.add_argument("--fx-blocked-policy", type=str, default="ALERT")
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-missing-lines", type=int, default=0)
        parser.add_argument("--max-stale-revaluation", type=int, default=0)
        parser.add_argument("--max-open-intercompany", type=int, default=0)
        parser.add_argument("--max-disputed-intercompany", type=int, default=0)
        parser.add_argument("--max-blocked-consolidation", type=int, default=0)
        parser.add_argument("--max-open-consolidation-exception", type=int, default=0)
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
    def _validate_determinism(payload: dict[str, Any], *, fx_policy: str) -> tuple[list[str], list[dict[str, Any]]]:
        errors: list[str] = []
        warnings: list[dict[str, Any]] = []
        if bool(payload.get("passed")) is not True:
            errors.append("determinism.passed debe ser true.")
        if bool(payload.get("go_live_passed")) is not True:
            errors.append("determinism.go_live_passed debe ser true.")
        if bool(payload.get("deterministic_replay")) is not True:
            errors.append("determinism.deterministic_replay debe ser true.")
        first_hash = str(payload.get("first_manifest_hash") or "")
        second_hash = str(payload.get("second_manifest_hash") or "")
        if not first_hash or not second_hash or first_hash != second_hash:
            errors.append("first_manifest_hash y second_manifest_hash deben coincidir.")

        second_report = dict(payload.get("second_report") or {})
        revaluation = dict(second_report.get("revaluation") or {})
        status = str(revaluation.get("status") or "")
        fx_warn = bool(revaluation.get("fx_blocked_warning"))
        if status == "FAILED":
            errors.append("revaluation.status=FAILED no permitido en gate F12.")
        elif status == "BLOCKED":
            if fx_policy == FX_BLOCKED_POLICY_BLOCK:
                errors.append("revaluation.status=BLOCKED no permitido con fx_blocked_policy=BLOCK.")
            else:
                warnings.append(
                    {
                        "code": "FX_REVALUATION_BLOCKED",
                        "severity": "WARN",
                        "message": "Revaluación FX bloqueada aceptada por política ALERT.",
                    }
                )
                if not fx_warn:
                    errors.append("revaluation.fx_blocked_warning debe ser true cuando status=BLOCKED.")
        elif status != "COMPLETED":
            errors.append(f"revaluation.status inválido para gate: {status}")

        return errors, warnings

    @staticmethod
    def _validate_slo(payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if bool(payload.get("slo_passed")) is not True:
            errors.append("slo_passed debe ser true.")
        if int(len(payload.get("threshold_violations") or [])) > 0:
            errors.append("threshold_violations debe estar vacío.")
        return errors

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        output = str(options.get("output") or "").strip()
        fx_policy = normalize_fx_blocked_policy(str(options.get("fx_blocked_policy") or "ALERT"))

        determinism = self._read_json(str(options["determinism_evidence"]))
        slo = self._read_json(str(options["slo_evidence"]))

        parity_mismatches: list[dict[str, str]] = []
        staging_manifest_path = str(options.get("staging_manifest") or "").strip()
        prod_manifest_path = str(options.get("prod_manifest") or "").strip()
        if staging_manifest_path and prod_manifest_path:
            staging_manifest = self._read_json(staging_manifest_path)
            prod_manifest = self._read_json(prod_manifest_path)
            parity_mismatches = compare_phase12_env_manifests(left=staging_manifest, right=prod_manifest)

        determinism_errors, determinism_warnings = self._validate_determinism(determinism, fx_policy=fx_policy)
        slo_errors = self._validate_slo(slo)
        warnings = [*determinism_warnings, *list(slo.get("warnings") or [])]

        health = collect_phase12_operational_health(company_id=company_id, consumer=consumer)
        phase7 = dict(health.get("phase7a") or {})
        phase7b = dict(health.get("phase7b") or {})

        checks = [
            {
                "name": "parity_no_drift",
                "passed": len(parity_mismatches) == 0,
                "detail": {"mismatches_count": len(parity_mismatches)},
            },
            {
                "name": "determinism_evidence_valid",
                "passed": len(determinism_errors) == 0,
                "detail": {"errors": determinism_errors},
            },
            {
                "name": "slo_evidence_valid",
                "passed": len(slo_errors) == 0,
                "detail": {"errors": slo_errors},
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
                "name": "missing_lines_within_threshold",
                "passed": int(phase7.get("missing_lines_count") or 0) <= int(options.get("max_missing_lines") or 0),
                "detail": {
                    "count": int(phase7.get("missing_lines_count") or 0),
                    "max_allowed": int(options.get("max_missing_lines") or 0),
                },
            },
            {
                "name": "stale_revaluation_within_threshold",
                "passed": int(phase7.get("stale_revaluation_count") or 0) <= int(options.get("max_stale_revaluation") or 0),
                "detail": {
                    "count": int(phase7.get("stale_revaluation_count") or 0),
                    "max_allowed": int(options.get("max_stale_revaluation") or 0),
                },
            },
            {
                "name": "open_intercompany_within_threshold",
                "passed": int(phase7b.get("open_intercompany_count") or 0) <= int(options.get("max_open_intercompany") or 0),
                "detail": {
                    "count": int(phase7b.get("open_intercompany_count") or 0),
                    "max_allowed": int(options.get("max_open_intercompany") or 0),
                },
            },
            {
                "name": "disputed_intercompany_within_threshold",
                "passed": int(phase7b.get("disputed_intercompany_count") or 0) <= int(options.get("max_disputed_intercompany") or 0),
                "detail": {
                    "count": int(phase7b.get("disputed_intercompany_count") or 0),
                    "max_allowed": int(options.get("max_disputed_intercompany") or 0),
                },
            },
            {
                "name": "blocked_consolidation_within_threshold",
                "passed": int(phase7b.get("blocked_consolidation_count") or 0) <= int(options.get("max_blocked_consolidation") or 0),
                "detail": {
                    "count": int(phase7b.get("blocked_consolidation_count") or 0),
                    "max_allowed": int(options.get("max_blocked_consolidation") or 0),
                },
            },
            {
                "name": "open_consolidation_exception_within_threshold",
                "passed": int(phase7b.get("open_consolidation_exception_count") or 0)
                <= int(options.get("max_open_consolidation_exception") or 0),
                "detail": {
                    "count": int(phase7b.get("open_consolidation_exception_count") or 0),
                    "max_allowed": int(options.get("max_open_consolidation_exception") or 0),
                },
            },
        ]
        go_live_passed = all(bool(item["passed"]) for item in checks)
        risk_level = "HIGH"
        if go_live_passed:
            risk_level = "MEDIUM" if warnings else "LOW"

        report = {
            "schema_version": 2,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"company_id": int(company_id)},
            "consumer": consumer,
            "fx_policy_applied": fx_policy,
            "go_live_passed": bool(go_live_passed),
            "phase12_go_live_passed": bool(go_live_passed),
            "risk_level": risk_level,
            "checks": checks,
            "warnings": warnings,
            "parity_mismatches": parity_mismatches,
            "health": health,
            "evidence": {
                "determinism_evidence": str(options["determinism_evidence"]),
                "slo_evidence": str(options["slo_evidence"]),
            },
        }
        secret = str(os.getenv("PHASE12_EVIDENCE_SECRET", "")).strip()
        signed_report = build_phase12_evidence(payload=report, secret=secret)
        raw = json.dumps(signed_report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase12 go-live report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not go_live_passed:
            raise CommandError("phase12 go-live gate failed.")
