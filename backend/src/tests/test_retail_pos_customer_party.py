from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.accounting.models import EconomicEvent, JournalDraft
from apps.kernels.facturacion.models import BillingDocument
from apps.kernels.payments.models import CashMovement, PaymentIntent
from apps.modulos.estacion_servicios import services as fuel_services
from apps.modulos.estacion_servicios.models import FuelSale
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.parties.models import Party, PartyRole
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.retail_pos.models import PosTicket, PosTicketStatus

User = get_user_model()


def _mk_org(*, suffix: str = "") -> tuple[OrgUnit, OrgUnit]:
    token = suffix or uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"POS Holding {token}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"POS Company {token}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"POS Branch {token}", parent=company)
    return company, branch


def _party(*, company: OrgUnit, suffix: str = "") -> Party:
    token = suffix or uuid.uuid4().hex[:8]
    return Party.objects.create(
        company=company,
        party_type=Party.PartyType.JURIDICAL,
        display_name=f"Cliente POS {token}",
        tax_id=f"RUC-POS-{token}",
        national_id=f"NAT-POS-{token}",
    )


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email=f"{username}@retail-pos.test", password="pass12345")

    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        if not perm.is_active:
            perm.is_active = True
            perm.save(update_fields=["is_active"])
        RolePermission.objects.get_or_create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient(raise_request_exception=True)
    login = client.post(
        "/api/auth/login/",
        {"username": username, "password": "pass12345"},
        format="json",
        HTTP_X_AUTH_TRANSPORT="header",
    )
    assert login.status_code == 200
    access = login.data.get("access") if isinstance(login.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    client.defaults["HTTP_X_AUTH_TRANSPORT"] = "header"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _checkout_line_payload(*, volume: str = "4.0000", unit_price: str = "39.0000") -> dict[str, object]:
    return {
        "line": {
            "product": "DIESEL",
            "volume": volume,
            "volume_uom": "LITER",
            "unit_price_entered": unit_price,
            "unit_price_uom": "PER_LITER",
        }
    }


def _open_shift_session_ticket(*, client: APIClient, party: Party | None = None, payment_method: str = "CASH") -> int:
    shift = client.post("/api/fuel/shifts/open/", {"note": "turno-pos-party"}, format="json")
    assert shift.status_code == 201

    session = client.post(
        "/api/retail/pos/sessions/open/",
        {"opening_amount": "25.00", "note": "apertura-pos-party"},
        format="json",
    )
    assert session.status_code == 201

    payload = {
        "shift_id": int(shift.data["id"]),
        "idempotency_key": f"ticket-party-{uuid.uuid4().hex[:8]}",
        "external_ref": "POS-PARTY-001",
        "customer_name": "Cliente Snapshot POS",
        "customer_ref": "CLI-POS-001",
        "payment_method": payment_method,
    }
    if party is not None:
        payload["customer_party_id"] = int(party.id)
    ticket = client.post("/api/retail/pos/tickets/", payload, format="json")
    assert ticket.status_code == 201, ticket.content.decode()
    if party is not None:
        assert ticket.data["customer_party_id"] == party.id
        assert ticket.data["customer_party_display_name"] == party.display_name
        assert "customer_tax_id" not in ticket.data
        assert "customer_national_id" not in ticket.data
    return int(ticket.data["id"])


@pytest.mark.django_db
def test_pos_open_with_customer_party_persists_and_checkout_propagates_to_fuel_billing() -> None:
    company, branch = _mk_org(suffix="OK")
    party = _party(company=company, suffix="OK")
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "retail.pos.session.open",
            "retail.pos.ticket.open",
            "retail.pos.ticket.read",
            "retail.pos.ticket.checkout",
        ],
    )
    ticket_id = _open_shift_session_ticket(client=client, party=party)

    ticket = PosTicket.objects.get(id=ticket_id)
    assert ticket.customer_party_id == party.id
    assert ticket.customer_name == "Cliente Snapshot POS"
    assert ticket.customer_ref == "CLI-POS-001"

    opened = OutboxEvent.objects.get(source_module="POS", event_type="POSTicketOpened")
    assert opened.payload["data"]["customer_party_id"] == party.id

    checkout = client.post(
        f"/api/retail/pos/tickets/{ticket_id}/checkout/",
        _checkout_line_payload(volume="5.0000", unit_price="41.0000"),
        format="json",
    )

    assert checkout.status_code == 200, checkout.content.decode()
    assert checkout.data["status"] == "CLOSED"
    assert checkout.data["customer_party_id"] == party.id
    assert checkout.data["customer_party_display_name"] == party.display_name
    assert checkout.data["customer_name"] == "Cliente Snapshot POS"
    assert checkout.data["customer_ref"] == "CLI-POS-001"

    sale = FuelSale.objects.get(id=int(checkout.data["sale_id"]))
    assert sale.billing_doc_id is not None
    doc = BillingDocument.objects.get(id=sale.billing_doc_id)
    assert sale.customer_party_id == party.id
    assert doc.customer_party_id == party.id
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.CUSTOMER, is_active=True).count() == 1

    assert PaymentIntent.objects.filter(payment_id=checkout.data["payment_intent_id"]).count() == 1
    assert CashMovement.objects.filter(reference=f"pos-ticket:{ticket_id}").count() == 1
    assert EconomicEvent.objects.filter(source_module__in=["POS", "FUEL"]).count() == 0
    assert JournalDraft.objects.filter(economic_event__source_module__in=["POS", "FUEL"]).count() == 0

    closed = OutboxEvent.objects.get(source_module="POS", event_type="POSTicketClosed")
    assert closed.payload["data"]["customer_party_id"] == party.id


