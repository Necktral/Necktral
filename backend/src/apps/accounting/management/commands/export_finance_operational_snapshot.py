from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounting.staging_ops import build_staging_ops_evidence, collect_finance_operational_snapshot


class Command(BaseCommand):
    help = "Exporta snapshot operacional de backend (F6/F7A/F7B) para dashboard y alertas."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--stale-minutes", type=int, default=30)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-missing-lines", type=int, default=0)
        parser.add_argument("--max-stale-revaluation", type=int, default=0)
        parser.add_argument("--max-open-intercompany", type=int, default=0)
        parser.add_argument("--max-disputed", type=int, default=0)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        output = str(options.get("output") or "").strip()

        try:
            payload = collect_finance_operational_snapshot(
                company_id=company_id,
                branch_id=branch_id,
                consumer=consumer,
                stale_minutes=int(options.get("stale_minutes") or 30),
                inbox_failed=int(options.get("max_inbox_failed") or 0),
                outbox_failed=int(options.get("max_outbox_failed") or 0),
                missing_lines=int(options.get("max_missing_lines") or 0),
                stale_revaluation=int(options.get("max_stale_revaluation") or 0),
                open_intercompany=int(options.get("max_open_intercompany") or 0),
                disputed=int(options.get("max_disputed") or 0),
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        secret = str(
            os.getenv("STAGING_EXECUTION_EVIDENCE_SECRET")
            or os.getenv("PHASE7B_EVIDENCE_SECRET")
            or ""
        ).strip()
        signed_payload = build_staging_ops_evidence(payload=payload, secret=secret)
        raw = json.dumps(signed_payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"finance operational snapshot exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(payload.get("snapshot_passed")):
            raise CommandError("finance operational snapshot gate failed.")
