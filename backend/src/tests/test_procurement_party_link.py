from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.kernels.accounting.models import EconomicEvent, JournalDraft
from apps.modulos.cec.models import CloseRun
from apps.modulos.compras.models import PurchaseDocType, PurchaseDocument
from apps.modulos.compras import services as procurement_services
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.parties.models import Party, PartyRole
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _org_tree(*, suffix: str = ""):
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Holding{suffix}",
        code=f"H{suffix}",
        is_active=True,
    )
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name=f"Company{suffix}",
        code=f"C{suffix}",
        is_active=True,
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Branch{suffix}",
        code=f"B{suffix}",
        is_active=True,
    )
    return company, branch


def _request(*, company, branch, user):
    return SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        request_id="req-proc-party-link",
        headers={},
        META={},
        path="/api/procurement/docs/",
        method="POST",
    )


def _party(*, company, suffix: str = "") -> Party:
    return Party.objects.create(
        company=company,
        party_type=Party.PartyType.JURIDICAL,
        display_name=f"Proveedor Party{suffix}",
        tax_id=f"RUC-PRV-{suffix or uuid.uuid4().hex[:8]}",
    )


def _create_purchase(*, request, user, supplier_party_id=None, idempotency_key="idem-proc-party"):
    return procurement_services.create_purchase_draft(
        request=request,
        actor=user,
        doc_type=PurchaseDocType.SUPPLIER_INVOICE,
        series="P",
        currency="NIO",
        supplier_name="Proveedor Legacy",
        supplier_ref="SUP-001",
        external_ref="EXT-001",
        subtotal=Decimal("100.00"),
        tax_total=Decimal("15.00"),
        total=Decimal("115.00"),
        supplier_party_id=supplier_party_id,
        notes="draft with party",
        metadata_json={"source": "test"},
        idempotency_key=idempotency_key,
    )


def _procurement_perms() -> list[str]:
    return ["procurement.doc.create", "procurement.doc.read", "procurement.doc.post", "procurement.doc.void"]


def _client(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str] | None = None) -> tuple[APIClient, Any]:
    username = f"proc_party_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"proc_party_role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes or _procurement_perms():
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


@pytest.mark.django_db
def test_create_purchase_draft_accepts_supplier_party_same_company():
    company, branch = _org_tree(suffix="A")
    user = User.objects.create_user(username="proc_party_ok", password="pass12345")
    party = _party(company=company, suffix="001")
    request = _request(company=company, branch=branch, user=user)

    result = _create_purchase(request=request, user=user, supplier_party_id=party.id, idempotency_key="idem-proc-party-1")

    doc = PurchaseDocument.objects.get(id=result.doc_id)
    assert doc.supplier_party_id == party.id
    assert doc.supplier_name == "Proveedor Legacy"
    assert doc.supplier_ref == "SUP-001"

    event = OutboxEvent.objects.get(source_module="PROCUREMENT", event_type="ProcurementDocumentDrafted")
    assert event.company_id == company.id
    assert event.branch_id == branch.id
    assert event.payload["data"]["supplier_party_id"] == party.id
    assert event.payload["data"]["supplier_ref"] == "SUP-001"


@pytest.mark.django_db
def test_create_purchase_draft_rejects_supplier_party_from_other_company():
    company_a, branch_a = _org_tree(suffix="A")
    company_b, _branch_b = _org_tree(suffix="B")
    user = User.objects.create_user(username="proc_party_cross", password="pass12345")
    foreign_party = _party(company=company_b, suffix="EXT")
    request = _request(company=company_a, branch=branch_a, user=user)

    with pytest.raises(procurement_services.ProcurementError):
        _create_purchase(
            request=request,
            user=user,
            supplier_party_id=foreign_party.id,
            idempotency_key="idem-proc-party-2",
        )

    assert PurchaseDocument.objects.count() == 0
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db
def test_purchase_document_model_rejects_supplier_party_company_mismatch():
    company_a, branch_a = _org_tree(suffix="A")
    company_b, _branch_b = _org_tree(suffix="B")
    party_b = _party(company=company_b, suffix="MODEL-X")

    doc = PurchaseDocument(
        company=company_a,
        branch=branch_a,
        doc_type=PurchaseDocType.SUPPLIER_INVOICE,
        supplier_party=party_b,
        subtotal=Decimal("1.00"),
        total=Decimal("1.00"),
    )

    with pytest.raises(ValidationError):
        doc.full_clean()


