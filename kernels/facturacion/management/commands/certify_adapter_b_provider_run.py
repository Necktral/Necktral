from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from kernels.facturacion.certification_phase9 import (
    build_phase9_evidence,
    certify_adapter_b_provider_run,
    collect_phase9_env_manifest,
)


class Command(BaseCommand):
    help = "Certifica corrida Fase 9 para Adapter B provider real/emulado."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--expect-blocked", action="store_true", default=False)
        parser.add_argument(
            "--blocked-adapter-code",
            type=str,
            default="EMULATED_B",
            help="Adapter code usado solo para escenario blocked (default: EMULATED_B).",
        )
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        expect_blocked = bool(options.get("expect_blocked", False))
        blocked_adapter_code = str(options.get("blocked_adapter_code") or "EMULATED_B").strip().upper()
        output = str(options.get("output") or "").strip()

        try:
            result = certify_adapter_b_provider_run(
                company_id=company_id,
                branch_id=branch_id,
                expect_blocked=expect_blocked,
                blocked_adapter_code=blocked_adapter_code,
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
            "first_counts": result.first_counts,
            "second_counts": result.second_counts,
            "job_counts": result.job_counts,
            "contingency_counts": result.contingency_counts,
            "cec_blocking_exceptions": int(result.cec_blocking_exceptions),
            "provider_mode": result.provider_mode,
            "provider_adapter_class": result.provider_adapter_class,
            "provider_check_ok": bool(result.provider_check_ok),
            "provider_check_error": result.provider_check_error,
            "scenario_adapter_code": result.scenario_adapter_code,
            "blocked_path_mode": result.blocked_path_mode,
            "go_live_passed": bool(result.go_live_passed),
            "env_manifest": collect_phase9_env_manifest(company_id=company_id, branch_id=branch_id),
        }
        secret = str(os.getenv("PHASE9_EVIDENCE_SECRET", os.getenv("PHASE6_EVIDENCE_SECRET", ""))).strip()
        evidence = build_phase9_evidence(payload=payload, secret=secret)
        raw = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase9 run evidence exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(result.passed):
            raise CommandError("phase9 certification failed.")

