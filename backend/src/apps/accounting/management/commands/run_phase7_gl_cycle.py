from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.certification_phase7 import build_phase7_evidence, collect_phase7_operational_health
from apps.accounting.phase7 import run_fx_revaluation
from apps.accounting.services import post_journal_drafts
from apps.integration.services import dispatch_outbox_events


class Command(BaseCommand):
    help = "Ciclo operativo Fase 7A (posting + revaluación + dispatch + health gates)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--run-id", type=str, default="")
        parser.add_argument("--year", type=int, default=None)
        parser.add_argument("--month", type=int, default=None)
        parser.add_argument("--posting-limit", type=int, default=500)
        parser.add_argument("--dispatch-limit", type=int, default=200)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-unbalanced-entries", type=int, default=0)
        parser.add_argument("--max-missing-lines", type=int, default=0)
        parser.add_argument("--max-stale-revaluation", type=int, default=0)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        run_id = str(options.get("run_id") or "").strip()
        posting_limit = int(options.get("posting_limit") or 500)
        dispatch_limit = int(options.get("dispatch_limit") or 200)
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        output = str(options.get("output") or "").strip()

        today = timezone.localdate()
        year = int(options.get("year") or today.year)
        month = int(options.get("month") or today.month)

        dispatch_before = dispatch_outbox_events(limit=dispatch_limit)
        posting = post_journal_drafts(
            company_id=company_id,
            run_id=run_id,
            limit=posting_limit,
            require_approved=False,
            auto_approve=False,
        )
        try:
            revaluation = run_fx_revaluation(
                company_id=company_id,
                year=year,
                month=month,
                strict=True,
            )
        except Exception as exc:  # noqa: BLE001
            revaluation = None
            revaluation_error = str(exc)
        else:
            revaluation_error = ""

        dispatch_after = dispatch_outbox_events(limit=dispatch_limit, source_module="ACCOUNTING")
        health = collect_phase7_operational_health(company_id=company_id, consumer=consumer)
        checks = [
            {
                "name": "inbox_failed_within_threshold",
                "passed": int(health["inbox_failed_count"]) <= int(options.get("max_inbox_failed") or 0),
                "detail": {"count": int(health["inbox_failed_count"]), "max_allowed": int(options.get("max_inbox_failed") or 0)},
            },
            {
                "name": "outbox_failed_within_threshold",
                "passed": int(health["outbox_failed_count"]) <= int(options.get("max_outbox_failed") or 0),
                "detail": {"count": int(health["outbox_failed_count"]), "max_allowed": int(options.get("max_outbox_failed") or 0)},
            },
            {
                "name": "unbalanced_entries_within_threshold",
                "passed": int(health["unbalanced_entries_count"]) <= int(options.get("max_unbalanced_entries") or 0),
                "detail": {
                    "count": int(health["unbalanced_entries_count"]),
                    "max_allowed": int(options.get("max_unbalanced_entries") or 0),
                },
            },
            {
                "name": "missing_lines_within_threshold",
                "passed": int(health["missing_lines_count"]) <= int(options.get("max_missing_lines") or 0),
                "detail": {"count": int(health["missing_lines_count"]), "max_allowed": int(options.get("max_missing_lines") or 0)},
            },
            {
                "name": "stale_revaluation_within_threshold",
                "passed": int(health["stale_revaluation_count"]) <= int(options.get("max_stale_revaluation") or 0),
                "detail": {
                    "count": int(health["stale_revaluation_count"]),
                    "max_allowed": int(options.get("max_stale_revaluation") or 0),
                },
            },
            {
                "name": "revaluation_not_blocked",
                "passed": bool(revaluation is not None and str(revaluation.status) != "BLOCKED" and not revaluation_error),
                "detail": {
                    "status": str(revaluation.status) if revaluation is not None else "FAILED",
                    "error": revaluation_error,
                },
            },
            {
                "name": "posting_without_failures",
                "passed": int(posting.failed) == 0,
                "detail": {"failed": int(posting.failed)},
            },
        ]
        cycle_passed = all(bool(x["passed"]) for x in checks)
        report: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {"company_id": company_id},
            "cycle_passed": bool(cycle_passed),
            "run_id": run_id,
            "period": {"year": year, "month": month},
            "dispatch_before": {
                "attempted": int(dispatch_before.attempted),
                "sent": int(dispatch_before.sent),
                "retried": int(dispatch_before.retried),
                "failed": int(dispatch_before.failed),
            },
            "posting": {
                "attempted": int(posting.attempted),
                "approved": int(posting.approved),
                "posted": int(posting.posted),
                "skipped": int(posting.skipped),
                "failed": int(posting.failed),
                "errors": posting.errors,
            },
            "revaluation": (
                {
                    "run_id": str(revaluation.run_id),
                    "status": str(revaluation.status),
                    "idempotent": bool(revaluation.idempotent),
                    "entries_created": int(revaluation.entries_created),
                    "issues_count": int(revaluation.issues_count),
                }
                if revaluation is not None
                else {"run_id": "", "status": "FAILED", "error": revaluation_error}
            ),
            "dispatch_after": {
                "attempted": int(dispatch_after.attempted),
                "sent": int(dispatch_after.sent),
                "retried": int(dispatch_after.retried),
                "failed": int(dispatch_after.failed),
            },
            "health": health,
            "checks": checks,
        }
        secret = str(os.getenv("PHASE7_EVIDENCE_SECRET", "")).strip()
        signed_report = build_phase7_evidence(payload=report, secret=secret)
        raw = json.dumps(signed_report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase7 cycle report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not cycle_passed:
            raise CommandError("phase7 cycle gate failed.")
