from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.certification_phase7b import build_phase7b_evidence
from apps.modulos.accounting.phase7b import Phase7BValidationError, run_intercompany_cycle
from apps.modulos.integration.services import dispatch_outbox_events


class Command(BaseCommand):
    help = "Ejecuta ciclo operativo intercompany (matching/conciliación) para una compañía."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--dispatch-limit", type=int, default=200)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        limit = int(options.get("limit") or 200)
        dispatch_limit = int(options.get("dispatch_limit") or 200)
        output = str(options.get("output") or "").strip()

        try:
            cycle = run_intercompany_cycle(
                company_id=company_id,
                limit=limit,
                strict=False,
                actor_user=None,
            )
        except Phase7BValidationError as exc:
            raise CommandError(str(exc)) from exc

        dispatch = dispatch_outbox_events(limit=dispatch_limit, source_module="ACCOUNTING")
        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "company_id": int(company_id),
            "strict": bool(strict),
            "cycle": cycle.report,
            "dispatch": {
                "attempted": int(dispatch.attempted),
                "sent": int(dispatch.sent),
                "retried": int(dispatch.retried),
                "failed": int(dispatch.failed),
            },
            "cycle_passed": int(cycle.report.get("issues_count") or 0) == 0,
        }
        secret = str(os.getenv("PHASE7B_EVIDENCE_SECRET", "")).strip()
        signed_payload = build_phase7b_evidence(payload=payload, secret=secret)
        raw = json.dumps(signed_payload, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"intercompany cycle report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(payload["cycle_passed"]):
            raise CommandError("intercompany cycle gate failed.")
