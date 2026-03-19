from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.certification_phase7b import build_phase7b_evidence, certify_phase7b_consolidation


class Command(BaseCommand):
    help = "Certifica consolidación 7B (determinismo + path esperado blocked/happy)."

    def add_arguments(self, parser):
        parser.add_argument("--parent-company-id", type=int, required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument("--company-ids", type=int, nargs="+", required=True)
        parser.add_argument("--expect-blocked", action="store_true", default=False)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        parent_company_id = int(options["parent_company_id"])
        year = int(options["year"])
        month = int(options["month"])
        company_ids = [int(x) for x in (options.get("company_ids") or [])]
        expect_blocked = bool(options.get("expect_blocked", False))
        output = str(options.get("output") or "").strip()

        try:
            result = certify_phase7b_consolidation(
                parent_company_id=parent_company_id,
                year=year,
                month=month,
                company_ids=company_ids,
                expect_blocked=expect_blocked,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"parent_company_id": parent_company_id, "company_ids": company_ids},
            "period": {"year": year, "month": month},
            "run_id": str(result.run_id),
            "passed": bool(result.passed),
            "blocked": bool(result.blocked),
            "deterministic_replay": bool(result.deterministic_replay),
            "first_status": str(result.first_status),
            "second_status": str(result.second_status),
            "first_manifest_hash": str(result.first_manifest_hash),
            "second_manifest_hash": str(result.second_manifest_hash),
            "first_metrics": result.first_metrics,
            "second_metrics": result.second_metrics,
            "go_live_passed": bool(result.passed),
        }
        secret = str(os.getenv("PHASE7B_EVIDENCE_SECRET", "")).strip()
        signed_payload = build_phase7b_evidence(payload=payload, secret=secret)
        raw = json.dumps(signed_payload, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase7b consolidation certification exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(result.passed):
            raise CommandError("phase7b consolidation certification failed.")
