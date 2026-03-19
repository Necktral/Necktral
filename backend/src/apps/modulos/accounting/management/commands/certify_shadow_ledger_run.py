from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.certification import (
    build_phase4_evidence,
    certify_shadow_ledger_run,
    collect_phase4_env_manifest,
)


class Command(BaseCommand):
    help = "Certifica corrida real Fase 4A por run_id (determinismo, idempotencia y gate contable)."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=str, required=True)
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--expect-blocked", action="store_true", default=False)
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args, **options):
        run_id = str(options["run_id"]).strip()
        company_id = options.get("company_id")
        expect_blocked = bool(options.get("expect_blocked", False))
        output = str(options.get("output") or "").strip()

        try:
            result = certify_shadow_ledger_run(
                run_id=run_id,
                company_id=company_id,
                expect_blocked=expect_blocked,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "run_id": result.run_id,
            "expect_blocked": bool(expect_blocked),
            "passed": bool(result.passed),
            "blocked": bool(result.blocked),
            "replay_performed": bool(result.replay_performed),
            "deterministic_replay": bool(result.deterministic_replay),
            "close_run_status": result.close_run_status,
            "first_manifest_hash": result.first_manifest_hash,
            "second_manifest_hash": result.second_manifest_hash,
            "first_counts": result.first_counts,
            "second_counts": result.second_counts,
            "env_manifest": collect_phase4_env_manifest(company_id=company_id),
        }
        secret = str(os.getenv("PHASE4_EVIDENCE_SECRET", "")).strip()
        evidence = build_phase4_evidence(payload=payload, secret=secret)
        raw = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase4 run evidence exported: {path}"))
        else:
            self.stdout.write(raw)

        if not result.passed:
            raise CommandError("Certificación real Fase 4A fallida.")
