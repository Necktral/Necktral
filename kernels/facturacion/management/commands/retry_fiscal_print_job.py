from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from kernels.facturacion.models import FiscalPrintJob
from kernels.facturacion.services import retry_fiscal_print_job


class Command(BaseCommand):
    help = "Reprograma un fiscal print job para reproceso manual auditado."

    def add_arguments(self, parser):
        parser.add_argument("--job-id", type=int, required=True)

    def handle(self, *args, **options):
        job_id = int(options["job_id"])
        try:
            FiscalPrintJob.objects.get(id=job_id)
        except FiscalPrintJob.DoesNotExist as exc:
            raise CommandError(f"job {job_id} not found") from exc

        job = retry_fiscal_print_job(job_id=job_id)
        self.stdout.write(
            self.style.SUCCESS(
                f"fiscal print job {job.id} scheduled: status={job.status} attempt_count={job.attempt_count}"
            )
        )