@pytest.mark.django_db
def test_create_purchase_draft_keeps_legacy_mode_without_supplier_party():
    company, branch = _org_tree(suffix="C")
    user = User.objects.create_user(username="proc_party_legacy", password="pass12345")
    request = _request(company=company, branch=branch, user=user)

    result = procurement_services.create_purchase_draft(
        request=request,
        actor=user,
        doc_type=PurchaseDocType.SUPPLIER_INVOICE,
        series="P",
        currency="NIO",
        supplier_name="Proveedor Legacy Only",
        supplier_ref="SUP-LEG-001",
        external_ref="EXT-LEG-001",
        subtotal=Decimal("80.00"),
        tax_total=Decimal("12.00"),
        total=Decimal("92.00"),
        idempotency_key="idem-proc-party-3",
    )

    doc = PurchaseDocument.objects.get(id=result.doc_id)
    assert doc.supplier_party_id is None
    assert doc.supplier_name == "Proveedor Legacy Only"
    assert PartyRole.objects.count() == 0

    event = OutboxEvent.objects.get(source_module="PROCUREMENT", event_type="ProcurementDocumentDrafted")
    assert event.payload["data"]["supplier_party_id"] is None


@pytest.mark.django_db
def test_create_purchase_draft_ensures_supplier_party_role_without_duplicates():
    company, branch = _org_tree(suffix="D")
    user = User.objects.create_user(username="proc_party_role", password="pass12345")
    party = _party(company=company, suffix="ROLE")
    request = _request(company=company, branch=branch, user=user)

    first = _create_purchase(
        request=request,
        user=user,
        supplier_party_id=party.id,
        idempotency_key="idem-proc-party-role-1",
    )
    procurement_services.post_purchase_document(request=request, actor=user, doc_id=first.doc_id)
    _create_purchase(request=request, user=user, supplier_party_id=party.id, idempotency_key="idem-proc-party-role-2")

    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.SUPPLIER, is_active=True).count() == 1


@pytest.mark.django_db
def test_create_purchase_draft_reuses_existing_supplier_party_role():
    company, branch = _org_tree(suffix="E")
    user = User.objects.create_user(username="proc_party_existing_role", password="pass12345")
    party = _party(company=company, suffix="EXISTING")
    PartyRole.objects.create(party=party, role=PartyRole.Role.SUPPLIER)
    request = _request(company=company, branch=branch, user=user)

    _create_purchase(request=request, user=user, supplier_party_id=party.id, idempotency_key="idem-proc-party-existing")

    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.SUPPLIER, is_active=True).count() == 1


@pytest.mark.django_db
def test_create_purchase_draft_rolls_back_when_supplier_role_assignment_fails(monkeypatch):
    company, branch = _org_tree(suffix="F")
    user = User.objects.create_user(username="proc_party_rollback", password="pass12345")
    party = _party(company=company, suffix="ROLLBACK")
    request = _request(company=company, branch=branch, user=user)

    def fail_assign_party_role(**_kwargs):
        raise RuntimeError("role audit failed")

    monkeypatch.setattr(procurement_services, "assign_party_role", fail_assign_party_role)

    with pytest.raises(RuntimeError):
        _create_purchase(request=request, user=user, supplier_party_id=party.id, idempotency_key="idem-proc-party-rollback")

    assert PurchaseDocument.objects.count() == 0
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.SUPPLIER).count() == 0
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db
def test_create_purchase_draft_idempotency_with_supplier_party_keeps_single_doc_and_role():
    company, branch = _org_tree(suffix="G")
    user = User.objects.create_user(username="proc_party_idem", password="pass12345")
    party = _party(company=company, suffix="IDEM")
    request = _request(company=company, branch=branch, user=user)

    first = _create_purchase(request=request, user=user, supplier_party_id=party.id, idempotency_key="idem-proc-party-same")
    second = _create_purchase(request=request, user=user, supplier_party_id=party.id, idempotency_key="idem-proc-party-same")

    assert first.doc_id == second.doc_id
    assert PurchaseDocument.objects.count() == 1
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.SUPPLIER, is_active=True).count() == 1
    assert OutboxEvent.objects.filter(source_module="PROCUREMENT", event_type="ProcurementDocumentDrafted").count() == 1


