from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.kernels.accounting.models import EconomicEvent, JournalDraft
from apps.kernels.facturacion import services as billing_services
from apps.kernels.facturacion.models import BillingDocument
from apps.kernels.inventarios.models import StockMovement
from apps.modulos.estacion_servicios import services as fuel_services
from apps.modulos.estacion_servicios.models import (
    FuelDispense,
    FuelPaymentMethod,
    FuelPriceUOM,
    FuelProduct,
    FuelSale,
    FuelSaleType,
    FuelShift,
    FuelVolumeUOM,
)
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.parties.models import Party, PartyRole
from tests.helpers.operational_auth import create_operational_api_actor as _client_with_perms

User = get_user_model()


def _mk_org(*, suffix: str = "") -> tuple[OrgUnit, OrgUnit]:
    token = suffix or uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"Fuel Holding {token}", code=f"FH{token}")
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        name=f"Fuel Company {token}",
        code=f"FC{token}",
        parent=holding,
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        name=f"Fuel Branch {token}",
        code=f"FB{token}",
        parent=company,
    )
    return company, branch


def _party(*, company: OrgUnit, suffix: str = "") -> Party:
    token = suffix or uuid.uuid4().hex[:8]
    return Party.objects.create(
        company=company,
        party_type=Party.PartyType.JURIDICAL,
        display_name=f"Cliente Fuel {token}",
        tax_id=f"RUC-FUEL-{token}",
        national_id=f"NAT-FUEL-{token}",
    )


def _client(*, company: OrgUnit, branch: OrgUnit):
    return _client_with_perms(
        company=company,
        branch=branch,
        email_prefix="fuel_party",
        perm_codes=[
            "fuel.shift.open",
            "fuel.dispense.create",
            "fuel.sale.create",
            "fuel.sale.read",
            "fuel.sale.void",
        ],
    )


def _open_shift_and_dispense(*, client) -> tuple[int, int]:
    shift = client.post("/api/fuel/shifts/open/", {"note": "turno-party"}, format="json")
    assert shift.status_code == 201

    dispense = client.post(
        "/api/fuel/dispenses/",
        {
            "shift_id": shift.data["id"],
            "product": FuelProduct.DIESEL,
            "liters": "8.0000",
            "unit_price": "42.5000",
        },
        format="json",
    )
    assert dispense.status_code == 201
    return int(shift.data["id"]), int(dispense.data["id"])


def _sale_payload(*, shift_id: int, dispense_id: int, customer_party_id=None, idempotency_key: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "shift_id": shift_id,
        "dispense_id": dispense_id,
        "sale_type": FuelSaleType.PUBLIC,
        "payment_method": FuelPaymentMethod.CASH,
        "customer_name": "Cliente Snapshot Fuel",
        "customer_ref": "CLI-FUEL-001",
    }
    if customer_party_id is not None:
        payload["customer_party_id"] = customer_party_id
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return payload


def _request(*, company: OrgUnit, branch: OrgUnit, user):
    return SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        request_id=f"req-fuel-customer-party-{uuid.uuid4().hex[:8]}",
        headers={},
        META={},
        path="/api/fuel/sales/",
        method="POST",
        data={},
    )


def _raw_shift_dispense(*, company: OrgUnit, branch: OrgUnit, user) -> tuple[FuelShift, FuelDispense]:
    shift = FuelShift.objects.create(company=company, branch=branch, opened_by=user)
    dispense = FuelDispense.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        recorded_by=user,
        product=FuelProduct.DIESEL,
        liters=Decimal("8.0000"),
        volume_entered=Decimal("8.0000"),
        volume_uom=FuelVolumeUOM.LITER,
        unit_price=Decimal("42.5000"),
        unit_price_entered=Decimal("42.5000"),
        unit_price_uom=FuelPriceUOM.PER_LITER,
        amount=Decimal("340.00"),
        amount_canonical=Decimal("340.00"),
    )
    return shift, dispense


@pytest.mark.django_db
def test_fuel_sale_legacy_without_customer_party_still_works() -> None:
    company, branch = _mk_org(suffix="LEG")
    client, _user = _client(company=company, branch=branch)
    shift_id, dispense_id = _open_shift_and_dispense(client=client)

    response = client.post(
        "/api/fuel/sales/",
        _sale_payload(shift_id=shift_id, dispense_id=dispense_id),
        format="json",
    )

    assert response.status_code == 201
    assert response.data["customer_party_id"] is None
    assert response.data["customer_party_display_name"] == ""

    sale = FuelSale.objects.get(id=int(response.data["id"]))
    doc = BillingDocument.objects.get(id=int(response.data["billing_doc_id"]))
    assert sale.customer_party_id is None
    assert doc.customer_party_id is None
    assert sale.customer_name == "Cliente Snapshot Fuel"
    assert sale.customer_ref == "CLI-FUEL-001"


