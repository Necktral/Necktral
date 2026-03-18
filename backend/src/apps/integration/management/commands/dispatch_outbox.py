from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.integration.services import dispatch_outbox_events


class Command(BaseCommand):
    help = "Despacha eventos pendientes del outbox con politica de retry/DLQ."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--source-module", type=str, default="")

    def handle(self, *args, **options):
        summary = dispatch_outbox_events(
            limit=int(options["limit"]),
            source_module=str(options.get("source_module") or ""),
        )
        self.stdout.write(
            self.style.SUCCESS(
                "outbox dispatched: "
                f"attempted={summary.attempted} sent={summary.sent} "
                f"retried={summary.retried} failed={summary.failed}"
            )
        )
