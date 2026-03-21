from __future__ import annotations

from types import SimpleNamespace

from django.core.management.base import BaseCommand

from apps.modulos.iam.models import OrgUnit
from apps.modulos.reports.models import ReportDefinition
from apps.modulos.reports.registry import REPORT_SPECS
from apps.modulos.reports.services import create_definition


class Command(BaseCommand):
    help = "Crea/actualiza catálogo de ReportDefinition para todos los REPORT_SPECS en compañías destino."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=False)

    def handle(self, *args, **options):
        company_id = options.get("company_id")
        qs = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY).order_by("id")
        if company_id:
            qs = qs.filter(id=int(company_id))

        total_created = 0
        total_updated = 0
        for company in qs:
            req = SimpleNamespace(
                company=company,
                branch=None,
                data_scope={"company_id": int(company.id), "branch_id": None},
                request_id=f"reports-seed-{company.id}",
                META={},
                path="/manage/reports_seed_catalog",
                method="SYSTEM",
            )
            for code, spec in sorted(REPORT_SPECS.items(), key=lambda item: item[0]):
                existed = ReportDefinition.objects.filter(company=company, code=code).exists()
                create_definition(
                    request=req,
                    actor=None,
                    company=company,
                    code=code,
                    name=code,
                    description=f"Seeded from REPORT_SPECS ({spec.family}/{spec.truth_level})",
                    schema_version=3,
                    contract_version=3,
                    is_active=True,
                )
                if existed:
                    total_updated += 1
                else:
                    total_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"reports_seed_catalog completed: created={total_created} updated={total_updated} specs={len(REPORT_SPECS)}"
            )
        )
