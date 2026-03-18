from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.certification_phase11 import build_phase11_evidence, collect_phase11_operational_health
from apps.accounting.phase7b import enforce_intercompany_sla, run_intercompany_cycle
from apps.integration.services import dispatch_outbox_events


class Command(BaseCommand):
    help = "Ciclo operativo Fase 11 (intercompany + SLA + outbox dispatch)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--dispatch-limit", type=int, default=200)
        parser.add_argument("--open-sla-hours", type=int, default=24)
        parser.add_argument("--dispute-sla-hours", type=int, default=24)
        parser.add_argument("--max-open-intercompany", type=int, default=0)
        parser.add_argument("--max-disputed-intercompany", type=int, default=0)
        parser.add_argument("--max-open-outside-sla", type=int, default=0)
        parser.add_argument("--max-disputed-outside-sla", type=int, default=0)
        parser.add_argument("--max-stale-confirmed-unclosed", type=int, default=0)
        parser.add_argument("--max-open-blocking-exceptions", type=int, default=0)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        output = str(options.get("output") or "").strip()

        dispatch_before = dispatch_outbox_events(limit=int(options.get("dispatch_limit") or 200))
        cycle = run_intercompany_cycle(
            company_id=company_id,
            limit=int(options.get("limit") or 200),
            strict=False,
            actor_user=None,
        )
        sla_result = enforce_intercompany_sla(
            company_id=company_id,
            open_sla_hours=int(options.get("open_sla_hours") or 24),
            dispute_sla_hours=int(options.get("dispute_sla_hours") or 24),
            actor_user=None,
        )
        dispatch_after = dispatch_outbox_events(limit=int(options.get("dispatch_limit") or 200), source_module="ACCOUNTING")

        health = collect_phase11_operational_health(
            company_id=company_id,
            consumer=consumer,
            open_sla_hours=int(options.get("open_sla_hours") or 24),
            dispute_sla_hours=int(options.get("dispute_sla_hours") or 24),
        )
        checks = [
            {
                "name": "open_intercompany_within_threshold",
                "passed": int(health.get("open_intercompany_count") or 0) <= int(options.get("max_open_intercompany") or 0),
                "detail": {
                    "count": int(health.get("open_intercompany_count") or 0),
                    "max_allowed": int(options.get("max_open_intercompany") or 0),
                },
            },
            {
                "name": "disputed_intercompany_within_threshold",
                "passed": int(health.get("disputed_intercompany_count") or 0)
                <= int(options.get("max_disputed_intercompany") or 0),
                "detail": {
                    "count": int(health.get("disputed_intercompany_count") or 0),
                    "max_allowed": int(options.get("max_disputed_intercompany") or 0),
                },
            },
            {
                "name": "open_outside_sla_within_threshold",
                "passed": int(health.get("open_outside_sla_count") or 0) <= int(options.get("max_open_outside_sla") or 0),
                "detail": {
                    "count": int(health.get("open_outside_sla_count") or 0),
                    "max_allowed": int(options.get("max_open_outside_sla") or 0),
                },
            },
            {
                "name": "disputed_outside_sla_within_threshold",
                "passed": int(health.get("disputed_outside_sla_count") or 0)
                <= int(options.get("max_disputed_outside_sla") or 0),
                "detail": {
                    "count": int(health.get("disputed_outside_sla_count") or 0),
                    "max_allowed": int(options.get("max_disputed_outside_sla") or 0),
                },
            },
            {
                "name": "stale_confirmed_unclosed_within_threshold",
                "passed": int(health.get("stale_confirmed_unclosed_count") or 0)
                <= int(options.get("max_stale_confirmed_unclosed") or 0),
                "detail": {
                    "count": int(health.get("stale_confirmed_unclosed_count") or 0),
                    "max_allowed": int(options.get("max_stale_confirmed_unclosed") or 0),
                },
            },
            {
                "name": "open_blocking_exceptions_within_threshold",
                "passed": int(health.get("open_intercompany_blocking_exception_count") or 0)
                <= int(options.get("max_open_blocking_exceptions") or 0),
                "detail": {
                    "count": int(health.get("open_intercompany_blocking_exception_count") or 0),
                    "max_allowed": int(options.get("max_open_blocking_exceptions") or 0),
                },
            },
            {
                "name": "inbox_failed_within_threshold",
                "passed": int(health.get("inbox_failed_count") or 0) <= int(options.get("max_inbox_failed") or 0),
                "detail": {
                    "count": int(health.get("inbox_failed_count") or 0),
                    "max_allowed": int(options.get("max_inbox_failed") or 0),
                },
            },
            {
                "name": "outbox_failed_within_threshold",
                "passed": int(health.get("outbox_failed_count") or 0) <= int(options.get("max_outbox_failed") or 0),
                "detail": {
                    "count": int(health.get("outbox_failed_count") or 0),
                    "max_allowed": int(options.get("max_outbox_failed") or 0),
                },
            },
        ]
        cycle_passed = all(bool(item["passed"]) for item in checks)

        report: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"company_id": int(company_id)},
            "consumer": consumer,
            "cycle_passed": bool(cycle_passed),
            "dispatch_before": {
                "attempted": int(dispatch_before.attempted),
                "sent": int(dispatch_before.sent),
                "retried": int(dispatch_before.retried),
                "failed": int(dispatch_before.failed),
            },
            "cycle": {
                "processed": int(cycle.processed),
                "confirmed": int(cycle.confirmed),
                "differences": int(cycle.differences),
                "disputed": int(cycle.disputed),
                "closed": int(cycle.closed),
                "open_items": int(cycle.open_items),
                "report_hash": str(cycle.report_hash),
            },
            "sla": {
                "escalated": int(sla_result.get("escalated") or 0),
                "resolved": int(sla_result.get("resolved") or 0),
                "open_sla_hours": int(options.get("open_sla_hours") or 24),
                "dispute_sla_hours": int(options.get("dispute_sla_hours") or 24),
            },
            "dispatch_after": {
                "attempted": int(dispatch_after.attempted),
                "sent": int(dispatch_after.sent),
                "retried": int(dispatch_after.retried),
                "failed": int(dispatch_after.failed),
            },
            "health": health,
            "checks": checks,
        }

        secret = str(os.getenv("PHASE11_EVIDENCE_SECRET", os.getenv("PHASE7B_EVIDENCE_SECRET", ""))).strip()
        signed = build_phase11_evidence(payload=report, secret=secret)
        raw = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase11 intercompany cycle report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not cycle_passed:
            raise CommandError("phase11 intercompany cycle gate failed.")
