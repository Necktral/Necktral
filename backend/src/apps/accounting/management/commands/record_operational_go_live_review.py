from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Registra revisión/aprobación de go-live operacional (owner funcional/técnico)."

    VALID_STATUS = ("OBSERVED", "APPROVED", "FINAL_APPROVED")
    VALID_ROLE = ("FUNCTIONAL", "TECHNICAL")

    def add_arguments(self, parser):
        parser.add_argument("--evidence-dir", type=str, required=True)
        parser.add_argument("--date", type=str, default="")
        parser.add_argument("--reviewer", type=str, required=True)
        parser.add_argument("--role", type=str, required=True, choices=self.VALID_ROLE)
        parser.add_argument("--status", type=str, required=True, choices=self.VALID_STATUS)
        parser.add_argument("--summary", type=str, required=True)
        parser.add_argument("--linked-evidence", nargs="*", default=[])
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args, **options):
        evidence_dir = Path(str(options["evidence_dir"]).strip())
        if not evidence_dir.exists() or not evidence_dir.is_dir():
            raise CommandError(f"directorio inválido: {evidence_dir}")

        review_date_raw = str(options.get("date") or "").strip() or timezone.localdate().isoformat()
        try:
            review_date = date.fromisoformat(review_date_raw).isoformat()
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"date inválida (ISO-8601 esperado): {review_date_raw}") from exc

        reviewer = str(options.get("reviewer") or "").strip()
        role = str(options.get("role") or "").strip().upper()
        status = str(options.get("status") or "").strip().upper()
        summary = str(options.get("summary") or "").strip()
        if not reviewer:
            raise CommandError("reviewer es requerido")
        if role not in self.VALID_ROLE:
            raise CommandError(f"role inválido: {role}")
        if status not in self.VALID_STATUS:
            raise CommandError(f"status inválido: {status}")
        if not summary:
            raise CommandError("summary es requerido")

        linked_evidence = [str(x).strip() for x in (options.get("linked_evidence") or []) if str(x).strip()]

        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "review_date": review_date,
            "reviewer": reviewer,
            "role": role,
            "status": status,
            "summary": summary,
            "linked_evidence": linked_evidence,
            "final_signoff": status == "FINAL_APPROVED",
        }
        raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
        elif status == "FINAL_APPROVED":
            path = evidence_dir / "operational_go_live_final_signoff.json"
        else:
            ts = timezone.localtime().strftime("%Y%m%d_%H%M%S")
            path = evidence_dir / f"operational_go_live_review_{role}_{ts}.json"

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"operational go-live review exported: {path}"))
