from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.certification_phase12 import (
    FX_BLOCKED_POLICY_BLOCK,
    build_phase12_evidence,
    normalize_fx_blocked_policy,
)


class Command(BaseCommand):
    help = "Verifica SLO operacional de Fase 12 sobre evidencias mensuales."

    def add_arguments(self, parser):
        parser.add_argument("--evidence-dir", type=str, required=True)
        parser.add_argument("--pattern", type=str, default="phase12_monthly_close_*.json")
        parser.add_argument("--min-periods", type=int, default=3)
        parser.add_argument("--max-failed-periods", type=int, default=0)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-missing-lines", type=int, default=0)
        parser.add_argument("--max-stale-revaluation", type=int, default=0)
        parser.add_argument("--max-open-intercompany", type=int, default=0)
        parser.add_argument("--max-disputed-intercompany", type=int, default=0)
        parser.add_argument("--fx-blocked-policy", type=str, default="ALERT")
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"JSON inválido en {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise CommandError(f"JSON inválido en {path}: se esperaba objeto")
        return payload

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        evidence_dir = Path(str(options["evidence_dir"]))
        pattern = str(options.get("pattern") or "phase12_monthly_close_*.json")
        output = str(options.get("output") or "").strip()
        fx_policy = normalize_fx_blocked_policy(str(options.get("fx_blocked_policy") or "ALERT"))

        if not evidence_dir.exists():
            raise CommandError(f"evidence-dir no existe: {evidence_dir}")
        files = sorted(evidence_dir.glob(pattern))
        if not files:
            raise CommandError(f"no se encontraron evidencias con patrón {pattern} en {evidence_dir}")

        reports: list[dict[str, Any]] = []
        for path in files:
            payload = self._read_json(path)
            period = dict(payload.get("period") or {})
            year = int(period.get("year") or 0)
            month = int(period.get("month") or 0)
            if year <= 0 or month <= 0:
                continue
            reports.append(
                {
                    "path": str(path),
                    "year": year,
                    "month": month,
                    "cycle_passed": bool(payload.get("cycle_passed")),
                    "health": dict(payload.get("health") or {}),
                }
            )

        if not reports:
            raise CommandError("no hay reportes fase12 válidos con period/year/month.")

        reports.sort(key=lambda x: (int(x["year"]), int(x["month"])))
        unique_periods = sorted({(int(r["year"]), int(r["month"])) for r in reports})
        failed_periods = [r for r in reports if not bool(r["cycle_passed"])]

        threshold_violations: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for row in reports:
            health = dict(row.get("health") or {})
            phase7 = dict(health.get("phase7a") or {})
            phase7b = dict(health.get("phase7b") or {})
            payload = self._read_json(Path(str(row["path"])))
            revaluation = dict(payload.get("revaluation") or {})
            revaluation_status = str(revaluation.get("status") or "")
            fx_blocked_warning = bool(revaluation.get("fx_blocked_warning"))
            checks = [
                ("inbox_failed_count", int(health.get("inbox_failed_count") or 0), int(options.get("max_inbox_failed") or 0)),
                (
                    "outbox_failed_count",
                    int(health.get("outbox_failed_count") or 0),
                    int(options.get("max_outbox_failed") or 0),
                ),
                (
                    "missing_lines_count",
                    int(phase7.get("missing_lines_count") or 0),
                    int(options.get("max_missing_lines") or 0),
                ),
                (
                    "stale_revaluation_count",
                    int(phase7.get("stale_revaluation_count") or 0),
                    int(options.get("max_stale_revaluation") or 0),
                ),
                (
                    "open_intercompany_count",
                    int(phase7b.get("open_intercompany_count") or 0),
                    int(options.get("max_open_intercompany") or 0),
                ),
                (
                    "disputed_intercompany_count",
                    int(phase7b.get("disputed_intercompany_count") or 0),
                    int(options.get("max_disputed_intercompany") or 0),
                ),
            ]
            for metric, value, max_allowed in checks:
                if int(value) > int(max_allowed):
                    threshold_violations.append(
                        {
                            "path": str(row["path"]),
                            "period": {"year": int(row["year"]), "month": int(row["month"])},
                            "metric": metric,
                            "value": int(value),
                            "max_allowed": int(max_allowed),
                        }
                    )

            if revaluation_status == "BLOCKED":
                if fx_policy == FX_BLOCKED_POLICY_BLOCK:
                    threshold_violations.append(
                        {
                            "path": str(row["path"]),
                            "period": {"year": int(row["year"]), "month": int(row["month"])},
                            "metric": "fx_blocked_not_allowed",
                            "value": 1,
                            "max_allowed": 0,
                        }
                    )
                else:
                    warnings.append(
                        {
                            "code": "FX_REVALUATION_BLOCKED",
                            "period": {"year": int(row["year"]), "month": int(row["month"])},
                            "path": str(row["path"]),
                        }
                    )
                    if not fx_blocked_warning:
                        threshold_violations.append(
                            {
                                "path": str(row["path"]),
                                "period": {"year": int(row["year"]), "month": int(row["month"])},
                                "metric": "fx_blocked_without_warning_flag",
                                "value": 1,
                                "max_allowed": 0,
                            }
                        )

        checks = [
            {
                "name": "minimum_periods_covered",
                "passed": len(unique_periods) >= int(options.get("min_periods") or 3),
                "detail": {"periods": [f"{y:04d}-{m:02d}" for y, m in unique_periods], "count": len(unique_periods)},
            },
            {
                "name": "failed_periods_within_threshold",
                "passed": len(failed_periods) <= int(options.get("max_failed_periods") or 0),
                "detail": {
                    "failed_count": len(failed_periods),
                    "max_allowed": int(options.get("max_failed_periods") or 0),
                    "failed_periods": [f"{int(r['year']):04d}-{int(r['month']):02d}" for r in failed_periods],
                },
            },
            {
                "name": "threshold_violations_empty",
                "passed": len(threshold_violations) == 0,
                "detail": {"count": len(threshold_violations)},
            },
        ]
        slo_passed = all(bool(item["passed"]) for item in checks)

        report = {
            "schema_version": 2,
            "generated_at": timezone.now().isoformat(),
            "evidence_dir": str(evidence_dir),
            "pattern": pattern,
            "slo_passed": bool(slo_passed),
            "fx_policy_applied": fx_policy,
            "checks": checks,
            "periods": [f"{y:04d}-{m:02d}" for y, m in unique_periods],
            "failed_periods": [f"{int(r['year']):04d}-{int(r['month']):02d}" for r in failed_periods],
            "threshold_violations": threshold_violations,
            "warnings": warnings,
        }
        secret = str(os.getenv("PHASE12_EVIDENCE_SECRET", "")).strip()
        signed_report = build_phase12_evidence(payload=report, secret=secret)
        raw = json.dumps(signed_report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase12 operational slo report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not slo_passed:
            raise CommandError("phase12 operational slo gate failed.")
