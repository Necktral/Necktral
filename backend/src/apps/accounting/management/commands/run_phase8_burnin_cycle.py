from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.phase7 import run_fx_revaluation
from apps.accounting.phase7b import Phase7BValidationError, run_consolidation, run_intercompany_cycle
from apps.accounting.phase8 import build_phase8_evidence, collect_phase8_operational_health
from apps.accounting.services import post_journal_drafts
from apps.integration.services import dispatch_outbox_events
from modulos.facturacion.services import process_fiscal_print_jobs


class Command(BaseCommand):
    help = "Ejecuta ciclo de burn-in F8 (F6+F7A+F7B) para operación diaria en producción." 

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--branch-id", type=int, required=True)
        parser.add_argument("--parent-company-id", type=int, required=True)
        parser.add_argument("--company-ids", type=int, nargs="+", required=True)
        parser.add_argument("--year", type=int, default=None)
        parser.add_argument("--month", type=int, default=None)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--print-limit", type=int, default=100)
        parser.add_argument("--dispatch-limit", type=int, default=200)
        parser.add_argument("--posting-limit", type=int, default=500)
        parser.add_argument("--intercompany-limit", type=int, default=200)
        parser.add_argument("--stale-minutes", type=int, default=30)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-missing-lines", type=int, default=0)
        parser.add_argument("--max-stale-revaluation", type=int, default=0)
        parser.add_argument("--max-open-intercompany", type=int, default=0)
        parser.add_argument("--max-disputed-intercompany", type=int, default=0)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = int(options["company_id"])
        branch_id = int(options["branch_id"])
        parent_company_id = int(options["parent_company_id"])
        company_ids = [int(x) for x in (options.get("company_ids") or [])]
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        output = str(options.get("output") or "").strip()

        today = timezone.localdate()
        year = int(options.get("year") or today.year)
        month = int(options.get("month") or today.month)

        dispatch_before = dispatch_outbox_events(limit=int(options.get("dispatch_limit") or 200))
        print_summary = process_fiscal_print_jobs(
            limit=int(options.get("print_limit") or 100),
            now=timezone.now(),
            company_id=company_id,
            branch_id=branch_id,
        )
        posting = post_journal_drafts(
            company_id=company_id,
            run_id="",
            limit=int(options.get("posting_limit") or 500),
            require_approved=False,
            auto_approve=False,
        )
        try:
            revaluation = run_fx_revaluation(
                company_id=company_id,
                year=year,
                month=month,
                strict=False,
            )
            revaluation_error = ""
        except Exception as exc:  # noqa: BLE001
            revaluation = None
            revaluation_error = str(exc)

        intercompany_reports: list[dict[str, Any]] = []
        intercompany_errors: list[str] = []
        for cid in sorted({company_id, *company_ids}):
            try:
                cycle = run_intercompany_cycle(
                    company_id=int(cid),
                    limit=int(options.get("intercompany_limit") or 200),
                    strict=False,
                )
                intercompany_reports.append(
                    {
                        "company_id": int(cid),
                        "processed": int(cycle.processed),
                        "confirmed": int(cycle.confirmed),
                        "differences": int(cycle.differences),
                        "disputed": int(cycle.disputed),
                        "closed": int(cycle.closed),
                        "open_items": int(cycle.open_items),
                        "report_hash": cycle.report_hash,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                intercompany_errors.append(f"company={cid}:{exc}")

        try:
            consolidation = run_consolidation(
                parent_company_id=parent_company_id,
                year=year,
                month=month,
                company_ids=company_ids,
                strict=False,
                actor_user=None,
            )
            consolidation_error = ""
        except Phase7BValidationError as exc:
            consolidation = None
            consolidation_error = str(exc)

        dispatch_after = dispatch_outbox_events(limit=int(options.get("dispatch_limit") or 200), source_module="ACCOUNTING")

        health = collect_phase8_operational_health(
            company_id=company_id,
            branch_id=branch_id,
            parent_company_id=parent_company_id,
            consumer=consumer,
            stale_minutes=int(options.get("stale_minutes") or 30),
        )
        phase6 = dict(health.get("phase6") or {})
        phase7a = dict(health.get("phase7a") or {})
        phase7b = dict(health.get("phase7b") or {})

        checks = [
            {
                "name": "inbox_failed_within_threshold",
                "passed": max(
                    int(phase6.get("inbox_failed_count") or 0),
                    int(phase7a.get("inbox_failed_count") or 0),
                    int(phase7b.get("inbox_failed_count") or 0),
                ) <= int(options.get("max_inbox_failed") or 0),
                "detail": {
                    "phase6": int(phase6.get("inbox_failed_count") or 0),
                    "phase7a": int(phase7a.get("inbox_failed_count") or 0),
                    "phase7b": int(phase7b.get("inbox_failed_count") or 0),
                    "max_allowed": int(options.get("max_inbox_failed") or 0),
                },
            },
            {
                "name": "outbox_failed_within_threshold",
                "passed": max(
                    int(phase6.get("outbox_failed_count") or 0),
                    int(phase7a.get("outbox_failed_count") or 0),
                    int(phase7b.get("outbox_failed_count") or 0),
                ) <= int(options.get("max_outbox_failed") or 0),
                "detail": {
                    "phase6": int(phase6.get("outbox_failed_count") or 0),
                    "phase7a": int(phase7a.get("outbox_failed_count") or 0),
                    "phase7b": int(phase7b.get("outbox_failed_count") or 0),
                    "max_allowed": int(options.get("max_outbox_failed") or 0),
                },
            },
            {
                "name": "missing_lines_within_threshold",
                "passed": int(phase7a.get("missing_lines_count") or 0) <= int(options.get("max_missing_lines") or 0),
                "detail": {
                    "count": int(phase7a.get("missing_lines_count") or 0),
                    "max_allowed": int(options.get("max_missing_lines") or 0),
                },
            },
            {
                "name": "stale_revaluation_within_threshold",
                "passed": int(phase7a.get("stale_revaluation_count") or 0)
                <= int(options.get("max_stale_revaluation") or 0),
                "detail": {
                    "count": int(phase7a.get("stale_revaluation_count") or 0),
                    "max_allowed": int(options.get("max_stale_revaluation") or 0),
                },
            },
            {
                "name": "open_intercompany_within_threshold",
                "passed": int(phase7b.get("open_intercompany_count") or 0)
                <= int(options.get("max_open_intercompany") or 0),
                "detail": {
                    "count": int(phase7b.get("open_intercompany_count") or 0),
                    "max_allowed": int(options.get("max_open_intercompany") or 0),
                },
            },
            {
                "name": "disputed_intercompany_within_threshold",
                "passed": int(phase7b.get("disputed_intercompany_count") or 0)
                <= int(options.get("max_disputed_intercompany") or 0),
                "detail": {
                    "count": int(phase7b.get("disputed_intercompany_count") or 0),
                    "max_allowed": int(options.get("max_disputed_intercompany") or 0),
                },
            },
            {
                "name": "intercompany_cycle_errors_empty",
                "passed": len(intercompany_errors) == 0,
                "detail": {"errors": intercompany_errors},
            },
            {
                "name": "consolidation_not_failed",
                "passed": consolidation_error == "",
                "detail": {"error": consolidation_error, "status": str(consolidation.status) if consolidation else "FAILED"},
            },
            {
                "name": "posting_without_failures",
                "passed": int(posting.failed) == 0,
                "detail": {"failed": int(posting.failed)},
            },
        ]
        cycle_passed = all(bool(item["passed"]) for item in checks)

        payload = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "pilot_scope": {
                "company_id": company_id,
                "branch_id": branch_id,
                "parent_company_id": parent_company_id,
                "company_ids": sorted({int(x) for x in company_ids}),
            },
            "period": {"year": year, "month": month},
            "consumer": consumer,
            "cycle_passed": bool(cycle_passed),
            "dispatch_before": {
                "attempted": int(dispatch_before.attempted),
                "sent": int(dispatch_before.sent),
                "retried": int(dispatch_before.retried),
                "failed": int(dispatch_before.failed),
            },
            "phase6_processing": {
                "attempted": int(print_summary.attempted),
                "printed": int(print_summary.printed),
                "retried": int(print_summary.retried),
                "failed": int(print_summary.failed),
                "contingency": int(print_summary.contingency),
            },
            "phase7a_posting": {
                "attempted": int(posting.attempted),
                "approved": int(posting.approved),
                "posted": int(posting.posted),
                "skipped": int(posting.skipped),
                "failed": int(posting.failed),
                "errors": posting.errors,
            },
            "phase7a_revaluation": (
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
            "phase7b_intercompany": intercompany_reports,
            "phase7b_consolidation": (
                {
                    "run_id": str(consolidation.run_id),
                    "status": str(consolidation.status),
                    "idempotent": bool(consolidation.idempotent),
                    "manifest_hash": str(consolidation.manifest_hash),
                    "issues_count": int(consolidation.issues_count),
                }
                if consolidation is not None
                else {"run_id": "", "status": "FAILED", "error": consolidation_error}
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

        secret = str(os.getenv("PHASE8_EVIDENCE_SECRET", "")).strip()
        signed_payload = build_phase8_evidence(payload=payload, secret=secret)
        raw = json.dumps(signed_payload, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"phase8 burn-in report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not cycle_passed:
            raise CommandError("phase8 burn-in cycle gate failed")
