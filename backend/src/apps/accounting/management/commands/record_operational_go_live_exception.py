from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Registra una excepción auditable (fuerza mayor) para ventana de go-live operacional."

    VALID_EXCEPTION_TYPE = ("FORCE_MAJEURE",)
    VALID_STATUS = ("APPROVED", "FINAL_APPROVED")

    def add_arguments(self, parser):
        parser.add_argument("--evidence-dir", type=str, required=True)
        parser.add_argument("--date", type=str, default="")
        parser.add_argument("--exception-type", type=str, default="FORCE_MAJEURE", choices=self.VALID_EXCEPTION_TYPE)
        parser.add_argument("--status", type=str, default="APPROVED", choices=self.VALID_STATUS)
        parser.add_argument("--reported-by", type=str, required=True)
        parser.add_argument("--approved-by", type=str, required=True)
        parser.add_argument("--summary", type=str, required=True)
        parser.add_argument("--impact", type=str, default="")
        parser.add_argument("--linked-evidence", nargs="*", default=[])
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args, **options):
        evidence_dir = Path(str(options["evidence_dir"]).strip())
        if not evidence_dir.exists() or not evidence_dir.is_dir():
            raise CommandError(f"directorio inválido: {evidence_dir}")

        exception_date_raw = str(options.get("date") or "").strip() or timezone.localdate().isoformat()
        try:
            exception_date = date.fromisoformat(exception_date_raw).isoformat()
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"date inválida (ISO-8601 esperado): {exception_date_raw}") from exc

        exception_type = str(options.get("exception_type") or "FORCE_MAJEURE").strip().upper()
        status = str(options.get("status") or "APPROVED").strip().upper()
        reported_by = str(options.get("reported_by") or "").strip()
        approved_by = str(options.get("approved_by") or "").strip()
        summary = str(options.get("summary") or "").strip()
        impact = str(options.get("impact") or "").strip()
        if exception_type not in self.VALID_EXCEPTION_TYPE:
            raise CommandError(f"exception-type inválido: {exception_type}")
        if status not in self.VALID_STATUS:
            raise CommandError(f"status inválido: {status}")
        if not reported_by:
            raise CommandError("reported-by es requerido")
        if not approved_by:
            raise CommandError("approved-by es requerido")
        if not summary:
            raise CommandError("summary es requerido")

        linked_evidence_raw = options.get("linked_evidence") or []
        linked_evidence = [str(item).strip() for item in linked_evidence_raw if str(item).strip()]

        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "exception_date": exception_date,
            "exception_type": exception_type,
            "status": status,
            "reported_by": reported_by,
            "approved_by": approved_by,
            "summary": summary,
            "impact": impact,
            "linked_evidence": linked_evidence,
        }
        raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
        else:
            ts = timezone.localtime().strftime("%Y%m%d_%H%M%S")
            path = evidence_dir / f"operational_go_live_excused_day_{exception_type}_{ts}.json"

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"operational go-live exception exported: {path}"))