@pytest.mark.django_db
def test_fuel_sale_with_customer_party_propagates_to_billing_and_outbox() -> None:
    company, branch = _mk_org(suffix="OK")
    party = _party(company=company, suffix="OK")
    client, _user = _client(company=company, branch=branch)
    shift_id, dispense_id = _open_shift_and_dispense(client=client)

    response = client.post(
        "/api/fuel/sales/",
        _sale_payload(shift_id=shift_id, dispense_id=dispense_id, customer_party_id=party.id),
        format="json",
    )

    assert response.status_code == 201, response.content.decode()
    assert response.data["customer_party_id"] == party.id
    assert response.data["customer_party_display_name"] == party.display_name
    assert "customer_tax_id" not in response.data
    assert "customer_national_id" not in response.data

    sale = FuelSale.objects.get(id=int(response.data["id"]))
    assert sale.customer_party_id == party.id
    assert sale.customer_name == "Cliente Snapshot Fuel"
    assert sale.customer_ref == "CLI-FUEL-001"

    doc = BillingDocument.objects.get(id=int(response.data["billing_doc_id"]))
    assert doc.customer_party_id == party.id
    assert doc.customer_name == "Cliente Snapshot Fuel"
    assert doc.customer_ref == "CLI-FUEL-001"

    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.CUSTOMER, is_active=True).count() == 1

    fuel_event = OutboxEvent.objects.get(source_module="FUEL", event_type="FuelSaleCreated")
    assert fuel_event.payload["data"]["customer_party_id"] == party.id

    billing_events = {
        event.event_type: event.payload["data"]["customer_party_id"]
        for event in OutboxEvent.objects.filter(
            source_module="BILLING",
            event_type__in=["DocumentDrafted", "DocumentIssued", "BILLING.FiscalDocumentIssued"],
        )
    }
    assert billing_events["DocumentDrafted"] == party.id
    assert billing_events["DocumentIssued"] == party.id
    assert billing_events["BILLING.FiscalDocumentIssued"] == party.id
    assert EconomicEvent.objects.filter(source_module="FUEL").count() == 0
    assert JournalDraft.objects.filter(economic_event__source_module="FUEL").count() == 0


@pytest.mark.django_db
def test_fuel_sale_detail_and_list_return_safe_customer_party_fields() -> None:
    company, branch = _mk_org(suffix="API")
    party = _party(company=company, suffix="API")
    client, _user = _client(company=company, branch=branch)
    shift_id, dispense_id = _open_shift_and_dispense(client=client)

    created = client.post(
        "/api/fuel/sales/",
        _sale_payload(shift_id=shift_id, dispense_id=dispense_id, customer_party_id=party.id),
        format="json",
    )
    assert created.status_code == 201

    detail = client.get(f"/api/fuel/sales/{created.data['id']}/")
    assert detail.status_code == 200
    assert detail.data["customer_party_id"] == party.id
    assert detail.data["customer_party_display_name"] == party.display_name
    assert "customer_tax_id" not in detail.data
    assert "customer_national_id" not in detail.data

    listed = client.get("/api/fuel/sales/")
    assert listed.status_code == 200
    row = listed.data["results"][0]
    assert row["customer_party_id"] == party.id
    assert row["customer_party_display_name"] == party.display_name
    assert "customer_tax_id" not in row
    assert "customer_national_id" not in row


@pytest.mark.django_db
def test_fuel_sale_rejects_cross_company_customer_party_without_partial_sale() -> None:
    company_a, branch_a = _mk_org(suffix="A")
    company_b, _branch_b = _mk_org(suffix="B")
    foreign_party = _party(company=company_b, suffix="FOREIGN")
    client, _user = _client(company=company_a, branch=branch_a)
    shift_id, dispense_id = _open_shift_and_dispense(client=client)
    outbox_before = OutboxEvent.objects.count()

    response = client.post(
        "/api/fuel/sales/",
        _sale_payload(shift_id=shift_id, dispense_id=dispense_id, customer_party_id=foreign_party.id),
        format="json",
    )

    assert response.status_code == 422
    assert FuelSale.objects.count() == 0
    assert BillingDocument.objects.count() == 0
    assert StockMovement.objects.count() == 0
    assert OutboxEvent.objects.count() == outbox_before
    assert PartyRole.objects.filter(party=foreign_party, role=PartyRole.Role.CUSTOMER).count() == 0


