from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.kernels.facturacion import services as billing_services
from apps.kernels.facturacion.models import BillingDocument, DocType
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.parties.models import Party, PartyRole
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _org_tree(*, suffix: str = ""):
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Bill Holding{suffix}",
        code=f"BH{suffix}",
        is_active=True,
    )
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name=f"Bill Company{suffix}",
        code=f"BC{suffix}",
        is_active=True,
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Bill Branch{suffix}",
        code=f"BB{suffix}",
        is_active=True,
    )
    return company, branch


def _request(*, company, branch, user):
    return SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        request_id=f"req-bill-customer-party-{uuid.uuid4().hex[:8]}",
        headers={},
        META={},
        path="/api/billing/docs/",
        method="POST",
    )


def _party(*, company, suffix: str = "") -> Party:
    token = suffix or uuid.uuid4().hex[:8]
    return Party.objects.create(
        company=company,
        party_type=Party.PartyType.JURIDICAL,
        display_name=f"Cliente Party {token}",
        tax_id=f"RUC-CLI-{token}",
        national_id=f"NAT-CLI-{token}",
    )


def _create_doc(
    *,
    request,
    user,
    customer_party_id=None,
    idempotency_key: str = "idem-bill-customer-party",
    series: str = "A",
):
    return billing_services.create_draft(
        request=request,
        actor=user,
        doc_type=DocType.INVOICE,
        series=series,
        currency="NIO",
        customer_name="Cliente Snapshot",
        customer_ref="CLI-001",
        customer_party_id=customer_party_id,
        is_fiscal=False,
        lines=[
            {
                "description": "Servicio",
                "quantity": "1",
                "unit_price": "100.00",
                "tax_rate": "0.15",
            }
        ],
        idempotency_key=idempotency_key,
    )


def _billing_perms() -> list[str]:
    return ["billing.doc.create", "billing.doc.read", "billing.doc.issue", "billing.doc.void"]


def _client(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str] | None = None) -> tuple[APIClient, Any]:
    username = f"bill_party_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"bill_party_role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes or _billing_perms():
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client, user


def _billing_payload(*, customer_party_id=None, idempotency_key: str = "idem-bill-api"):
    return {
        "doc_type": "INVOICE",
        "series": "A",
        "currency": "NIO",
        "customer_name": "Cliente API Snapshot",
        "customer_ref": "CLI-API",
        "customer_party_id": customer_party_id,
        "is_fiscal": False,
        "idempotency_key": idempotency_key,
        "lines": [
            {
                "description": "Servicio API",
                "quantity": "1.0000",
                "unit_price": "100.000000",
                "tax_rate": "0.1500",
            }
        ],
    }


@pytest.mark.django_db
def test_create_billing_draft_keeps_legacy_mode_without_customer_party():
    company, branch = _org_tree(suffix="LEG")
    user = User.objects.create_user(username="bill_party_legacy", password="pass12345")
    request = _request(company=company, branch=branch, user=user)

    result = billing_services.create_draft(
        request=request,
        actor=user,
        doc_type=DocType.INVOICE,
        series="A",
        currency="NIO",
        customer_name="Cliente Legacy",
        customer_ref="CLI-LEG",
        is_fiscal=False,
        lines=[{"description": "Legacy", "quantity": "1", "unit_price": "10", "tax_rate": "0.00"}],
        idempotency_key="idem-bill-legacy",
    )

    doc = BillingDocument.objects.get(id=result.doc_id)
    assert doc.customer_party_id is None
    assert doc.customer_name == "Cliente Legacy"
    assert doc.customer_ref == "CLI-LEG"
    assert PartyRole.objects.count() == 0

    event = OutboxEvent.objects.get(source_module="BILLING", event_type="DocumentDrafted")
    assert event.payload["data"]["customer_party_id"] is None


