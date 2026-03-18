from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.certification_phase7 import build_phase7_evidence, certify_phase7_gl_run


class Command(BaseCommand):
    help = "Certifica ejecución real Fase 7A (posting + líneas GL + revaluación + determinismo)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--run-id", type=str, required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument("--expect-blocked", action="store_true", default=False)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        run_id = str(options["run_id"]).strip()
        year = int(options["year"])
        month = int(options["month"])
        expect_blocked = bool(options.get("expect_blocked", False))
        output = str(options.get("output") or "").strip()

        try:
            result = certify_phase7_gl_run(
                company_id=company_id,
                run_id=run_id,
                year=year,
                month=month,
                expect_blocked=expect_blocked,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"company_id": company_id},
            "run_id": str(result.run_id),
            "revaluation_run_id": str(result.revaluation_run_id),
            "passed": bool(result.passed),
            "blocked": bool(result.blocked),
            "deterministic_replay": bool(result.deterministic_replay),
            "close_run_status": str(result.close_run_status),
            "first_manifest_hash": str(result.first_manifest_hash),
            "second_manifest_hash": str(result.second_manifest_hash),
            "manifest_hash": str(result.second_manifest_hash),
            "first_counts": result.first_counts,
            "second_counts": result.second_counts,
            "posting_first": result.posting_first,
            "posting_second": result.posting_second,
            "go_live_passed": bool(result.go_live_passed),
        }
        secret = str(os.getenv("PHASE7_EVIDENCE_SECRET", "")).strip()
        signed_payload = build_phase7_evidence(payload=payload, secret=secret)
        raw = json.dumps(signed_payload, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase7 certification exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(result.passed):
            raise CommandError("phase7 certification failed.")