@pytest.mark.django_db
def test_post_and_void_include_supplier_party_id_without_creating_financial_domains():
    company, branch = _org_tree(suffix="H")
    user = User.objects.create_user(username="proc_party_post_void", password="pass12345")
    party = _party(company=company, suffix="POST")
    request = _request(company=company, branch=branch, user=user)
    result = _create_purchase(request=request, user=user, supplier_party_id=party.id, idempotency_key="idem-proc-party-post")

    posted = procurement_services.post_purchase_document(request=request, actor=user, doc_id=result.doc_id)
    assert posted["status"] == "POSTED"
    voided = procurement_services.void_purchase_document(request=request, actor=user, doc_id=result.doc_id, reason="VOID_TEST")
    assert voided["status"] == "VOIDED"

    outbox_by_type = {
        event.event_type: event.payload["data"]["supplier_party_id"]
        for event in OutboxEvent.objects.filter(source_module="PROCUREMENT")
    }
    assert outbox_by_type["ProcurementDocumentDrafted"] == party.id
    assert outbox_by_type["ProcurementDocumentPosted"] == party.id
    assert outbox_by_type["ProcurementDocumentVoided"] == party.id

    assert EconomicEvent.objects.count() == 0
    assert JournalDraft.objects.count() == 0
    assert CloseRun.objects.count() == 0


@pytest.mark.django_db
def test_procurement_api_accepts_supplier_party_and_detail_returns_safe_party_fields():
    company, branch = _org_tree(suffix="API")
    party = _party(company=company, suffix="API")
    client, _user = _client(company=company, branch=branch)

    created = client.post(
        "/api/procurement/docs/",
        {
            "doc_type": "SUPPLIER_INVOICE",
            "series": "P",
            "currency": "NIO",
            "supplier_name": "Proveedor Snapshot",
            "supplier_ref": "SUP-API",
            "external_ref": "EXT-API",
            "subtotal": "100.00",
            "tax_total": "15.00",
            "total": "115.00",
            "supplier_party_id": party.id,
            "idempotency_key": "idem-proc-party-api",
        },
        format="json",
    )
    assert created.status_code == 201

    detail = client.get(f"/api/procurement/docs/{created.data['id']}/")
    assert detail.status_code == 200
    assert detail.data["supplier_party_id"] == party.id
    assert detail.data["supplier_party_display_name"] == party.display_name
    assert detail.data["supplier_name"] == "Proveedor Snapshot"
    assert detail.data["supplier_ref"] == "SUP-API"
    assert "supplier_tax_id" not in detail.data
    assert "supplier_national_id" not in detail.data


@pytest.mark.django_db
def test_procurement_api_rejects_cross_company_supplier_party():
    company_a, branch_a = _org_tree(suffix="APIA")
    company_b, _branch_b = _org_tree(suffix="APIB")
    foreign_party = _party(company=company_b, suffix="API-X")
    client, _user = _client(company=company_a, branch=branch_a)

    created = client.post(
        "/api/procurement/docs/",
        {
            "doc_type": "SUPPLIER_INVOICE",
            "series": "P",
            "currency": "NIO",
            "supplier_name": "Proveedor Cross",
            "supplier_ref": "SUP-CROSS",
            "external_ref": "EXT-CROSS",
            "subtotal": "50.00",
            "tax_total": "7.50",
            "total": "57.50",
            "supplier_party_id": foreign_party.id,
            "idempotency_key": "idem-proc-party-api-cross",
        },
        format="json",
    )

    assert created.status_code == 400
    assert PurchaseDocument.objects.count() == 0
    assert PartyRole.objects.filter(party=foreign_party, role=PartyRole.Role.SUPPLIER).count() == 0
