from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.phase8 import build_phase8_evidence


class Command(BaseCommand):
    help = "Verifica evidencia de revisión del contador para cierre F8."

    def add_arguments(self, parser):
        parser.add_argument("--evidence-dir", type=str, required=True)
        parser.add_argument("--window-start", type=str, default="")
        parser.add_argument("--window-end", type=str, default="")
        parser.add_argument("--output", type=str, default="")
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

    @staticmethod
    def _parse_date(raw: str, *, default: date | None = None) -> date | None:
        text = str(raw or "").strip()
        if not text:
            return default
        try:
            return date.fromisoformat(text)
        except Exception:
            return default

    @staticmethod
    def _parse_generated_at(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
        except Exception:
            return ""

    def handle(self, *args, **options):
        evidence_dir = Path(str(options["evidence_dir"]).strip())
        if not evidence_dir.exists() or not evidence_dir.is_dir():
            raise CommandError(f"directorio inválido: {evidence_dir}")

        window_start = self._parse_date(str(options.get("window_start") or ""), default=date(1970, 1, 1))
        window_end = self._parse_date(str(options.get("window_end") or ""), default=date(9999, 12, 31))
        if window_start is None or window_end is None or window_start > window_end:
            raise CommandError("window-start/window-end inválidos")

        review_files = sorted(evidence_dir.glob("63_phase8_accountant_review_*.json"))
        final_file = evidence_dir / "64_phase8_accountant_final_signoff.json"
        if final_file.exists():
            review_files.append(final_file)

        rows: list[dict[str, Any]] = []
        for path in review_files:
            payload = self._read_json(path)
            if payload is None:
                continue
            status = str(payload.get("status") or "").strip().upper()
            if status not in {"OBSERVED", "APPROVED", "FINAL_APPROVED"}:
                continue
            review_date = self._parse_date(str(payload.get("review_date") or ""))
            if review_date is None:
                continue
            if review_date < window_start or review_date > window_end:
                continue
            rows.append(
                {
                    "file": path.name,
                    "review_date": review_date.isoformat(),
                    "status": status,
                    "reviewer": str(payload.get("reviewer") or ""),
                    "summary": str(payload.get("summary") or ""),
                    "generated_at": self._parse_generated_at(str(payload.get("generated_at") or "")),
                }
            )

        rows.sort(key=lambda row: (str(row["review_date"]), str(row["generated_at"]), str(row["file"])))

        status_by_day: dict[str, str] = {}
        for row in rows:
            status_by_day[str(row["review_date"])] = str(row["status"])

        open_observations = sorted([day for day, status in status_by_day.items() if status == "OBSERVED"])
        final_rows = [row for row in rows if str(row.get("status")) == "FINAL_APPROVED"]
        final_approved_present = len(final_rows) > 0
        final_signoff = final_rows[-1] if final_rows else None

        checks = [
            {
                "name": "final_approved_present",
                "passed": bool(final_approved_present),
                "detail": {"count": len(final_rows)},
            },
            {
                "name": "open_observations_resolved",
                "passed": len(open_observations) == 0,
                "detail": {"open_observations": open_observations},
            },
        ]
        signoff_passed = all(bool(check["passed"]) for check in checks)

        report = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "policy": "ON_DEMAND_FINAL_REQUIRED",
            "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
            "signoff_passed": bool(signoff_passed),
            "final_approved_present": bool(final_approved_present),
            "final_signoff": final_signoff or {},
            "open_observations": open_observations,
            "status_by_day": status_by_day,
            "rows": rows,
            "checks": checks,
        }

        secret = str(os.getenv("PHASE8_EVIDENCE_SECRET", "")).strip()
        signed = build_phase8_evidence(payload=report, secret=secret)
        raw = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True)

        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase8 accountant signoff verification exported: {path}"))
        else:
            self.stdout.write(raw)

        if bool(options.get("strict")) and not signoff_passed:
            raise CommandError("phase8 accountant signoff verification failed")
