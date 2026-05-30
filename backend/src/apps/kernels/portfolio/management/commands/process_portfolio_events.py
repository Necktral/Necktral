"""
Management command to process pending integration events for Portfolio kernel.

Scans OutboxEvents destined for Portfolio (Procurement→Payable, Billing→Receivable)
and processes them via the handlers registry.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.modulos.integration.models import InboxEvent, OutboxEvent

from apps.kernels.portfolio.handlers import EVENT_HANDLERS, dispatch_portfolio_event


class Command(BaseCommand):
    help = "Process pending integration events for the Portfolio kernel"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum number of events to process per run (default: 100)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show events that would be processed without actually processing them",
        )

    def handle(self, *args, **options):
        limit = int(options["limit"])
        dry_run = bool(options["dry_run"])

        # Build Q filter for events the Portfolio is interested in
        q_filter = Q(pk__isnull=True)  # start empty
        for source_module, event_type in EVENT_HANDLERS:
            q_filter |= Q(source_module=source_module, event_type=event_type)

        # Find sent or pending events not yet consumed by PORTFOLIO
        already_consumed = InboxEvent.objects.filter(
            consumer="PORTFOLIO",
        ).values_list("event_id", flat=True)

        events = (
            OutboxEvent.objects.filter(q_filter)
            .filter(status__in=[OutboxEvent.Status.SENT, OutboxEvent.Status.PENDING])
            .exclude(event_id__in=already_consumed)
            .order_by("occurred_at", "id")[:limit]
        )

        total = 0
        processed = 0
        skipped = 0
        errors = 0

        for event in events:
            total += 1
            if dry_run:
                self.stdout.write(
                    f"  [DRY-RUN] Would process: {event.source_module}.{event.event_type} "
                    f"(event_id={event.event_id})"
                )
                continue

            try:
                result = dispatch_portfolio_event(event)
                if result is None:
                    skipped += 1
                elif result.get("ok"):
                    if result.get("skipped"):
                        skipped += 1
                    else:
                        processed += 1
                else:
                    errors += 1
                    self.stderr.write(
                        f"  ERROR: {event.source_module}.{event.event_type} "
                        f"event_id={event.event_id}: {result.get('error', 'unknown')}"
                    )
            except Exception as exc:
                errors += 1
                self.stderr.write(
                    f"  EXCEPTION: {event.source_module}.{event.event_type} "
                    f"event_id={event.event_id}: {exc}"
                )

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Dry run complete. {total} events found."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Portfolio events processed: {processed} ok, {skipped} skipped, "
                    f"{errors} errors (total: {total})"
                )
            )
