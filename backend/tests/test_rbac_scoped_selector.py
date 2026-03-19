import pytest
from django.contrib.auth import get_user_model

from apps.modulos.iam.models import OrgUnit
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission, UserRole
from apps.modulos.rbac.selectors import get_effective_permissions_for_scope

User = get_user_model()


@pytest.mark.django_db
def test_scoped_role_assignment_company_applies_in_company_context():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    c1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    b1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=c1)

    user = User.objects.create_user(username="u1", password="pass12345")

    role = Role.objects.create(name="warehouse", is_active=True)
    perm = Permission.objects.create(code="inventory.read", is_active=True)
    RolePermission.objects.create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=c1, is_active=True)

    perms_company = get_effective_permissions_for_scope(user, company=c1, branch=None, include_global=False)
    assert "inventory.read" in perms_company

    perms_branch = get_effective_permissions_for_scope(user, company=c1, branch=b1, include_global=False)
    assert "inventory.read" in perms_branch


@pytest.mark.django_db
def test_scoped_role_assignment_branch_applies_only_in_that_branch():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    c1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    b1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=c1)
    b2 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B2", parent=c1)

    user = User.objects.create_user(username="u2", password="pass12345")

    role = Role.objects.create(name="sales", is_active=True)
    perm = Permission.objects.create(code="clients.read", is_active=True)
    RolePermission.objects.create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=b1, is_active=True)

    perms_b1 = get_effective_permissions_for_scope(user, company=c1, branch=b1, include_global=False)
    assert "clients.read" in perms_b1

    perms_b2 = get_effective_permissions_for_scope(user, company=c1, branch=b2, include_global=False)
    assert "clients.read" not in perms_b2


@pytest.mark.django_db
def test_include_global_legacy_userrole_still_works_for_transition():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    c1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)

    user = User.objects.create_user(username="u3", password="pass12345")

    role = Role.objects.create(name="legacy_global", is_active=True)
    perm = Permission.objects.create(code="reports.view", is_active=True)
    RolePermission.objects.create(role=role, permission=perm)

    UserRole.objects.create(user=user, role=role)

    perms = get_effective_permissions_for_scope(user, company=c1, branch=None, include_global=True)
    assert "reports.view" in perms

    perms_no_global = get_effective_permissions_for_scope(user, company=c1, branch=None, include_global=False)
    assert "reports.view" not in perms_no_global
