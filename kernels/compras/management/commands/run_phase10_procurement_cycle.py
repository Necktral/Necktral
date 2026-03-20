from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.accounting.services import post_journal_drafts, project_pending_shadow_ledger_triggers
from apps.modulos.integration.services import dispatch_outbox_events
from kernels.compras.certification_phase10 import build_phase10_evidence, collect_phase10_operational_health


class Command(BaseCommand):
    help = "Ciclo operativo Fase 10 (procurement -> projection -> posting -> health gate)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--projection-limit", type=int, default=200)
        parser.add_argument("--posting-limit", type=int, default=500)
        parser.add_argument("--dispatch-limit", type=int, default=200)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-open-procurement-drafts", type=int, default=0)
        parser.add_argument("--max-open-procurement-blocking-exceptions", type=int, default=0)
        parser.add_argument("--max-posting-failed", type=int, default=0)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        output = str(options.get("output") or "").strip()

        dispatch_before = dispatch_outbox_events(limit=int(options.get("dispatch_limit") or 200))
        projection = project_pending_shadow_ledger_triggers(
            limit=int(options.get("projection_limit") or 200),
            company_id=company_id,
        )
        posting = post_journal_drafts(
            company_id=company_id,
            run_id="",
            limit=int(options.get("posting_limit") or 500),
            require_approved=False,
            auto_approve=False,
        )
        dispatch_after = dispatch_outbox_events(limit=int(options.get("dispatch_limit") or 200), source_module="ACCOUNTING")

        health = collect_phase10_operational_health(company_id=company_id, branch_id=branch_id, consumer=consumer)
        checks = [
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
            {
                "name": "open_procurement_drafts_within_threshold",
                "passed": int(health.get("open_procurement_drafts_count") or 0)
                <= int(options.get("max_open_procurement_drafts") or 0),
                "detail": {
                    "count": int(health.get("open_procurement_drafts_count") or 0),
                    "max_allowed": int(options.get("max_open_procurement_drafts") or 0),
                },
            },
            {
                "name": "open_procurement_blocking_exceptions_within_threshold",
                "passed": int(health.get("open_procurement_blocking_exceptions_count") or 0)
                <= int(options.get("max_open_procurement_blocking_exceptions") or 0),
                "detail": {
                    "count": int(health.get("open_procurement_blocking_exceptions_count") or 0),
                    "max_allowed": int(options.get("max_open_procurement_blocking_exceptions") or 0),
                },
            },
            {
                "name": "posting_failed_within_threshold",
                "passed": int(posting.failed) <= int(options.get("max_posting_failed") or 0),
                "detail": {
                    "count": int(posting.failed),
                    "max_allowed": int(options.get("max_posting_failed") or 0),
                },
            },
        ]
        cycle_passed = all(bool(item["passed"]) for item in checks)

        report: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"company_id": company_id, "branch_id": branch_id},
            "consumer": consumer,
            "cycle_passed": bool(cycle_passed),
            "dispatch_before": {
                "attempted": int(dispatch_before.attempted),
                "sent": int(dispatch_before.sent),
                "retried": int(dispatch_before.retried),
                "failed": int(dispatch_before.failed),
            },
            "projection": {
                "attempted": int(projection.attempted),
                "processed": int(projection.processed),
                "blocked": int(projection.blocked),
                "skipped": int(projection.skipped),
                "failed": int(projection.failed),
            },
            "posting": {
                "attempted": int(posting.attempted),
                "approved": int(posting.approved),
                "posted": int(posting.posted),
                "skipped": int(posting.skipped),
                "failed": int(posting.failed),
                "errors": posting.errors,
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

        secret = str(os.getenv("PHASE10_EVIDENCE_SECRET", "")).strip()
        signed = build_phase10_evidence(payload=report, secret=secret)
        raw = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase10 procurement cycle report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not cycle_passed:
            raise CommandError("phase10 procurement cycle gate failed.")