@pytest.mark.django_db
def test_pos_open_rejects_cross_company_customer_party_without_checkout_side_effects() -> None:
    company, branch = _mk_org(suffix="A")
    foreign_company, _foreign_branch = _mk_org(suffix="B")
    foreign_party = _party(company=foreign_company, suffix="FOREIGN")
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "retail.pos.session.open",
            "retail.pos.ticket.open",
            "retail.pos.ticket.read",
            "retail.pos.ticket.checkout",
        ],
    )
    shift = client.post("/api/fuel/shifts/open/", {"note": "turno-pos-cross-company"}, format="json")
    assert shift.status_code == 201
    session = client.post(
        "/api/retail/pos/sessions/open/",
        {"opening_amount": "10.00", "note": "apertura-pos-cross-company"},
        format="json",
    )
    assert session.status_code == 201

    response = client.post(
        "/api/retail/pos/tickets/",
        {
            "shift_id": int(shift.data["id"]),
            "idempotency_key": "ticket-party-cross-company",
            "customer_party_id": int(foreign_party.id),
            "payment_method": "CASH",
        },
        format="json",
    )

    assert response.status_code == 400
    assert PosTicket.objects.count() == 0
    assert FuelSale.objects.count() == 0
    assert PaymentIntent.objects.count() == 0
    assert CashMovement.objects.count() == 0
    assert not PartyRole.objects.filter(party=foreign_party, role=PartyRole.Role.CUSTOMER).exists()


@pytest.mark.django_db
def test_pos_compensation_retry_reuses_persisted_customer_party(monkeypatch) -> None:
    company, branch = _mk_org(suffix="RETRY")
    party = _party(company=company, suffix="RETRY")
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "retail.pos.session.open",
            "retail.pos.ticket.open",
            "retail.pos.ticket.read",
            "retail.pos.ticket.checkout",
        ],
    )
    ticket_id = _open_shift_session_ticket(client=client, party=party)

    attempts = {"count": 0}
    real_create_sale = fuel_services.create_sale

    def flaky_create_sale(*args, **kwargs):
        attempts["count"] += 1
        assert kwargs["customer_party_id"] == party.id
        if attempts["count"] == 1:
            raise RuntimeError("forced-party-create-sale-failure")
        return real_create_sale(*args, **kwargs)

    monkeypatch.setattr("apps.modulos.retail_pos.services.create_sale", flaky_create_sale)

    checkout = client.post(
        f"/api/retail/pos/tickets/{ticket_id}/checkout/",
        _checkout_line_payload(volume="3.0000", unit_price="40.0000"),
        format="json",
    )
    assert checkout.status_code == 409

    pending = PosTicket.objects.get(id=ticket_id)
    assert pending.status == PosTicketStatus.CHECKOUT_PENDING
    assert pending.compensation_pending is True
    assert pending.customer_party_id == party.id
    assert "forced-party-create-sale-failure" in pending.compensation_last_error

    retry = client.post(
        f"/api/retail/pos/tickets/{ticket_id}/compensate/retry/",
        {"reason": "manual-party-retry"},
        format="json",
    )
    assert retry.status_code == 200, retry.content.decode()
    assert retry.data["status"] == "CLOSED"
    assert retry.data["customer_party_id"] == party.id

    recovered = PosTicket.objects.get(id=ticket_id)
    assert recovered.sale_id is not None
    sale = FuelSale.objects.get(id=recovered.sale_id)
    assert sale.billing_doc_id is not None
    doc = BillingDocument.objects.get(id=sale.billing_doc_id)
    assert recovered.customer_party_id == party.id
    assert sale.customer_party_id == party.id
    assert doc.customer_party_id == party.id
    assert attempts["count"] == 2


@pytest.mark.django_db
def test_pos_transfer_checkout_with_customer_party_does_not_create_cash_movement() -> None:
    company, branch = _mk_org(suffix="TRANSFER")
    party = _party(company=company, suffix="TRANSFER")
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "retail.pos.session.open",
            "retail.pos.ticket.open",
            "retail.pos.ticket.read",
            "retail.pos.ticket.checkout",
        ],
    )
    ticket_id = _open_shift_session_ticket(client=client, party=party, payment_method="TRANSFER")

    checkout = client.post(
        f"/api/retail/pos/tickets/{ticket_id}/checkout/",
        _checkout_line_payload(volume="4.0000", unit_price="40.0000"),
        format="json",
    )

    assert checkout.status_code == 200, checkout.content.decode()
    assert checkout.data["status"] == "CLOSED"
    assert checkout.data["customer_party_id"] == party.id
    assert checkout.data["cash_movement_id"] is None
    assert CashMovement.objects.filter(reference=f"pos-ticket:{ticket_id}").count() == 0
    sale = FuelSale.objects.get(id=int(checkout.data["sale_id"]))
    assert sale.customer_party_id == party.id
    billing_doc = sale.billing_doc
    assert billing_doc is not None
    assert billing_doc.customer_party_id == party.id
