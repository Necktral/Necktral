import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.iam.models import AdminGrant, OrgUnit, UserMembership
from apps.org.models import BranchProfile, CompanyProfile
from apps.rbac.models import Role, RoleAssignment

User = get_user_model()


@pytest.mark.django_db
def test_bootstrap_company_command_is_idempotent_and_scoped_to_company():
    admin = User.objects.create_user(username="admin", password="pass12345")

    # 1ra corrida
    call_command(
        "bootstrap_company",
        "--no-input",
        "--holding-name", "HOLDING",
        "--company-name", "ACME",
        "--company-code", "AC",
        "--branch-name", "ACME-1",
        "--branch-code", "AC1",
        "--admin-username", "admin",
    )

    holding = OrgUnit.objects.get(unit_type=OrgUnit.UnitType.HOLDING)
    company = OrgUnit.objects.get(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name="ACME")
    branch = OrgUnit.objects.get(unit_type=OrgUnit.UnitType.BRANCH, parent=company, name="ACME-1")

    assert CompanyProfile.objects.filter(company=company).exists()
    assert BranchProfile.objects.filter(branch=branch).exists()

    mem = UserMembership.objects.get(user=admin, org_unit=company)
    assert mem.is_active is True

    role = Role.objects.get(name="company_admin")
    ra = RoleAssignment.objects.get(
        user=admin,
        role=role,
        org_unit=company,
        origin=RoleAssignment.Origin.SYSTEM,
    )
    assert ra.is_active is True

    expected_caps = {cap for cap, _ in AdminGrant.Capability.choices}
    grants = AdminGrant.objects.filter(user=admin, org_unit=company)
    assert set(grants.values_list("capability", flat=True)) == expected_caps
    assert all(g.is_active and g.applies_to_subtree for g in grants)

    # Captura de conteos para idempotencia
    org_count = OrgUnit.objects.count()
    mem_count = UserMembership.objects.filter(user=admin, org_unit=company).count()
    ra_count = RoleAssignment.objects.filter(
        user=admin, role=role, org_unit=company, origin=RoleAssignment.Origin.SYSTEM
    ).count()
    grant_count = AdminGrant.objects.filter(user=admin, org_unit=company).count()

    # 2da corrida (mismos inputs) -> no debe duplicar
    call_command(
        "bootstrap_company",
        "--no-input",
        "--holding-name", "HOLDING",
        "--company-name", "ACME",
        "--company-code", "AC",
        "--branch-name", "ACME-1",
        "--branch-code", "AC1",
        "--admin-username", "admin",
    )

    assert OrgUnit.objects.count() == org_count
    assert UserMembership.objects.filter(user=admin, org_unit=company).count() == mem_count
    assert RoleAssignment.objects.filter(
        user=admin, role=role, org_unit=company, origin=RoleAssignment.Origin.SYSTEM
    ).count() == ra_count
    assert AdminGrant.objects.filter(user=admin, org_unit=company).count() == grant_count
