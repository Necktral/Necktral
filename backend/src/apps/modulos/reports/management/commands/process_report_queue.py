from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.modulos.reports.services import process_queued_runs


class Command(BaseCommand):
    help = "Procesa corridas en cola de reports."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        summary = process_queued_runs(limit=int(options.get("limit") or 20))
        self.stdout.write(
            self.style.SUCCESS(
                f"processed={int(summary.get('processed') or 0)} failed={int(summary.get('failed') or 0)}"
            )
        )

