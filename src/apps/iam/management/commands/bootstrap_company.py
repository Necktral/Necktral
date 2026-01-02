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

    def _require_no_input(self, *, no_input: bool, company_name: str | None, branch_name: str | None, admin_username: str | None) -> None:
        if not no_input:
            return
        missing = []
        if not company_name:
            missing.append("--company-name")
        if not branch_name:
            missing.append("--branch-name")
        if not admin_username:
            missing.append("--admin-username")
        if missing:
            raise CommandError(f"--no-input requiere: {', '.join(missing)}")

    def _find_or_create_holding(self, holding_name: str) -> OrgUnit:
        holding = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING).order_by("id").first()
        if holding:
            if not holding.is_active:
                holding.is_active = True
                holding.save(update_fields=["is_active"])
            if holding.name != holding_name:
                holding.name = holding_name
                holding.save(update_fields=["name"])
            return holding
        return OrgUnit.objects.create(
            unit_type=OrgUnit.UnitType.HOLDING,
            name=holding_name,
            code="",
            is_active=True,
        )

    def _find_company(self, holding: OrgUnit, company_code: str, company_name: str) -> OrgUnit | None:
        qs = OrgUnit.objects.filter(parent=holding, unit_type=OrgUnit.UnitType.COMPANY)
        if company_code:
            obj = qs.filter(code=company_code).order_by("id").first()
            if obj:
                return obj
        return qs.filter(name=company_name).order_by("id").first()

    def _find_branch(self, company: OrgUnit, branch_code: str, branch_name: str) -> OrgUnit | None:
        qs = OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH)
        if branch_code:
            obj = qs.filter(code=branch_code).order_by("id").first()
            if obj:
                return obj
        return qs.filter(name=branch_name).order_by("id").first()

    def handle(self, *args, **options):
        from django.db import transaction
        no_input = bool(options["no_input"])

        company_name = options["company_name"]
        branch_name = options["branch_name"]
        admin_username = options["admin_username"]

        self._require_no_input(
            no_input=no_input,
            company_name=company_name,
            branch_name=branch_name,
            admin_username=admin_username,
        )

        if not company_name:
            company_name = self._ask("Nombre de la empresa (company_name): ")
            if not company_name:
                raise CommandError("company_name vacío.")

        if not branch_name:
            branch_name = self._ask("Nombre de la sucursal inicial (branch_name): ")
            if not branch_name:
                raise CommandError("branch_name vacío.")

        if not admin_username:
            admin_username = self._ask("Username del admin Django existente: ")
            if not admin_username:
                raise CommandError("admin_username vacío.")

        admin_user = User.objects.filter(username=admin_username).first()
        if not admin_user:
            raise CommandError(f"No existe usuario username='{admin_username}'.")

        with transaction.atomic():
            # 1) Seed RBAC v0.1 (idempotente)
            seed_rbac_v01()

            # 2) Holding
            holding_name = options["holding_name"]
            holding = self._find_or_create_holding(holding_name)

            # 3) Company (idempotente)
            company_code = (options["company_code"] or "").strip()
            company = self._find_company(holding, company_code, company_name)
            if company is None:
                company = OrgUnit.objects.create(
                    unit_type=OrgUnit.UnitType.COMPANY,
                    parent=holding,
                    name=company_name,
                    code=company_code,
                    is_active=True,
                )
            else:
                updates = []
                if not company.is_active:
                    company.is_active = True
                    updates.append("is_active")
                if company.name != company_name:
                    company.name = company_name
                    updates.append("name")
                if company_code and company.code != company_code:
                    company.code = company_code
                    updates.append("code")
                if updates:
                    company.save(update_fields=updates)

            CompanyProfile.objects.get_or_create(company=company)

            # 4) Branch (idempotente)
            branch_code = (options["branch_code"] or "").strip()
            branch = self._find_branch(company, branch_code, branch_name)
            if branch is None:
                branch = OrgUnit.objects.create(
                    unit_type=OrgUnit.UnitType.BRANCH,
                    parent=company,
                    name=branch_name,
                    code=branch_code,
                    is_active=True,
                )
            else:
                updates = []
                if not branch.is_active:
                    branch.is_active = True
                    updates.append("is_active")
                if branch.name != branch_name:
                    branch.name = branch_name
                    updates.append("name")
                if branch_code and branch.code != branch_code:
                    branch.code = branch_code
                    updates.append("code")
                if updates:
                    branch.save(update_fields=updates)

            BranchProfile.objects.get_or_create(branch=branch)

            # 5) Membership a la company (reactivar si estaba off)
            mem, created = UserMembership.objects.get_or_create(
                user=admin_user,
                org_unit=company,
                defaults={"is_active": True},
            )
            if (not created) and (not mem.is_active):
                mem.is_active = True
                mem.left_at = None
                mem.save(update_fields=["is_active", "left_at"])

            # 6) RoleAssignment SYSTEM (company_admin) - reactivar si existe
            role = Role.objects.filter(name="company_admin").first()
            if not role:
                raise CommandError("No existe role 'company_admin'. Ejecuta seed_rbac_v01 primero.")

            ra, ra_created = RoleAssignment.objects.get_or_create(
                user=admin_user,
                role=role,
                org_unit=company,
                origin=RoleAssignment.Origin.SYSTEM,
                defaults={"is_active": True, "origin_ref": "bootstrap"},
            )
            if (not ra_created) and (not ra.is_active):
                ra.is_active = True
                ra.origin_ref = "bootstrap"
                ra.save(update_fields=["is_active", "origin_ref"])

            # 7) AdminGrants: siempre con org_unit=company (y reactivar si estaban off)
            for cap, _ in AdminGrant.Capability.choices:
                ag, ag_created = AdminGrant.objects.get_or_create(
                    user=admin_user,
                    org_unit=company,
                    capability=cap,
                    defaults={"applies_to_subtree": True, "is_active": True},
                )
                if (not ag_created) and (not ag.is_active or not ag.applies_to_subtree):
                    ag.is_active = True
                    ag.applies_to_subtree = True
                    ag.save(update_fields=["is_active", "applies_to_subtree"])

        self.stdout.write(self.style.SUCCESS("Bootstrap OK"))
        self.stdout.write(f"HOLDING: {holding.id} {holding.name}")
        self.stdout.write(f"COMPANY:  {company.id} {company.name}")
        self.stdout.write(f"BRANCH:   {branch.id} {branch.name}")
        self.stdout.write(f"ADMIN:    {admin_user.id} {admin_user.username}")
