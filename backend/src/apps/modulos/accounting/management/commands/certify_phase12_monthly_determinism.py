from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.certification_phase12 import (
    build_phase12_evidence,
    certify_phase12_monthly_determinism,
)


class Command(BaseCommand):
    help = "Certifica determinismo de cierres mensuales Fase 12 (doble corrida)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--parent-company-id", type=int, required=True)
        parser.add_argument("--company-ids", type=int, nargs="+", required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--fx-blocked-policy", type=str, default="ALERT")
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        output = str(options.get("output") or "").strip()
        company_id = int(options["company_id"])
        parent_company_id = int(options["parent_company_id"])
        company_ids = [int(x) for x in (options.get("company_ids") or [])]
        year = int(options["year"])
        month = int(options["month"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        fx_blocked_policy = str(options.get("fx_blocked_policy") or "ALERT")

        try:
            result = certify_phase12_monthly_determinism(
                company_id=company_id,
                parent_company_id=parent_company_id,
                company_ids=company_ids,
                year=year,
                month=month,
                consumer=consumer,
                fx_blocked_policy=fx_blocked_policy,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {
                "company_id": int(company_id),
                "parent_company_id": int(parent_company_id),
                "company_ids": sorted({int(x) for x in company_ids}),
            },
            "period": {"year": int(year), "month": int(month)},
            "consumer": consumer,
            "passed": bool(result.passed),
            "go_live_passed": bool(result.passed),
            "deterministic_replay": bool(result.deterministic_replay),
            "first_manifest_hash": result.first_manifest_hash,
            "second_manifest_hash": result.second_manifest_hash,
            "fx_policy_applied": result.fx_policy_applied,
            "warnings": result.warnings,
            "first_report": result.first_report,
            "second_report": result.second_report,
        }
        secret = str(os.getenv("PHASE12_EVIDENCE_SECRET", "")).strip()
        evidence = build_phase12_evidence(payload=payload, secret=secret)
        raw = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase12 monthly determinism report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(result.passed):
            raise CommandError("phase12 monthly determinism certification failed.")
