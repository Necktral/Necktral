from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.iam.models import OrgUnit
from modulos.facturacion.services import provision_billing_sequences_for_branch


class Command(BaseCommand):
    help = "Provisiona secuencias de facturacion por sucursal."

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
            res = provision_billing_sequences_for_branch(company=branch.parent, branch=branch, actor_user=None)
            if res.get("created"):
                total += 1
                self.stdout.write(f"Provisionado branch {branch.id} (created={res.get('created')})")

        self.stdout.write(f"Provision completo. Branches actualizados: {total}")
