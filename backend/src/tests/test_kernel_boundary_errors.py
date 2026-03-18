from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="boundaries@test.com", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    resp = client.post("/api/backend/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert resp.status_code == 200
    access = resp.data.get("access") if isinstance(resp.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_inventory_transfer_same_warehouse_returns_400_not_500():
    company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["inventory.transfer.create"])

    resp = client.post(
        "/api/inventory/transfers/",
        {"from_warehouse_id": 1, "to_warehouse_id": 1, "item_id": 1, "qty": "1.0000"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_billing_create_without_branch_returns_400_not_500():
    company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["billing.doc.create"])
    del client.defaults["HTTP_X_BRANCH_ID"]

    resp = client.post(
        "/api/billing/docs/",
        {
            "doc_type": "INVOICE",
            "series": "A",
            "currency": "NIO",
            "lines": [{"description": "x", "quantity": "1.0000", "unit_price": "10.000000", "tax_rate": "0.0000"}],
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_billing_issue_not_found_returns_404_not_500():
    company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["billing.doc.issue"])

    resp = client.post("/api/billing/docs/99999/issue/", {"apply_inventory": False}, format="json")
    assert resp.status_code == 404
