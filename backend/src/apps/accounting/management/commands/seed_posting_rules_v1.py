from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.accounting.services import seed_posting_rules_v1_for_company
from apps.iam.models import OrgUnit


class Command(BaseCommand):
    help = "Seed idempotente de PostingRuleSet v1 para Shadow Ledger (Fase 4A)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, default=None)

    def handle(self, *args, **options):
        company_id = options.get("company_id")
        qs = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY, is_active=True).order_by("id")
        if company_id is not None:
            qs = qs.filter(id=int(company_id))

        created = unchanged = 0
        for company in qs:
            _, was_created = seed_posting_rules_v1_for_company(company=company)
            if was_created:
                created += 1
            else:
                unchanged += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"posting_rules_v1 seeded: companies_created_or_updated={created} companies_unchanged={unchanged}"
            )
        )
