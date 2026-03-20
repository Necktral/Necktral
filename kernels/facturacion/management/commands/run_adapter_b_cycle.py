from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.modulos.integration.services import dispatch_outbox_events
from kernels.facturacion.certification import build_phase6_evidence, collect_phase6_operational_health
from kernels.facturacion.services import process_fiscal_print_jobs


class Command(BaseCommand):
    help = "Ejecuta ciclo operativo Adapter B (print queue + outbox dispatch + health gate)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--print-limit", type=int, default=100)
        parser.add_argument("--dispatch-limit", type=int, default=200)
        parser.add_argument("--stale-minutes", type=int, default=30)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-failed-jobs", type=int, default=0)
        parser.add_argument("--max-retry-overdue", type=int, default=0)
        parser.add_argument("--max-stale-pending", type=int, default=0)
        parser.add_argument("--max-open-contingency", type=int, default=0)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        print_limit = int(options.get("print_limit") or 100)
        dispatch_limit = int(options.get("dispatch_limit") or 200)
        stale_minutes = int(options.get("stale_minutes") or 30)
        max_inbox_failed = int(options.get("max_inbox_failed") or 0)
        max_outbox_failed = int(options.get("max_outbox_failed") or 0)
        max_failed_jobs = int(options.get("max_failed_jobs") or 0)
        max_retry_overdue = int(options.get("max_retry_overdue") or 0)
        max_stale_pending = int(options.get("max_stale_pending") or 0)
        max_open_contingency = int(options.get("max_open_contingency") or 0)
        output = str(options.get("output") or "").strip()

        now = timezone.now()
        dispatch_before = dispatch_outbox_events(limit=dispatch_limit, now=now)
        print_summary = process_fiscal_print_jobs(
            limit=print_limit,
            now=now,
            company_id=company_id,
            branch_id=branch_id,
        )
        dispatch_after = dispatch_outbox_events(limit=dispatch_limit, now=timezone.now(), source_module="BILLING")

        health = collect_phase6_operational_health(
            company_id=company_id,
            branch_id=branch_id,
            consumer=consumer,
            stale_minutes=stale_minutes,
        )
        checks = [
            {
                "name": "inbox_failed_within_threshold",
                "passed": health["inbox_failed_count"] <= max_inbox_failed,
                "detail": {
                    "consumer": consumer,
                    "failed_count": int(health["inbox_failed_count"]),
                    "max_allowed": int(max_inbox_failed),
                },
            },
            {
                "name": "outbox_failed_within_threshold",
                "passed": health["outbox_failed_count"] <= max_outbox_failed,
                "detail": {
                    "failed_count": int(health["outbox_failed_count"]),
                    "max_allowed": int(max_outbox_failed),
                },
            },
            {
                "name": "failed_jobs_within_threshold",
                "passed": health["failed_jobs_count"] <= max_failed_jobs,
                "detail": {
                    "failed_jobs_count": int(health["failed_jobs_count"]),
                    "max_allowed": int(max_failed_jobs),
                },
            },
            {
                "name": "retry_overdue_within_threshold",
                "passed": health["retry_overdue_count"] <= max_retry_overdue,
                "detail": {
                    "retry_overdue_count": int(health["retry_overdue_count"]),
                    "max_allowed": int(max_retry_overdue),
                },
            },
            {
                "name": "stale_pending_within_threshold",
                "passed": health["stale_pending_count"] <= max_stale_pending,
                "detail": {
                    "stale_pending_count": int(health["stale_pending_count"]),
                    "max_allowed": int(max_stale_pending),
                },
            },
            {
                "name": "open_contingency_within_threshold",
                "passed": health["contingency_open_count"] <= max_open_contingency,
                "detail": {
                    "contingency_open_count": int(health["contingency_open_count"]),
                    "max_allowed": int(max_open_contingency),
                },
            },
        ]
        cycle_passed = all(bool(row["passed"]) for row in checks)

        report: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"company_id": int(company_id), "branch_id": int(branch_id)},
            "consumer": consumer,
            "cycle_passed": bool(cycle_passed),
            "dispatch_before": {
                "attempted": int(dispatch_before.attempted),
                "sent": int(dispatch_before.sent),
                "retried": int(dispatch_before.retried),
                "failed": int(dispatch_before.failed),
            },
            "print_processing": {
                "attempted": int(print_summary.attempted),
                "printed": int(print_summary.printed),
                "retried": int(print_summary.retried),
                "failed": int(print_summary.failed),
                "contingency": int(print_summary.contingency),
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
        secret = str(os.getenv("PHASE6_EVIDENCE_SECRET", "")).strip()
        signed_report = build_phase6_evidence(payload=report, secret=secret)
        raw = json.dumps(signed_report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"adapter b cycle report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not cycle_passed:
            raise CommandError("adapter b cycle gate failed.")
