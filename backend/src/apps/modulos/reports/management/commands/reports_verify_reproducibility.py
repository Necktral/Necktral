from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.reports.models import ReportRun


class Command(BaseCommand):
    help = "Verifica consistencia de hashes de reproducibilidad en corridas de reports."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=False)

    def handle(self, *args, **options):
        qs = ReportRun.objects.filter(status=ReportRun.Status.SUCCEEDED).exclude(reproducibility_mode=ReportRun.ReproducibilityMode.LIVE)
        company_id = options.get("company_id")
        if company_id:
            qs = qs.filter(company_id=int(company_id))
        failures = []
        for run in qs.order_by("-started_at"):
            if not str(run.source_manifest_hash or "").strip() or not str(run.output_manifest_hash or "").strip():
                failures.append(f"{run.run_id}: missing manifest hashes")
        if failures:
            for row in failures:
                self.stderr.write(row)
            raise CommandError(f"reproducibility check failed ({len(failures)} issues)")
        self.stdout.write(self.style.SUCCESS(f"reproducibility check passed ({qs.count()} runs)"))