@pytest.mark.django_db
def test_create_billing_draft_accepts_customer_party_same_company():
    company, branch = _org_tree(suffix="OK")
    user = User.objects.create_user(username="bill_party_ok", password="pass12345")
    party = _party(company=company, suffix="OK")
    request = _request(company=company, branch=branch, user=user)

    result = _create_doc(request=request, user=user, customer_party_id=party.id, idempotency_key="idem-bill-party-ok")

    doc = BillingDocument.objects.get(id=result.doc_id)
    assert doc.customer_party_id == party.id
    assert doc.customer_name == "Cliente Snapshot"
    assert doc.customer_ref == "CLI-001"

    event = OutboxEvent.objects.get(source_module="BILLING", event_type="DocumentDrafted")
    assert event.company_id == company.id
    assert event.branch_id == branch.id
    assert event.payload["data"]["customer_party_id"] == party.id


@pytest.mark.django_db
def test_create_billing_draft_rejects_customer_party_from_other_company():
    company_a, branch_a = _org_tree(suffix="A")
    company_b, _branch_b = _org_tree(suffix="B")
    user = User.objects.create_user(username="bill_party_cross", password="pass12345")
    foreign_party = _party(company=company_b, suffix="CROSS")
    request = _request(company=company_a, branch=branch_a, user=user)

    with pytest.raises(billing_services.BillingError):
        _create_doc(
            request=request,
            user=user,
            customer_party_id=foreign_party.id,
            idempotency_key="idem-bill-cross",
        )

    assert BillingDocument.objects.count() == 0
    assert OutboxEvent.objects.count() == 0
    assert PartyRole.objects.filter(party=foreign_party, role=PartyRole.Role.CUSTOMER).count() == 0


@pytest.mark.django_db
def test_billing_document_model_rejects_customer_party_company_mismatch():
    company_a, branch_a = _org_tree(suffix="MODELA")
    company_b, _branch_b = _org_tree(suffix="MODELB")
    party_b = _party(company=company_b, suffix="MODEL-X")

    doc = BillingDocument(
        company=company_a,
        branch=branch_a,
        doc_type=DocType.INVOICE,
        customer_party=party_b,
        subtotal=Decimal("1.00"),
        total=Decimal("1.00"),
    )

    with pytest.raises(ValidationError):
        doc.full_clean()


@pytest.mark.django_db
def test_create_billing_draft_ensures_customer_party_role_without_duplicates():
    company, branch = _org_tree(suffix="ROLE")
    user = User.objects.create_user(username="bill_party_role", password="pass12345")
    party = _party(company=company, suffix="ROLE")
    request = _request(company=company, branch=branch, user=user)

    _create_doc(request=request, user=user, customer_party_id=party.id, idempotency_key="idem-bill-role-1")
    _create_doc(request=request, user=user, customer_party_id=party.id, idempotency_key="idem-bill-role-2", series="B")

    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.CUSTOMER, is_active=True).count() == 1


@pytest.mark.django_db
def test_create_billing_draft_reuses_existing_customer_party_role():
    company, branch = _org_tree(suffix="EXISTING")
    user = User.objects.create_user(username="bill_party_existing_role", password="pass12345")
    party = _party(company=company, suffix="EXISTING")
    PartyRole.objects.create(party=party, role=PartyRole.Role.CUSTOMER)
    request = _request(company=company, branch=branch, user=user)

    _create_doc(request=request, user=user, customer_party_id=party.id, idempotency_key="idem-bill-existing-role")

    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.CUSTOMER, is_active=True).count() == 1


