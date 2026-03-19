from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.certification_phase7b import build_phase7b_evidence
from apps.modulos.accounting.phase7b import Phase7BValidationError, run_consolidation
from apps.modulos.integration.services import dispatch_outbox_events


class Command(BaseCommand):
    help = "Ejecuta cierre consolidado 7B para un periodo y scope de compañías."

    def add_arguments(self, parser):
        parser.add_argument("--parent-company-id", type=int, required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument("--company-ids", type=int, nargs="+", required=True)
        parser.add_argument("--dispatch-limit", type=int, default=200)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        parent_company_id = int(options["parent_company_id"])
        year = int(options["year"])
        month = int(options["month"])
        company_ids = [int(x) for x in (options.get("company_ids") or [])]
        dispatch_limit = int(options.get("dispatch_limit") or 200)
        output = str(options.get("output") or "").strip()

        try:
            result = run_consolidation(
                parent_company_id=parent_company_id,
                year=year,
                month=month,
                company_ids=company_ids,
                strict=True,
                actor_user=None,
            )
        except Phase7BValidationError as exc:
            raise CommandError(str(exc)) from exc

        dispatch = dispatch_outbox_events(limit=dispatch_limit, source_module="ACCOUNTING")
        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"parent_company_id": parent_company_id, "company_ids": company_ids},
            "period": {"year": year, "month": month},
            "run_id": str(result.run_id),
            "status": str(result.status),
            "idempotent": bool(result.idempotent),
            "manifest_hash": str(result.manifest_hash),
            "issues_count": int(result.issues_count),
            "summary": result.summary_json,
            "dispatch": {
                "attempted": int(dispatch.attempted),
                "sent": int(dispatch.sent),
                "retried": int(dispatch.retried),
                "failed": int(dispatch.failed),
            },
            "close_passed": str(result.status) == "COMPLETED",
        }
        secret = str(os.getenv("PHASE7B_EVIDENCE_SECRET", "")).strip()
        signed_payload = build_phase7b_evidence(payload=payload, secret=secret)
        raw = json.dumps(signed_payload, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"consolidated close report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(payload["close_passed"]):
            raise CommandError("consolidated close gate failed.")
