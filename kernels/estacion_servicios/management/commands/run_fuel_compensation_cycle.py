from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.iam.models import OrgUnit
from kernels.estacion_servicios.services import run_fuel_compensation_cycle


class Command(BaseCommand):
    help = "Procesa compensaciones pendientes/fallidas de ventas Fuel."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=False)
        parser.add_argument("--branch-id", type=int, required=False)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--include-failed", action="store_true", default=False)

    def handle(self, *args, **options):
        company_id = options.get("company_id")
        branch_id = options.get("branch_id")
        limit = int(options.get("limit") or 100)
        include_failed = bool(options.get("include_failed", False))

        company = None
        branch = None
        if company_id is not None:
            company = OrgUnit.objects.filter(
                id=int(company_id),
                unit_type=OrgUnit.UnitType.COMPANY,
                is_active=True,
            ).first()
            if company is None:
                raise CommandError(f"company inválida o inactiva: {company_id}")
        if branch_id is not None:
            branch = OrgUnit.objects.filter(
                id=int(branch_id),
                unit_type=OrgUnit.UnitType.BRANCH,
                is_active=True,
            ).first()
            if branch is None:
                raise CommandError(f"branch inválida o inactiva: {branch_id}")

        result = run_fuel_compensation_cycle(
            company=company,
            branch=branch,
            limit=max(1, limit),
            include_failed=include_failed,
            actor_user=None,
        )
        payload = {
            "attempted": int(result.attempted),
            "succeeded": int(result.succeeded),
            "failed": int(result.failed),
            "still_pending": int(result.still_pending),
            "errors": result.errors,
            "include_failed": bool(include_failed),
            "limit": int(max(1, limit)),
            "company_id": int(company.id) if company is not None else None,
            "branch_id": int(branch.id) if branch is not None else None,
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False))

