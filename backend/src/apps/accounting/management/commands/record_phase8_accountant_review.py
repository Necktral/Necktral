from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.phase8 import build_phase8_evidence


class Command(BaseCommand):
    help = "Registra revisión on-demand del contador para F8 y genera evidencia firmada."

    VALID_STATUS = ("OBSERVED", "APPROVED", "FINAL_APPROVED")

    def add_arguments(self, parser):
        parser.add_argument("--evidence-dir", type=str, required=True)
        parser.add_argument("--date", type=str, default="")
        parser.add_argument("--reviewer", type=str, required=True)
        parser.add_argument("--status", type=str, required=True, choices=self.VALID_STATUS)
        parser.add_argument("--summary", type=str, required=True)
        parser.add_argument("--adjustments-json", type=str, default="{}")
        parser.add_argument("--linked-evidence", nargs="*", default=[])
        parser.add_argument("--output", type=str, default="")

    @staticmethod
    def _parse_adjustments(raw: str) -> Any:
        text = str(raw or "").strip() or "{}"
        try:
            return json.loads(text)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"adjustments-json inválido: {exc}") from exc

    def handle(self, *args, **options):
        evidence_dir = Path(str(options["evidence_dir"]).strip())
        if not evidence_dir.exists() or not evidence_dir.is_dir():
            raise CommandError(f"directorio inválido: {evidence_dir}")

        review_date = str(options.get("date") or "").strip() or timezone.localdate().isoformat()
        try:
            review_date = date.fromisoformat(review_date).isoformat()
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"date inválida (ISO-8601 esperado): {review_date}") from exc
        reviewer = str(options.get("reviewer") or "").strip()
        status = str(options.get("status") or "").strip().upper()
        summary = str(options.get("summary") or "").strip()
        if not reviewer:
            raise CommandError("reviewer es requerido")
        if not summary:
            raise CommandError("summary es requerido")
        if status not in self.VALID_STATUS:
            raise CommandError(f"status inválido: {status}")

        adjustments = self._parse_adjustments(str(options.get("adjustments_json") or "{}"))
        linked_evidence = [str(x).strip() for x in (options.get("linked_evidence") or []) if str(x).strip()]

        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "policy": "ON_DEMAND_FINAL_REQUIRED",
            "review_date": review_date,
            "status": status,
            "reviewer": reviewer,
            "summary": summary,
            "adjustments_json": adjustments,
            "linked_evidence": linked_evidence,
            "final_signoff": status == "FINAL_APPROVED",
        }

        secret = str(os.getenv("PHASE8_EVIDENCE_SECRET", "")).strip()
        signed = build_phase8_evidence(payload=payload, secret=secret)

        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
        elif status == "FINAL_APPROVED":
            path = evidence_dir / "64_phase8_accountant_final_signoff.json"
        else:
            ts = timezone.localtime().strftime("%Y%m%d_%H%M%S")
            path = evidence_dir / f"63_phase8_accountant_review_{ts}.json"

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"phase8 accountant review exported: {path}"))
