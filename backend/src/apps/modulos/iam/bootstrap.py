from __future__ import annotations

from typing import TypedDict
from django.db import transaction
from apps.modulos.iam.models import OrgUnit, UserMembership, AdminGrant
from apps.modulos.org.models import CompanyProfile, BranchProfile
from apps.modulos.accounts.models import User

from apps.modulos.rbac.models import Role, RoleAssignment
from apps.modulos.rbac.seed_v01 import seed_rbac_v01


class InitialAdminData(TypedDict):
    username: str
    email: str
    password: str
    first_name: str
    last_name: str


class OrganizationData(TypedDict):
    holding_name: str
    company_name: str
    company_tax_id: str
    branch_name: str
    branch_address: str


def is_system_fresh() -> bool:
    """Returns True if there are no users in the system."""
    return User.objects.count() == 0


@transaction.atomic
def create_initial_admin(data: InitialAdminData) -> User:
    """Creates the first superuser of the system."""
    if not is_system_fresh():
        raise ValueError("System is not fresh. Cannot create initial admin.")

    user = User.objects.create_superuser(
        username=data["username"],
        email=data["email"],
        password=data["password"],
        first_name=data["first_name"],
        last_name=data["last_name"],
        is_setup_complete=False,  # Setup not complete until Org is created
        must_change_password=False,  # Initial admin sets their own password
    )
    return user


@transaction.atomic
def bootstrap_organization(user: User, data: OrganizationData) -> dict[str, OrgUnit]:
    """
    Creates the initial Holding -> Company -> Branch structure
    and links the user to them.
    """

    # Contrato: bootstrap inicial único
    if OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING, is_active=True).exists():
        raise ValueError("Bootstrap ya realizado.")

    # 1) Seed RBAC (idempotente)
    seed_rbac_v01()

    # 2) Holding
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=data["holding_name"],
        code="",
        is_active=True,
    )

    # 3) Company
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        name=data["company_name"],
        parent=holding,
        code="",
        is_active=True,
    )
    cp, _ = CompanyProfile.objects.get_or_create(company=company)
    cp.tax_id = data.get("company_tax_id", "")
    cp.legal_name = data.get("company_name", "") or data["company_name"]
    cp.save(update_fields=["tax_id", "legal_name"])

    # 4) Branch
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        name=data["branch_name"],
        parent=company,
        code="",
        is_active=True,
    )
    bp, _ = BranchProfile.objects.get_or_create(branch=branch)
    bp.address = data.get("branch_address", "")
    bp.save(update_fields=["address"])

    # 5) Membership a COMPANY (consistente con el flujo actual)
    mem, created = UserMembership.objects.get_or_create(
        user=user,
        org_unit=company,
        defaults={"is_active": True},
    )
    if not created and not mem.is_active:
        mem.is_active = True
        mem.left_at = None
        mem.save(update_fields=["is_active", "left_at"])

    # 6) RoleAssignment SYSTEM: company_admin (scope COMPANY)
    role = Role.objects.filter(name="company_admin").first()
    if not role:
        raise ValueError("Falta role 'company_admin'. Ejecuta seed_rbac_v01.")

    RoleAssignment.objects.get_or_create(
        user=user,
        role=role,
        org_unit=company,
        origin=RoleAssignment.Origin.SYSTEM,
        defaults={"is_active": True, "origin_ref": "bootstrap"},
    )

    # 7) AdminGrants (scoped a COMPANY, completos)
    for cap, _ in AdminGrant.Capability.choices:
        AdminGrant.objects.get_or_create(
            user=user,
            org_unit=company,
            capability=cap,
            defaults={"applies_to_subtree": True, "is_active": True, "granted_by": user},
        )

    # 8) Setup complete
    user.is_setup_complete = True
    user.save(update_fields=["is_setup_complete"])

    return {"holding": holding, "company": company, "branch": branch}
