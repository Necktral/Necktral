from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Role, Permission, RoleAssignment, RolePermission
from apps.accounts.models import User
from apps.audit.models import AuditEvent


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(user: User, company: OrgUnit, branch: OrgUnit, perms: list[str]) -> APIClient:
    role = Role.objects.create(name="tmp_role2", is_active=True)
    for p in perms:
        perm, _ = Permission.objects.get_or_create(code=p, defaults={"description": p, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)

    # RBAC scoped real: RoleAssignment se asigna por org_unit (COMPANY y/o BRANCH)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, origin=RoleAssignment.Origin.MANUAL)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, origin=RoleAssignment.Origin.MANUAL)

    c = APIClient()

    # Flujo real: login => JWT => JWTAuthWithOrgContext inyecta company/branch
    login = c.post(
        "/api/auth/login/",
        {"username": user.username, "password": "x"},
        format="json",
    )
    assert login.status_code == 200
    access = login.data["access"]
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


@pytest.mark.django_db
def test_billing_create_issue_void_audited():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="u2", password="x")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    c = _client_with_perms(
        user,
        company,
        branch,
        ["billing.doc.create", "billing.doc.read", "billing.doc.issue", "billing.doc.void"],
    )

    r = c.post(
        "/api/billing/docs/",
        {
            "doc_type": "INVOICE",
            "series": "A",
            "currency": "NIO",
            "customer_name": "Cliente 1",
            "is_fiscal": True,
            "idempotency_key": "b1",
            "lines": [
                {"description": "Servicio", "quantity": "1.0000", "unit_price": "100.000000", "tax_rate": "0.1500"},
            ],
        },
        format="json",
    )
    assert r.status_code == 201
    doc_id = r.data["id"]

    r = c.post(f"/api/billing/docs/{doc_id}/issue/", {"apply_inventory": False}, format="json")
    assert r.status_code == 200
    assert r.data["ok"] is True

    r = c.post(f"/api/billing/docs/{doc_id}/void/", {"reason": "Cliente canceló"}, format="json")
    assert r.status_code == 200
    assert r.data["ok"] is True

    assert AuditEvent.objects.filter(module="BILLING", event_type="BILLING_DOC_CREATED").count() >= 1
    assert AuditEvent.objects.filter(module="BILLING", event_type="BILLING_DOC_ISSUED").count() >= 1
    assert AuditEvent.objects.filter(module="BILLING", event_type="BILLING_DOC_VOIDED").count() >= 1


@pytest.mark.django_db
def test_billing_doc_cannot_void_draft():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="u3", password="x")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    c = _client_with_perms(
        user,
        company,
        branch,
        ["billing.doc.create", "billing.doc.void"],
    )

    r = c.post(
        "/api/billing/docs/",
        {
            "doc_type": "INVOICE",
            "series": "A",
            "currency": "NIO",
            "customer_name": "Cliente 2",
            "is_fiscal": False,
            "idempotency_key": "b2",
            "lines": [
                {"description": "Servicio", "quantity": "1.0000", "unit_price": "50.000000", "tax_rate": "0.1500"},
            ],
        },
        format="json",
    )
    assert r.status_code == 201
    doc_id = r.data["id"]

    r = c.post(f"/api/billing/docs/{doc_id}/void/", {"reason": "No emitido"}, format="json")
    assert r.status_code == 400
    assert "draft" in r.data["error"]["message"]


@pytest.mark.django_db
def test_billing_doc_issue_idempotent():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="u4", password="x")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    c = _client_with_perms(
        user,
        company,
        branch,
        ["billing.doc.create", "billing.doc.issue"],
    )

    r = c.post(
        "/api/billing/docs/",
        {
            "doc_type": "INVOICE",
            "series": "A",
            "currency": "NIO",
            "customer_name": "Cliente 3",
            "is_fiscal": False,
            "idempotency_key": "b3",
            "lines": [
                {"description": "Servicio", "quantity": "1.0000", "unit_price": "25.000000", "tax_rate": "0.1500"},
            ],
        },
        format="json",
    )
    assert r.status_code == 201
    doc_id = r.data["id"]

    r1 = c.post(f"/api/billing/docs/{doc_id}/issue/", {"apply_inventory": False}, format="json")
    assert r1.status_code == 200
    assert r1.data["ok"] is True

    r2 = c.post(f"/api/billing/docs/{doc_id}/issue/", {"apply_inventory": False}, format="json")
    assert r2.status_code == 200
    assert r2.data.get("already_issued") is True
