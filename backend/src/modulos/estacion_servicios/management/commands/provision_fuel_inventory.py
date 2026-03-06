from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.iam.models import OrgUnit
from modulos.estacion_servicios.services import provision_fuel_inventory_for_branch


class Command(BaseCommand):
    help = "Provisiona inventario FUEL (warehouse + items) por sucursal."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--branch-id", type=int, default=None)

    def handle(self, *args, **options):
        company_id = options.get("company_id")
        branch_id = options.get("branch_id")

        qs = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.BRANCH, is_active=True)
        if company_id:
            qs = qs.filter(parent_id=company_id)
        if branch_id:
            qs = qs.filter(id=branch_id)

        total = 0
        for branch in qs:
            res = provision_fuel_inventory_for_branch(company=branch.parent, branch=branch, actor_user=None)
            if res.get("warehouse") or res.get("items"):
                total += 1
                self.stdout.write(f"Provisionado branch {branch.id} (items={res.get('items')})")

        self.stdout.write(f"Provision completo. Branches actualizados: {total}")
