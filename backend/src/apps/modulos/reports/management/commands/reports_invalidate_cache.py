from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.iam.models import OrgUnit
from apps.modulos.reports.services import invalidate_dataset_cache


class Command(BaseCommand):
    help = "Invalida cache de datasets del módulo reports por company/dataset/version."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--dataset-code", type=str, required=True)
        parser.add_argument("--dataset-version", type=str, required=False, default="")
        parser.add_argument("--source-manifest-hash", type=str, required=False, default="")

    def handle(self, *args, **options):
        company = OrgUnit.objects.filter(id=int(options["company_id"]), unit_type=OrgUnit.UnitType.COMPANY).first()
        if company is None:
            raise CommandError("company not found or not a COMPANY unit")
        deleted = invalidate_dataset_cache(
            company=company,
            dataset_code=str(options["dataset_code"]).strip(),
            dataset_version=str(options.get("dataset_version") or "").strip(),
            source_manifest_hash=str(options.get("source_manifest_hash") or "").strip(),
        )
        self.stdout.write(self.style.SUCCESS(f"dataset_cache_deleted={deleted}"))
