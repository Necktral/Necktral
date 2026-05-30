"""
Management command to update aging for all obligations

Usage:
    python manage.py update_portfolio_aging --company-id=1
    python manage.py update_portfolio_aging --all-companies
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.modulos.org.models import OrgUnit
from apps.kernels.portfolio import services


class Command(BaseCommand):
    help = "Update aging buckets and days overdue for all obligations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--company-id",
            type=int,
            help="Specific company ID to process"
        )
        parser.add_argument(
            "--all-companies",
            action="store_true",
            help="Process all companies"
        )
        parser.add_argument(
            "--as-of-date",
            type=str,
            help="As-of date (YYYY-MM-DD), defaults to today"
        )

    def handle(self, *args, **options):
        company_id = options.get("company_id")
        all_companies = options.get("all_companies")
        as_of_date_str = options.get("as_of_date")

        # Parse date
        if as_of_date_str:
            as_of_date = date.fromisoformat(as_of_date_str)
        else:
            as_of_date = timezone.localdate()

        self.stdout.write(f"Updating aging as of: {as_of_date}")

        # Get companies to process
        if company_id:
            companies = [OrgUnit.objects.get(id=company_id)]
        elif all_companies:
            companies = OrgUnit.objects.filter(is_company=True)
        else:
            self.stdout.write(self.style.ERROR("Must specify --company-id or --all-companies"))
            return

        for company in companies:
            self.stdout.write(f"\nProcessing company: {company.name}")

            try:
                services.update_aging_for_obligations(company, as_of_date)
                self.stdout.write(self.style.SUCCESS(f"  ✓ Updated aging for {company.name}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {e}"))

        self.stdout.write(self.style.SUCCESS("\n✓ Aging update complete"))
