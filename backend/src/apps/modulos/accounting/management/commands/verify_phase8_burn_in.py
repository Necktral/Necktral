from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Verifica burn-in F8 sobre evidencias diarias (14 dias por defecto) para go-live final."

    def add_arguments(self, parser):
        parser.add_argument("--evidence-dir", type=str, required=True)
        parser.add_argument("--min-days", type=int, default=14)
        parser.add_argument("--max-failed-days", type=int, default=0)
        parser.add_argument("--strict", action="store_true", default=False)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def handle(self, *args, **options):
        evidence_dir = Path(str(options["evidence_dir"]).strip())
        min_days = max(1, int(options.get("min_days") or 7))
        max_failed_days = max(0, int(options.get("max_failed_days") or 0))
        strict = bool(options.get("strict", False))

        if not evidence_dir.exists() or not evidence_dir.is_dir():
            raise CommandError(f"directorio inválido: {evidence_dir}")

        # Solo considerar evidencias canónicas de ciclo diario.
        # Evita contaminar el cálculo con trackers auxiliares (p.ej. phase8_burnin_calendar_tracker.json).
        files = sorted(evidence_dir.glob("phase8_burn_*.json"))

        rows: list[dict[str, Any]] = []
        for path in files:
            payload = self._read_json(path)
            if payload is None:
                continue
            day_from_file = ""
            match = re.match(r"^phase8_burn_(\d{8})\.json$", path.name)
            if match:
                raw = match.group(1)
                day_from_file = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
            generated_at = str(payload.get("generated_at") or "")
            try:
                dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            except Exception:
                dt = timezone.now()
            day = day_from_file or dt.date().isoformat()
            rows.append(
                {
                    "file": path.name,
                    "date": day,
                    "cycle_passed": bool(payload.get("cycle_passed")),
                    "evidence_hash": str(payload.get("evidence_hash") or ""),
                }
            )

        if not rows:
            raise CommandError("no se encontraron evidencias burn-in válidas")

        day_map: dict[str, bool] = {}
        for row in rows:
            day = str(row["date"])
            day_map[day] = bool(day_map.get(day, False) or row["cycle_passed"])

        ordered_days = sorted(day_map.keys())
        failed_days = [d for d in ordered_days if not bool(day_map[d])]
        passed_days = [d for d in ordered_days if bool(day_map[d])]

        checks = [
            {
                "name": "minimum_days_covered",
                "passed": len(ordered_days) >= min_days,
                "detail": {"days": len(ordered_days), "min_required": min_days},
            },
            {
                "name": "failed_days_within_threshold",
                "passed": len(failed_days) <= max_failed_days,
                "detail": {"failed_days": failed_days, "max_allowed": max_failed_days},
            },
        ]
        burn_in_passed = all(bool(c["passed"]) for c in checks)

        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "burn_in_passed": bool(burn_in_passed),
            "checks": checks,
            "days": ordered_days,
            "passed_days": passed_days,
            "failed_days": failed_days,
            "rows": rows,
        }
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

        if strict and not burn_in_passed:
            raise CommandError("phase8 burn-in verification failed")
