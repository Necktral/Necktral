from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.modulos.accounting.certification import build_phase4_evidence
from apps.modulos.accounting.services import project_pending_shadow_ledger_triggers
from apps.modulos.integration.models import InboxEvent, OutboxEvent
from apps.modulos.integration.services import dispatch_outbox_events


class Command(BaseCommand):
    help = "Ejecuta ciclo operativo Shadow Ledger (dispatch + projection + health gate)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--consumer", type=str, default="accounting.projector")
        parser.add_argument("--project-limit", type=int, default=100)
        parser.add_argument("--dispatch-limit", type=int, default=200)
        parser.add_argument("--stale-minutes", type=int, default=30)
        parser.add_argument("--max-inbox-failed", type=int, default=0)
        parser.add_argument("--max-outbox-failed", type=int, default=0)
        parser.add_argument("--max-stale-pending-triggers", type=int, default=0)
        parser.add_argument("--max-projection-failed", type=int, default=0)
        parser.add_argument("--output", type=str, default="")
        parser.add_argument("--no-strict", action="store_true", default=False)

    def handle(self, *args, **options):
        strict = not bool(options.get("no_strict", False))
        company_id = options.get("company_id")
        consumer = str(options.get("consumer") or "accounting.projector").strip() or "accounting.projector"
        project_limit = int(options.get("project_limit") or 100)
        dispatch_limit = int(options.get("dispatch_limit") or 200)
        stale_minutes = int(options.get("stale_minutes") or 30)
        max_inbox_failed = int(options.get("max_inbox_failed") or 0)
        max_outbox_failed = int(options.get("max_outbox_failed") or 0)
        max_stale_pending = int(options.get("max_stale_pending_triggers") or 0)
        max_projection_failed = int(options.get("max_projection_failed") or 0)
        output = str(options.get("output") or "").strip()

        now = timezone.now()
        dispatch_before = dispatch_outbox_events(limit=dispatch_limit, now=now)
        projection = project_pending_shadow_ledger_triggers(limit=project_limit, company_id=company_id)
        dispatch_after = dispatch_outbox_events(limit=dispatch_limit, now=timezone.now(), source_module="ACCOUNTING")

        inbox_failed_qs = InboxEvent.objects.filter(
            consumer=consumer,
            status=InboxEvent.Status.FAILED,
        )
        inbox_failed_count = int(inbox_failed_qs.count())

        outbox_failed_qs = OutboxEvent.objects.filter(
            source_module__in=["CEC", "BILLING", "INVENTORY", "PAYMENTS", "ACCOUNTING"],
            status=OutboxEvent.Status.FAILED,
        )
        trigger_qs = OutboxEvent.objects.filter(
            source_module="CEC",
            event_type="CloseRunPackaged",
        )
        if company_id is not None:
            outbox_failed_qs = outbox_failed_qs.filter(company_id=int(company_id))
            trigger_qs = trigger_qs.filter(company_id=int(company_id))
        outbox_failed_count = int(outbox_failed_qs.count())

        ack_subq = InboxEvent.objects.filter(
            event_id=OuterRef("event_id"),
            consumer=consumer,
            status__in=[InboxEvent.Status.PROCESSED, InboxEvent.Status.FAILED],
        )
        stale_cutoff = now - timedelta(minutes=stale_minutes)
        stale_pending_qs = (
            trigger_qs.annotate(is_acknowledged=Exists(ack_subq))
            .filter(is_acknowledged=False, occurred_at__lte=stale_cutoff)
            .order_by("occurred_at", "id")
        )
        stale_pending_count = int(stale_pending_qs.count())

        checks = [
            {
                "name": "inbox_failed_within_threshold",
                "passed": inbox_failed_count <= max_inbox_failed,
                "detail": {
                    "consumer": consumer,
                    "failed_count": inbox_failed_count,
                    "max_allowed": max_inbox_failed,
                },
            },
            {
                "name": "outbox_failed_within_threshold",
                "passed": outbox_failed_count <= max_outbox_failed,
                "detail": {
                    "failed_count": outbox_failed_count,
                    "max_allowed": max_outbox_failed,
                },
            },
            {
                "name": "stale_pending_triggers_within_threshold",
                "passed": stale_pending_count <= max_stale_pending,
                "detail": {
                    "stale_minutes": stale_minutes,
                    "count": stale_pending_count,
                    "max_allowed": max_stale_pending,
                },
            },
            {
                "name": "projection_failed_within_threshold",
                "passed": int(projection.failed) <= max_projection_failed,
                "detail": {
                    "projection_failed": int(projection.failed),
                    "max_allowed": max_projection_failed,
                },
            },
        ]
        cycle_passed = all(bool(row["passed"]) for row in checks)

        report: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "company_id": int(company_id) if company_id is not None else None,
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
            "dispatch_after": {
                "attempted": int(dispatch_after.attempted),
                "sent": int(dispatch_after.sent),
                "retried": int(dispatch_after.retried),
                "failed": int(dispatch_after.failed),
            },
            "checks": checks,
        }
        secret = str(os.getenv("PHASE4_EVIDENCE_SECRET", "")).strip()
        signed_report = build_phase4_evidence(payload=report, secret=secret)
        raw = json.dumps(signed_report, ensure_ascii=False, indent=2, sort_keys=True)

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"shadow ledger cycle report exported: {path}"))
        else:
            self.stdout.write(raw)

        if strict and not cycle_passed:
            raise CommandError("shadow ledger cycle gate failed.")

