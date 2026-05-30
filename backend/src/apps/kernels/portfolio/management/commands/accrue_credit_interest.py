"""
Management command to accrue interest on active credits

Usage:
    python manage.py accrue_credit_interest --company-id=1
    python manage.py accrue_credit_interest --all-companies
"""
from decimal import Decimal
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.modulos.org.models import OrgUnit
from apps.kernels.portfolio.models import Credit, CreditStatus, PortfolioSettings
from apps.kernels.portfolio import services


class Command(BaseCommand):
    help = "Accrue interest on active credits"

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
            "--accrual-date",
            type=str,
            help="Accrual date (YYYY-MM-DD), defaults to today"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Dry run without saving"
        )

    def handle(self, *args, **options):
        company_id = options.get("company_id")
        all_companies = options.get("all_companies")
        accrual_date_str = options.get("accrual_date")
        dry_run = options.get("dry_run")

        # Parse accrual date
        if accrual_date_str:
            accrual_date = date.fromisoformat(accrual_date_str)
        else:
            accrual_date = timezone.localdate()

        self.stdout.write(f"Accruing interest for date: {accrual_date}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be saved"))

        # Get companies to process
        if company_id:
            companies = [OrgUnit.objects.get(id=company_id)]
        elif all_companies:
            companies = OrgUnit.objects.filter(is_company=True)
        else:
            self.stdout.write(self.style.ERROR("Must specify --company-id or --all-companies"))
            return

        total_processed = 0
        total_accrued = Decimal("0.00")

        for company in companies:
            self.stdout.write(f"\nProcessing company: {company.name}")

            # Get portfolio settings
            settings = PortfolioSettings.get_or_create_for_company(company)
            frequency = settings.interest_accrual_frequency

            # Determine period
            if frequency == "MONTHLY":
                # Last day of previous month
                first_of_month = accrual_date.replace(day=1)
                period_end = first_of_month - timedelta(days=1)
                period_start = period_end.replace(day=1)
            elif frequency == "DAILY":
                period_start = accrual_date
                period_end = accrual_date
            else:
                self.stdout.write(self.style.WARNING(f"Unsupported frequency: {frequency}"))
                continue

            # Get active credits
            credits = Credit.objects.filter(
                company=company,
                credit_status__in=[CreditStatus.DISBURSED, CreditStatus.ACTIVE],
                disbursement_date__lte=period_end,
            )

            self.stdout.write(f"Found {credits.count()} active credits")

            for credit in credits:
                try:
                    if not dry_run:
                        accrual = services.accrue_interest_for_credit(
                            credit=credit,
                            accrual_date=accrual_date,
                            period_start=period_start,
                            period_end=period_end,
                        )

                        if accrual:
                            total_processed += 1
                            total_accrued += accrual.accrued_interest
                            self.stdout.write(
                                f"  ✓ Credit {credit.contract_number}: {accrual.accrued_interest} {credit.currency}"
                            )
                        else:
                            self.stdout.write(
                                f"  - Credit {credit.contract_number}: skipped (already exists or no balance)"
                            )
                    else:
                        # Dry run: just calculate
                        principal = credit.disbursed_amount - credit.allocated_amount
                        if principal > 0:
                            self.stdout.write(
                                f"  [DRY] Credit {credit.contract_number}: principal={principal}"
                            )
                            total_processed += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"  ✗ Error processing {credit.contract_number}: {e}")
                    )

        self.stdout.write(self.style.SUCCESS(f"\n✓ Processed {total_processed} credits"))
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"✓ Total accrued: {total_accrued}"))
