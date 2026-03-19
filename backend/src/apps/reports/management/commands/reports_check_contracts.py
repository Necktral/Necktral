from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.reports.models import ReportDefinition
from apps.reports.registry import REPORT_SPECS


class Command(BaseCommand):
    help = "Verifica compatibilidad de ReportDefinition DB vs contract-as-code (registry)."

    def handle(self, *args, **options):
        errors: list[str] = []
        for row in ReportDefinition.objects.all().order_by("company_id", "code"):
            spec = REPORT_SPECS.get(row.code)
            if spec is None:
                errors.append(f"[{row.company_id}] {row.code}: missing spec")
                continue
            if row.truth_level != spec.truth_level:
                errors.append(f"[{row.company_id}] {row.code}: truth_level mismatch db={row.truth_level} spec={spec.truth_level}")
            if row.report_family != spec.family:
                errors.append(f"[{row.company_id}] {row.code}: family mismatch db={row.report_family} spec={spec.family}")
            if row.reproducibility_mode != spec.reproducibility_mode:
                errors.append(
                    f"[{row.company_id}] {row.code}: reproducibility mismatch db={row.reproducibility_mode} spec={spec.reproducibility_mode}"
                )
            if int(row.schema_version) <= 0 or int(row.contract_version) <= 0:
                errors.append(f"[{row.company_id}] {row.code}: invalid schema/contract version")

        if errors:
            for err in errors:
                self.stderr.write(err)
            raise CommandError(f"reports contract check failed ({len(errors)} errors)")
        self.stdout.write(self.style.SUCCESS("reports contract check passed"))

