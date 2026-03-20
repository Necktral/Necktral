from __future__ import annotations

from django.core.management.base import BaseCommand

from kernels.facturacion.services import process_fiscal_print_jobs


class Command(BaseCommand):
    help = "Procesa cola fiscal de impresion con retry exponencial y contingencia."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--company-id", type=int, required=False)
        parser.add_argument("--branch-id", type=int, required=False)

    def handle(self, *args, **options):
        summary = process_fiscal_print_jobs(
            limit=int(options.get("limit") or 100),
            company_id=options.get("company_id"),
            branch_id=options.get("branch_id"),
        )
        self.stdout.write(
            self.style.SUCCESS(
                "fiscal print jobs processed: "
                f"attempted={summary.attempted} "
                f"printed={summary.printed} "
                f"retried={summary.retried} "
                f"failed={summary.failed} "
                f"contingency={summary.contingency}"
            )
        )
