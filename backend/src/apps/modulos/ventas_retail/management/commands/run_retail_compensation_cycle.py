from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.modulos.iam.models import OrgUnit
from apps.modulos.ventas_retail.services import run_retail_compensation_cycle


class Command(BaseCommand):
    help = "Ejecuta el ciclo de compensación/recovery de ventas retail."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--branch-id", type=int, default=None)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--include-failed", action="store_true", default=False)

    def handle(self, *args, **options):
        company = None
        branch = None
        company_id = options.get("company_id")
        branch_id = options.get("branch_id")
        if company_id is not None:
            company = OrgUnit.objects.get(id=int(company_id))
        if branch_id is not None:
            branch = OrgUnit.objects.get(id=int(branch_id))

        payload = run_retail_compensation_cycle(
            company=company,
            branch=branch,
            limit=int(options.get("limit") or 100),
            include_failed=bool(options.get("include_failed", False)),
        )
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
