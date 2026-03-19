from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.certification_phase11 import (
    build_phase11_evidence,
    certify_phase11_intercompany_sla,
)


class Command(BaseCommand):
    help = "Certifica Fase 11 (intercompany dispute/settlement + SLA + determinismo)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--target-company-id", type=int, default=None)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--open-sla-hours", type=int, default=24)
        parser.add_argument("--dispute-sla-hours", type=int, default=24)
        parser.add_argument("--expect-blocked", action="store_true", default=False)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        target_company_id = options.get("target_company_id")
        output = str(options.get("output") or "").strip()

        try:
            result = certify_phase11_intercompany_sla(
                company_id=company_id,
                target_company_id=int(target_company_id) if target_company_id is not None else None,
                consumer=str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector",
                open_sla_hours=int(options.get("open_sla_hours") or 24),
                dispute_sla_hours=int(options.get("dispute_sla_hours") or 24),
                expect_blocked=bool(options.get("expect_blocked", False)),
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": result.pilot_scope,
            "passed": bool(result.passed),
            "go_live_passed": bool(result.go_live_passed),
            "blocked": bool(result.blocked),
            "expect_blocked": bool(options.get("expect_blocked", False)),
            "deterministic_replay": bool(result.deterministic_replay),
            "tx_id": result.tx_id,
            "create_status": result.create_status,
            "dispute_status": result.dispute_status,
            "settle_status": result.settle_status,
            "first_cycle_hash": result.first_cycle_hash,
            "second_cycle_hash": result.second_cycle_hash,
            "third_cycle_hash": result.third_cycle_hash,
            "first_cycle_open_items": int(result.first_cycle_open_items),
            "second_cycle_open_items": int(result.second_cycle_open_items),
            "third_cycle_open_items": int(result.third_cycle_open_items),
            "tx_open_blocking_exception_count": int(result.tx_open_blocking_exception_count),
            "health": result.health,
        }
        secret = str(os.getenv("PHASE11_EVIDENCE_SECRET", os.getenv("PHASE7B_EVIDENCE_SECRET", ""))).strip()
        evidence = build_phase11_evidence(payload=payload, secret=secret)
        raw = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase11 intercompany certification exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(result.passed):
            raise CommandError("phase11 intercompany certification failed.")
