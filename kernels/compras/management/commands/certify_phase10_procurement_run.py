from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from kernels.compras.certification_phase10 import (
    build_phase10_evidence,
    certify_phase10_procurement_run,
    collect_phase10_env_manifest,
)


class Command(BaseCommand):
    help = "Certificación Fase 10 para procurement (proyección + posting + determinismo)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--expect-blocked", action="store_true", default=False)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        expect_blocked = bool(options.get("expect_blocked", False))
        output = str(options.get("output") or "").strip()

        try:
            result = certify_phase10_procurement_run(
                company_id=company_id,
                branch_id=branch_id,
                expect_blocked=expect_blocked,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": result.pilot_scope,
            "run_id": result.run_id,
            "expect_blocked": bool(expect_blocked),
            "passed": bool(result.passed),
            "blocked": bool(result.blocked),
            "deterministic_replay": bool(result.deterministic_replay),
            "close_run_status": result.close_run_status,
            "first_manifest_hash": result.first_manifest_hash,
            "second_manifest_hash": result.second_manifest_hash,
            "manifest_hash": result.second_manifest_hash,
            "doc_type": result.doc_type,
            "first_counts": result.first_counts,
            "second_counts": result.second_counts,
            "posting_first": result.posting_first,
            "posting_second": result.posting_second,
            "projection_first": result.projection_first,
            "projection_second": result.projection_second,
            "go_live_passed": bool(result.go_live_passed),
            "env_manifest": collect_phase10_env_manifest(company_id=company_id, branch_id=branch_id),
        }

        secret = str(os.getenv("PHASE10_EVIDENCE_SECRET", "")).strip()
        evidence = build_phase10_evidence(payload=payload, secret=secret)
        raw = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase10 procurement evidence exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(result.passed):
            raise CommandError("phase10 procurement certification failed.")

