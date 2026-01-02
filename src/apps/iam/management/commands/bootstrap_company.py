from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.iam.models import AdminGrant, OrgUnit, UserMembership
from apps.org.models import BranchProfile, CompanyProfile
from apps.rbac.models import Role, RoleAssignment
from apps.rbac.seed_v01 import seed_rbac_v01

User = get_user_model()

class Command(BaseCommand):
    help = "Bootstrap: crea holding/company/branch y asigna company_admin a un usuario existente."

    def add_arguments(self, parser):
        parser.add_argument("--holding-name", type=str, default="HOLDING")
        parser.add_argument("--company-name", type=str, default=None)
        parser.add_argument("--company-code", type=str, default="")
        parser.add_argument("--branch-name", type=str, default=None)
        parser.add_argument("--branch-code", type=str, default="")
        parser.add_argument("--admin-username", type=str, default=None)
        parser.add_argument("--no-input", action="store_true", default=False)

    def _ask(self, prompt: str) -> str:
        return input(prompt).strip()

    def handle(self, *args, **options):
        no_input = bool(options["no_input"])

        company_name = options["company_name"]
        branch_name = options["branch_name"]
        admin_username = options["admin_username"]

        if not company_name:
            company_name = self._ask("Nombre de la empresa: ")
        if not branch_name:
            branch_name = self._ask("Nombre de la sucursal: ")
        if not admin_username:
            admin_username = self._ask("Username del admin existente: ")
        admin_user = User.objects.filter(username=admin_username).first()
        if not admin_user:
            raise CommandError(f"No existe el usuario: {admin_username}")

        # 1) Seed RBAC v0.1
        seed_rbac_v01()

        # 2) Holding (si existe uno, reutiliza; si no, crea)
        holding_name = options["holding_name"]
        holding = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING).order_by("id").first()
        if not holding:
            holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=holding_name, code="HOLDING", is_active=True)

        # 3) Company + Profile
        company = OrgUnit.objects.create(
            unit_type=OrgUnit.UnitType.COMPANY,
            parent=holding,
            name=company_name,
            code=options["company_code"],
            is_active=True,
        )
        CompanyProfile.objects.get_or_create(company=company)

        # 4) Branch + Profile
        branch = OrgUnit.objects.create(
            unit_type=OrgUnit.UnitType.BRANCH,
            parent=company,
            name=branch_name,
            code=options["branch_code"],
            is_active=True,
        )
        BranchProfile.objects.get_or_create(branch=branch)

        # 5) Membership + RoleAssignment (company_admin)
        UserMembership.objects.get_or_create(user=admin_user, org_unit=company, defaults={"is_active": True})

        role = Role.objects.filter(name="company_admin").first()
        if not role:
            raise CommandError("No existe el rol company_admin")

        RoleAssignment.objects.get_or_create(
            user=admin_user,
            role=role,
            org_unit=company,
            origin=RoleAssignment.Origin.SYSTEM,
            defaults={"is_active": True},
        )

        # 6) AdminGrants (capabilities)
        for cap, _ in AdminGrant.Capability.choices:
            AdminGrant.objects.get_or_create(user=admin_user, capability=cap)

        self.stdout.write(self.style.SUCCESS("Bootstrap OK"))
        self.stdout.write(f"HOLDING: {holding.id} {holding.name}")
        self.stdout.write(f"COMPANY:  {company.id} {company.name}")
        self.stdout.write(f"BRANCH:   {branch.id} {branch.name}")
        self.stdout.write(f"ADMIN:    {admin_user.id} {admin_user.username}")