@pytest.mark.django_db
def test_fuel_sale_model_rejects_customer_party_company_mismatch() -> None:
    company_a, branch_a = _mk_org(suffix="MODELA")
    company_b, _branch_b = _mk_org(suffix="MODELB")
    user = User.objects.create_user(username="fuel_party_model", password="pass12345")
    shift, dispense = _raw_shift_dispense(company=company_a, branch=branch_a, user=user)
    foreign_party = _party(company=company_b, suffix="MODEL")

    sale = FuelSale(
        company=company_a,
        branch=branch_a,
        shift=shift,
        dispense=dispense,
        sale_type=FuelSaleType.PUBLIC,
        payment_method=FuelPaymentMethod.CASH,
        customer_party=foreign_party,
        total_amount=dispense.amount,
        created_by=user,
    )

    with pytest.raises(ValidationError):
        sale.full_clean()


@pytest.mark.django_db
def test_fuel_sale_idempotency_includes_customer_party() -> None:
    company, branch = _mk_org(suffix="IDEM")
    party_a = _party(company=company, suffix="IDEMA")
    party_b = _party(company=company, suffix="IDEMB")
    client, _user = _client(company=company, branch=branch)
    shift_id, dispense_id = _open_shift_and_dispense(client=client)
    payload = _sale_payload(
        shift_id=shift_id,
        dispense_id=dispense_id,
        customer_party_id=party_a.id,
        idempotency_key="fuel-party-idem",
    )

    first = client.post("/api/fuel/sales/", payload, format="json")
    assert first.status_code == 201

    replay = client.post("/api/fuel/sales/", payload, format="json")
    assert replay.status_code == 200
    assert replay.data["id"] == first.data["id"]
    assert replay.data["customer_party_id"] == party_a.id

    mismatch = client.post(
        "/api/fuel/sales/",
        {**payload, "customer_party_id": party_b.id},
        format="json",
    )
    assert mismatch.status_code == 409
    assert "payload distinto" in str(mismatch.data)
    assert FuelSale.objects.filter(company=company, idempotency_key="fuel-party-idem").count() == 1


@pytest.mark.django_db
def test_fuel_sale_reuses_existing_customer_party_role_without_duplicate() -> None:
    company, branch = _mk_org(suffix="ROLE")
    party = _party(company=company, suffix="ROLE")
    PartyRole.objects.create(party=party, role=PartyRole.Role.CUSTOMER)
    client, _user = _client(company=company, branch=branch)
    shift_id, dispense_id = _open_shift_and_dispense(client=client)

    response = client.post(
        "/api/fuel/sales/",
        _sale_payload(shift_id=shift_id, dispense_id=dispense_id, customer_party_id=party.id),
        format="json",
    )

    assert response.status_code == 201
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.CUSTOMER, is_active=True).count() == 1


@pytest.mark.django_db
def test_fuel_sale_rolls_back_if_billing_customer_role_assignment_fails(monkeypatch) -> None:
    company, branch = _mk_org(suffix="ROLL")
    user = User.objects.create_user(username="fuel_party_rollback", password="pass12345")
    party = _party(company=company, suffix="ROLL")
    shift, dispense = _raw_shift_dispense(company=company, branch=branch, user=user)
    request = _request(company=company, branch=branch, user=user)

    def fail_assign_party_role(**_kwargs):
        raise RuntimeError("role audit failed")

    monkeypatch.setattr(billing_services, "assign_party_role", fail_assign_party_role)

    with pytest.raises(RuntimeError):
        fuel_services.create_sale_with_status(
            request=request,
            company=company,
            branch=branch,
            shift=shift,
            dispense=dispense,
            actor_user=user,
            sale_type=FuelSaleType.PUBLIC,
            payment_method=FuelPaymentMethod.CASH,
            customer_name="Cliente Rollback",
            customer_ref="CLI-ROLL",
            customer_party_id=party.id,
            idempotency_key="fuel-party-rollback",
        )

    assert FuelSale.objects.count() == 0
    assert BillingDocument.objects.count() == 0
    assert StockMovement.objects.filter(source_module="FUEL").count() == 0
    assert OutboxEvent.objects.filter(source_module__in=["FUEL", "BILLING", "INVENTORY"]).count() == 0
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.CUSTOMER).count() == 0
