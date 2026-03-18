from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounting.certification_phase12 import build_phase12_evidence, run_phase12_monthly_close


class Command(BaseCommand):
    help = "Ejecuta ciclo mensual continuo Fase 12 (backend-only)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--parent-company-id", type=int, required=True)
        parser.add_argument("--company-ids", type=int, nargs="+", required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--posting-limit", type=int, default=500)
        parser.add_argument("--intercompany-limit", type=int, default=200)
        parser.add_argument("--dispatch-limit", type=int, default=200)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-missing-lines", type=int, default=0)
        parser.add_argument("--max-stale-revaluation", type=int, default=0)
        parser.add_argument("--max-open-intercompany", type=int, default=0)
        parser.add_argument("--max-disputed-intercompany", type=int, default=0)
        parser.add_argument("--max-blocked-consolidation", type=int, default=0)
        parser.add_argument("--max-open-consolidation-exception", type=int, default=0)
        parser.add_argument("--fx-blocked-policy", type=str, default="ALERT")
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        output = str(options.get("output") or "").strip()

        try:
            result = run_phase12_monthly_close(
                company_id=int(options["company_id"]),
                parent_company_id=int(options["parent_company_id"]),
                company_ids=[int(x) for x in (options.get("company_ids") or [])],
                year=int(options["year"]),
                month=int(options["month"]),
                consumer=str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector",
                posting_limit=int(options.get("posting_limit") or 500),
                intercompany_limit=int(options.get("intercompany_limit") or 200),
                dispatch_limit=int(options.get("dispatch_limit") or 200),
                max_inbox_failed=int(options.get("max_inbox_failed") or 0),
                max_outbox_failed=int(options.get("max_outbox_failed") or 0),
                max_missing_lines=int(options.get("max_missing_lines") or 0),
                max_stale_revaluation=int(options.get("max_stale_revaluation") or 0),
                max_open_intercompany=int(options.get("max_open_intercompany") or 0),
                max_disputed_intercompany=int(options.get("max_disputed_intercompany") or 0),
                max_blocked_consolidation=int(options.get("max_blocked_consolidation") or 0),
                max_open_consolidation_exception=int(options.get("max_open_consolidation_exception") or 0),
                fx_blocked_policy=str(options.get("fx_blocked_policy") or "ALERT"),
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = dict(result.report)
        payload["go_live_passed"] = bool(result.cycle_passed)
        secret = str(os.getenv("PHASE12_EVIDENCE_SECRET", "")).strip()
        evidence = build_phase12_evidence(payload=payload, secret=secret)
        raw = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase12 monthly close report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not bool(result.cycle_passed):
            raise CommandError("phase12 monthly close gate failed.")
