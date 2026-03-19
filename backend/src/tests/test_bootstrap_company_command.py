import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.modulos.iam.models import AdminGrant, OrgUnit, UserMembership
from apps.modulos.org.models import BranchProfile, CompanyProfile
from apps.modulos.rbac.models import Role, RoleAssignment

User = get_user_model()


@pytest.mark.django_db
def test_bootstrap_company_no_input_requires_required_params():
    """
    Contrato: con no_input=True, si faltan parámetros obligatorios, el comando falla.
    """
    User.objects.create_user(username="admin", password="pass12345")

    with pytest.raises(CommandError):
        call_command("bootstrap_company", no_input=True)


@pytest.mark.django_db
def test_bootstrap_company_is_idempotent_and_scoped_to_company():
    """
    Contrato v0.1 del bootstrap:
    - crea/reutiliza HOLDING/COMPANY/BRANCH sin duplicar (idempotencia)
    - crea CompanyProfile y BranchProfile
    - asigna membership al admin en COMPANY
    - asigna RoleAssignment origin=SYSTEM al role company_admin (scope COMPANY)
    - crea AdminGrants scoped a COMPANY y activos
    """
    User.objects.create_user(username="admin", password="pass12345")

    args = dict(
        holding_name="HOLDING",
        company_name="ACME",
        company_code="AC",
        branch_name="ACME-1",
        branch_code="AC1",
        admin_username="admin",
        no_input=True,
    )

    # 1ra corrida
    call_command("bootstrap_company", **args)

    # Validar árbol ORG
    assert OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING).count() == 1
    holding = OrgUnit.objects.get(unit_type=OrgUnit.UnitType.HOLDING)

    assert OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY, parent=holding).count() == 1
    company = OrgUnit.objects.get(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, code="AC")

    assert OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.BRANCH, parent=company).count() == 1
    branch = OrgUnit.objects.get(unit_type=OrgUnit.UnitType.BRANCH, parent=company, code="AC1")

    # Profiles ORG
    assert CompanyProfile.objects.filter(company=company).exists()
    assert BranchProfile.objects.filter(branch=branch).exists()

    admin = User.objects.get(username="admin")

    # Membership: COMPANY
    mem = UserMembership.objects.get(user=admin, org_unit=company)
    assert mem.is_active is True

    # RoleAssignment: company_admin, origin SYSTEM, scope COMPANY
    role = Role.objects.get(name="company_admin")
    ra = RoleAssignment.objects.get(
        user=admin,
        role=role,
        org_unit=company,
        origin=RoleAssignment.Origin.SYSTEM,
    )
    assert ra.is_active is True

    # AdminGrants: scoped a COMPANY y completos
    expected_caps = {cap for cap, _ in AdminGrant.Capability.choices}
    grants = AdminGrant.objects.filter(user=admin, org_unit=company)
    assert set(grants.values_list("capability", flat=True)) == expected_caps
    assert all(g.is_active for g in grants)
    assert all(getattr(g, "applies_to_subtree", True) for g in grants)

    # Snapshot de conteos (idempotencia)
    counts_before = dict(
        org=OrgUnit.objects.count(),
        profiles_company=CompanyProfile.objects.count(),
        profiles_branch=BranchProfile.objects.count(),
        membership=UserMembership.objects.filter(user=admin, org_unit=company).count(),
        role_assignment=RoleAssignment.objects.filter(
            user=admin, role=role, org_unit=company, origin=RoleAssignment.Origin.SYSTEM
        ).count(),
        grants=AdminGrant.objects.filter(user=admin, org_unit=company).count(),
    )

    # 2da corrida: no duplica
    call_command("bootstrap_company", **args)

    counts_after = dict(
        org=OrgUnit.objects.count(),
        profiles_company=CompanyProfile.objects.count(),
        profiles_branch=BranchProfile.objects.count(),
        membership=UserMembership.objects.filter(user=admin, org_unit=company).count(),
        role_assignment=RoleAssignment.objects.filter(
            user=admin, role=role, org_unit=company, origin=RoleAssignment.Origin.SYSTEM
        ).count(),
        grants=AdminGrant.objects.filter(user=admin, org_unit=company).count(),
    )

    assert counts_after == counts_before