@pytest.mark.django_db
def test_create_billing_draft_rolls_back_when_customer_role_assignment_fails(monkeypatch):
    company, branch = _org_tree(suffix="ROLLBACK")
    user = User.objects.create_user(username="bill_party_rollback", password="pass12345")
    party = _party(company=company, suffix="ROLLBACK")
    request = _request(company=company, branch=branch, user=user)

    def fail_assign_party_role(**_kwargs):
        raise RuntimeError("role audit failed")

    monkeypatch.setattr(billing_services, "assign_party_role", fail_assign_party_role)

    with pytest.raises(RuntimeError):
        _create_doc(
            request=request,
            user=user,
            customer_party_id=party.id,
            idempotency_key="idem-bill-rollback",
        )

    assert BillingDocument.objects.count() == 0
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.CUSTOMER).count() == 0
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db
def test_create_billing_draft_idempotency_with_customer_party_keeps_single_doc_and_role():
    company, branch = _org_tree(suffix="IDEM")
    user = User.objects.create_user(username="bill_party_idem", password="pass12345")
    party = _party(company=company, suffix="IDEM")
    request = _request(company=company, branch=branch, user=user)

    first = _create_doc(request=request, user=user, customer_party_id=party.id, idempotency_key="idem-bill-same")
    second = _create_doc(request=request, user=user, customer_party_id=party.id, idempotency_key="idem-bill-same")

    assert first.doc_id == second.doc_id
    assert BillingDocument.objects.count() == 1
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.CUSTOMER, is_active=True).count() == 1
    assert OutboxEvent.objects.filter(source_module="BILLING", event_type="DocumentDrafted").count() == 1


@pytest.mark.django_db
def test_issue_and_void_include_customer_party_id_in_billing_outbox():
    company, branch = _org_tree(suffix="OUTBOX")
    user = User.objects.create_user(username="bill_party_outbox", password="pass12345")
    party = _party(company=company, suffix="OUTBOX")
    request = _request(company=company, branch=branch, user=user)
    result = _create_doc(request=request, user=user, customer_party_id=party.id, idempotency_key="idem-bill-outbox")

    billing_services.issue_doc(request=request, actor=user, doc_id=result.doc_id)
    billing_services.void_doc(request=request, actor=user, doc_id=result.doc_id, reason="VOID_TEST")

    outbox_by_type = {
        event.event_type: event.payload["data"]["customer_party_id"]
        for event in OutboxEvent.objects.filter(
            source_module="BILLING",
            event_type__in=["DocumentDrafted", "DocumentIssued", "DocumentVoided", "BILLING.FiscalDocumentIssued"],
        )
    }
    assert outbox_by_type["DocumentDrafted"] == party.id
    assert outbox_by_type["DocumentIssued"] == party.id
    assert outbox_by_type["DocumentVoided"] == party.id
    assert outbox_by_type["BILLING.FiscalDocumentIssued"] == party.id


@pytest.mark.django_db
def test_billing_api_accepts_customer_party_and_detail_list_return_safe_party_fields():
    company, branch = _org_tree(suffix="API")
    party = _party(company=company, suffix="API")
    client, _user = _client(company=company, branch=branch)

    created = client.post(
        "/api/billing/docs/",
        _billing_payload(customer_party_id=party.id, idempotency_key="idem-bill-api"),
        format="json",
    )
    assert created.status_code == 201

    detail = client.get(f"/api/billing/docs/{created.data['id']}/")
    assert detail.status_code == 200
    assert detail.data["customer_party_id"] == party.id
    assert detail.data["customer_party_display_name"] == party.display_name
    assert detail.data["customer_name"] == "Cliente API Snapshot"
    assert detail.data["customer_ref"] == "CLI-API"
    assert "customer_tax_id" not in detail.data
    assert "customer_national_id" not in detail.data

    listed = client.get("/api/billing/docs/")
    assert listed.status_code == 200
    row = listed.data["results"][0]
    assert row["customer_party_id"] == party.id
    assert row["customer_party_display_name"] == party.display_name
    assert "customer_tax_id" not in row
    assert "customer_national_id" not in row


@pytest.mark.django_db
def test_billing_api_rejects_cross_company_customer_party():
    company_a, branch_a = _org_tree(suffix="APIA")
    company_b, _branch_b = _org_tree(suffix="APIB")
    foreign_party = _party(company=company_b, suffix="API-X")
    client, _user = _client(company=company_a, branch=branch_a)

    created = client.post(
        "/api/billing/docs/",
        _billing_payload(customer_party_id=foreign_party.id, idempotency_key="idem-bill-api-cross"),
        format="json",
    )

    assert created.status_code == 400
    assert BillingDocument.objects.count() == 0
    assert PartyRole.objects.filter(party=foreign_party, role=PartyRole.Role.CUSTOMER).count() == 0
