from __future__ import annotations

from decimal import Decimal
import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.payments.models import CashMovement, CashSession, PaymentIntent
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.ventas_retail.models import RetailBranchConfig, RetailTerminal
from kernels.facturacion.models import BillingDocument, DocStatus
from kernels.inventarios.models import InventoryItem, InventoryTaxProfile, StockBalance, Warehouse

User = get_user_model()


def _error_code(response) -> str:
    data = response.data if isinstance(response.data, dict) else {}
    if "code" in data:
        return str(data.get("code") or "")
    error_raw = data.get("error")
    error = error_raw if isinstance(error_raw, dict) else {}
    details_raw = error.get("details")
    details = details_raw if isinstance(details_raw, dict) else {}
    return str(details.get("code") or error.get("code") or "")


def _error_detail(response) -> str:
    data = response.data if isinstance(response.data, dict) else {}
    if "detail" in data:
        return str(data.get("detail") or "")
    error_raw = data.get("error")
    error = error_raw if isinstance(error_raw, dict) else {}
    details_raw = error.get("details")
    details = details_raw if isinstance(details_raw, dict) else {}
    return str(details.get("detail") or error.get("message") or "")


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"retail_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="retail@test.com", password="pass12345")

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

    client = APIClient()
    login = client.post("/api/backend/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    token = login.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _seed_retail_catalog(*, company: OrgUnit, branch: OrgUnit):
    warehouse = Warehouse.objects.create(company=company, branch=branch, name="Retail Main", code="RTL")
    terminal = RetailTerminal.objects.create(branch=branch, code="POS-01", name="Caja 01")
    tax_profile = InventoryTaxProfile.objects.create(
        company=company,
        code="IVA15",
        name="IVA 15%",
        tax_treatment="GRAVADO",
        rate=Decimal("0.1500"),
    )
    item = InventoryItem.objects.create(
        company=company,
        sku=f"RET-{uuid.uuid4().hex[:6]}",
        name="Producto Retail",
        invoice_name="Producto Retail",
        uom="UNIT",
        uom_base="UNIT",
        uom_purchase="UNIT",
        uom_sale="UNIT",
        item_type="INVENTARIABLE",
        status="ACTIVO",
        sales_enabled=True,
        controls_stock=True,
        allow_returns=True,
        visible_pos=True,
        default_branch=branch,
        default_warehouse=warehouse,
        enabled_branch_ids=[int(branch.id)],
        suggested_price=Decimal("10.000000"),
        min_sale_price=Decimal("8.000000"),
        last_known_cost=Decimal("4.000000"),
        tax_profile=tax_profile,
        tax_treatment="GRAVADO",
    )
    StockBalance.objects.create(
        company=company,
        branch=branch,
        warehouse=warehouse,
        item=item,
        qty_on_hand=Decimal("10.0000"),
        avg_cost=Decimal("4.000000"),
    )
    return warehouse, terminal, item


@pytest.mark.django_db
def test_retail_hold_resume_checkout_and_void_flow():
    company, branch = _mk_org()
    _, terminal, item = _seed_retail_catalog(company=company, branch=branch)
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "retail.pos.use",
            "retail.ticket.create",
            "retail.ticket.update",
            "retail.ticket.hold",
            "retail.ticket.checkout",
            "retail.ticket.void",
            "retail.return.create",
            "retail.catalog.read",
            "retail.sale.read",
            "retail.compensation.retry",
            "payments.intent.read",
            "payments.intent.create",
            "payments.intent.capture",
            "payments.intent.refund",
            "payments.cash_session.read",
            "payments.cash_session.open",
            "payments.cash_session.close",
            "payments.cash_movement.create",
        ],
    )

    open_session = client.post("/api/backend/payments/cash-sessions/open/", {"opening_amount": "0.00"}, format="json")
    assert open_session.status_code == 201
    cash_session_id = int(open_session.data["id"])

    create_ticket = client.post(
        "/api/backend/retail/tickets/",
        {"terminal_id": terminal.id, "cash_session_id": cash_session_id, "customer_name": "Cliente POS"},
        format="json",
    )
    assert create_ticket.status_code == 201
    ticket_id = int(create_ticket.data["id"])

    add_line = client.post(
        f"/api/backend/retail/tickets/{ticket_id}/lines/",
        {"expected_version": create_ticket.data["version"], "item_id": item.id, "qty": "2.0000"},
        format="json",
    )
    assert add_line.status_code == 201
    assert add_line.data["status"] == "OPEN"
    assert add_line.data["total"] == "23.00"

    hold = client.post(
        f"/api/backend/retail/tickets/{ticket_id}/hold/",
        {"expected_version": add_line.data["version"], "reason": "cliente en espera"},
        format="json",
    )
    assert hold.status_code == 201
    hold_id = int(hold.data["id"])

    blocked_line = client.post(
        f"/api/backend/retail/tickets/{ticket_id}/lines/",
        {"expected_version": hold.data["ticket"]["version"], "item_id": item.id, "qty": "1.0000"},
        format="json",
    )
    assert blocked_line.status_code == 400
    assert "Ticket retenido" in str(blocked_line.data)

    resume = client.post(f"/api/backend/retail/holds/{hold_id}/resume/", {}, format="json")
    assert resume.status_code == 200

    preview = client.post(
        f"/api/backend/retail/tickets/{ticket_id}/checkout/preview/",
        {"expected_version": resume.data["ticket"]["version"]},
        format="json",
    )
    assert preview.status_code == 200
    assert preview.data["ok"] is True
    assert preview.data["cash_session"]["id"] == cash_session_id

    commit = client.post(
        f"/api/backend/retail/tickets/{ticket_id}/checkout/commit/",
        {
            "expected_version": resume.data["ticket"]["version"],
            "idempotency_key": f"checkout-{uuid.uuid4().hex[:8]}",
            "cash_received": "25.00",
        },
        format="json",
    )
    assert commit.status_code == 200
    assert commit.data["status"] == "COMPLETED"
    assert commit.data["billing"]["status"] == "ISSUED"
    assert commit.data["payment"]["intent_status"] == "CAPTURED"
    assert len(commit.data["inventory"]["movement_ids"]) == 1

    flow_correlation_id = str(commit.data["correlation_id"])
    ticket_detail = client.get(f"/api/backend/retail/tickets/{ticket_id}/")
    assert ticket_detail.status_code == 200
    assert ticket_detail.data["ticket"]["status"] == "CLOSED"

    void_payload = {
        "expected_version": ticket_detail.data["ticket"]["version"],
        "idempotency_key": f"void-{uuid.uuid4().hex[:8]}",
        "reason": "void test",
    }
    void = client.post(
        f"/api/backend/retail/tickets/{ticket_id}/void/",
        void_payload,
        format="json",
    )
    assert void.status_code == 200
    assert void.data["status"] == "VOIDED"
    assert void.data["idempotency_replayed"] is False

    void_replay = client.post(
        f"/api/backend/retail/tickets/{ticket_id}/void/",
        void_payload,
        format="json",
    )
    assert void_replay.status_code == 200
    assert void_replay.data["idempotency_replayed"] is True

    void_mismatch = client.post(
        f"/api/backend/retail/tickets/{ticket_id}/void/",
        {**void_payload, "reason": "void distinto"},
        format="json",
    )
    assert void_mismatch.status_code == 409
    assert _error_code(void_mismatch) == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"

    billing_doc = BillingDocument.objects.get(id=int(commit.data["billing"]["doc_id"]))
    billing_doc.refresh_from_db()
    assert billing_doc.status == DocStatus.VOIDED

    payment_intent = PaymentIntent.objects.get(payment_id=commit.data["payment"]["payment_id"])
    payment_intent.refresh_from_db()
    assert payment_intent.status == PaymentIntent.Status.REFUNDED

    balance = StockBalance.objects.get(item=item)
    assert balance.qty_on_hand == Decimal("10.0000")

    cash_session = CashSession.objects.get(id=cash_session_id)
    assert cash_session.expected_amount == Decimal("0.00")

    retail_events = set(OutboxEvent.objects.filter(source_module="RETAIL").values_list("event_type", flat=True))
    assert "RetailSaleCompleted" in retail_events
    assert "RetailSaleVoided" in retail_events
    assert OutboxEvent.objects.filter(source_module="BILLING", correlation_id=flow_correlation_id).exists()
    assert OutboxEvent.objects.filter(source_module="INVENTORY", correlation_id=flow_correlation_id).exists()
    assert OutboxEvent.objects.filter(source_module="PAYMENTS", correlation_id=flow_correlation_id).exists()
    assert AuditEvent.objects.filter(module="RETAIL", event_type="RETAIL_SALE_COMPLETED").exists()


@pytest.mark.django_db
def test_retail_checkout_idempotency_replay_and_payload_mismatch_conflict():
    company, branch = _mk_org()
    _, terminal, item = _seed_retail_catalog(company=company, branch=branch)
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "retail.pos.use",
            "retail.ticket.create",
            "retail.ticket.update",
            "retail.ticket.checkout",
            "retail.catalog.read",
            "payments.intent.read",
            "payments.intent.create",
            "payments.intent.capture",
            "payments.intent.refund",
            "payments.cash_session.read",
            "payments.cash_session.open",
            "payments.cash_movement.create",
        ],
    )

    open_session = client.post("/api/backend/payments/cash-sessions/open/", {"opening_amount": "0.00"}, format="json")
    assert open_session.status_code == 201

    ticket = client.post(
        "/api/backend/retail/tickets/",
        {"terminal_id": terminal.id, "cash_session_id": open_session.data["id"], "customer_name": "Cliente"},
        format="json",
    )
    assert ticket.status_code == 201

    line = client.post(
        f"/api/backend/retail/tickets/{ticket.data['id']}/lines/",
        {"expected_version": ticket.data["version"], "item_id": item.id, "qty": "2.0000"},
        format="json",
    )
    assert line.status_code == 201

    idem = f"checkout-fixed-{uuid.uuid4().hex[:8]}"
    payload = {
        "expected_version": line.data["version"],
        "idempotency_key": idem,
        "cash_received": "25.00",
    }
    first = client.post(
        f"/api/backend/retail/tickets/{ticket.data['id']}/checkout/commit/",
        payload,
        format="json",
    )
    assert first.status_code == 200
    assert first.data["idempotency_replayed"] is False

    replay = client.post(
        f"/api/backend/retail/tickets/{ticket.data['id']}/checkout/commit/",
        payload,
        format="json",
    )
    assert replay.status_code == 200
    assert replay.data["idempotency_replayed"] is True
    assert replay.data["sale_id"] == first.data["sale_id"]

    mismatch = client.post(
        f"/api/backend/retail/tickets/{ticket.data['id']}/checkout/commit/",
        {**payload, "cash_received": "30.00"},
        format="json",
    )
    assert mismatch.status_code == 409
    assert _error_code(mismatch) == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"


@pytest.mark.django_db
def test_retail_require_customer_for_fiscal_blocks_preview_and_commit():
    company, branch = _mk_org()
    warehouse, terminal, item = _seed_retail_catalog(company=company, branch=branch)
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "retail.pos.use",
            "retail.ticket.create",
            "retail.ticket.update",
            "retail.ticket.checkout",
            "retail.catalog.read",
            "payments.intent.read",
            "payments.intent.create",
            "payments.intent.capture",
            "payments.intent.refund",
            "payments.cash_session.read",
            "payments.cash_session.open",
            "payments.cash_movement.create",
        ],
    )

    bootstrap = client.get("/api/backend/retail/bootstrap/")
    assert bootstrap.status_code == 200
    cfg = RetailBranchConfig.objects.get(branch=branch)
    cfg.require_customer_for_fiscal = True
    cfg.default_warehouse = warehouse
    cfg.active = True
    cfg.save(update_fields=["require_customer_for_fiscal", "default_warehouse", "active", "updated_at"])

    open_session = client.post("/api/backend/payments/cash-sessions/open/", {"opening_amount": "0.00"}, format="json")
    assert open_session.status_code == 201

    ticket = client.post(
        "/api/backend/retail/tickets/",
        {"terminal_id": terminal.id, "cash_session_id": open_session.data["id"]},
        format="json",
    )
    assert ticket.status_code == 201
    line = client.post(
        f"/api/backend/retail/tickets/{ticket.data['id']}/lines/",
        {"expected_version": ticket.data["version"], "item_id": item.id, "qty": "1.0000"},
        format="json",
    )
    assert line.status_code == 201

    preview = client.post(
        f"/api/backend/retail/tickets/{ticket.data['id']}/checkout/preview/",
        {"expected_version": line.data["version"]},
        format="json",
    )
    assert preview.status_code == 200
    assert preview.data["ok"] is False
    assert any(row.get("code") == "RETAIL_CUSTOMER_REQUIRED" for row in preview.data["blocking_errors"])

    commit = client.post(
        f"/api/backend/retail/tickets/{ticket.data['id']}/checkout/commit/",
        {
            "expected_version": line.data["version"],
            "idempotency_key": f"checkout-{uuid.uuid4().hex[:8]}",
            "cash_received": "20.00",
        },
        format="json",
    )
    assert commit.status_code == 400
    assert _error_code(commit) == "RETAIL_CHECKOUT_PREVIEW_BLOCKED"
    assert "Cliente requerido" in _error_detail(commit)


@pytest.mark.django_db
def test_retail_partial_return_is_idempotent_and_caps_cumulative_qty():
    company, branch = _mk_org()
    _, terminal, item = _seed_retail_catalog(company=company, branch=branch)
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "retail.pos.use",
            "retail.ticket.create",
            "retail.ticket.update",
            "retail.ticket.checkout",
            "retail.return.create",
            "retail.catalog.read",
            "retail.sale.read",
            "payments.intent.read",
            "payments.intent.create",
            "payments.intent.capture",
            "payments.intent.refund",
            "payments.cash_session.read",
            "payments.cash_session.open",
            "payments.cash_movement.create",
        ],
    )

    open_session = client.post("/api/backend/payments/cash-sessions/open/", {"opening_amount": "0.00"}, format="json")
    assert open_session.status_code == 201

    ticket = client.post(
        "/api/backend/retail/tickets/",
        {"terminal_id": terminal.id, "cash_session_id": open_session.data["id"]},
        format="json",
    )
    assert ticket.status_code == 201

    line = client.post(
        f"/api/backend/retail/tickets/{ticket.data['id']}/lines/",
        {"expected_version": ticket.data["version"], "item_id": item.id, "qty": "2.0000"},
        format="json",
    )
    assert line.status_code == 201

    commit = client.post(
        f"/api/backend/retail/tickets/{ticket.data['id']}/checkout/commit/",
        {
            "expected_version": line.data["version"],
            "idempotency_key": f"checkout-{uuid.uuid4().hex[:8]}",
            "cash_received": "23.00",
        },
        format="json",
    )
    assert commit.status_code == 200

    ticket_detail = client.get(f"/api/backend/retail/tickets/{ticket.data['id']}/")
    assert ticket_detail.status_code == 200
    original_line_id = int(ticket_detail.data["ticket"]["lines"][0]["id"])

    return_idem = f"return-{uuid.uuid4().hex[:8]}"
    create_return = client.post(
        "/api/backend/retail/returns/",
        {
            "sale_id": commit.data["sale_id"],
            "reason": "partial return",
            "idempotency_key": return_idem,
            "lines": [{"line_id": original_line_id, "qty": "1.0000"}],
        },
        format="json",
    )
    assert create_return.status_code == 201
    assert create_return.data["refund_amount"] == "11.50"
    return_id = int(create_return.data["id"])

    duplicate_return = client.post(
        "/api/backend/retail/returns/",
        {
            "sale_id": commit.data["sale_id"],
            "reason": "partial return",
            "idempotency_key": return_idem,
            "lines": [{"line_id": original_line_id, "qty": "1.0000"}],
        },
        format="json",
    )
    assert duplicate_return.status_code == 201
    assert int(duplicate_return.data["id"]) == return_id

    over_return = client.post(
        "/api/backend/retail/returns/",
        {
            "sale_id": commit.data["sale_id"],
            "reason": "too much",
            "idempotency_key": f"return-{uuid.uuid4().hex[:8]}",
            "lines": [{"line_id": original_line_id, "qty": "2.0000"}],
        },
        format="json",
    )
    assert over_return.status_code == 400
    assert "Cantidad de devolución inválida" in str(over_return.data)

    balance = StockBalance.objects.get(item=item)
    assert balance.qty_on_hand == Decimal("9.0000")

    payment_intent = PaymentIntent.objects.get(payment_id=commit.data["payment"]["payment_id"])
    payment_intent.refresh_from_db()
    assert payment_intent.status == PaymentIntent.Status.CAPTURED
    assert str((payment_intent.metadata or {}).get("refunded_total")) == "11.50"

    cash_session = CashSession.objects.get(id=int(open_session.data["id"]))
    assert cash_session.expected_amount == Decimal("11.50")

    return_detail = client.get(f"/api/backend/retail/returns/{return_id}/")
    assert return_detail.status_code == 200
    assert return_detail.data["status"] == "COMPLETED"
    assert return_detail.data["ticket"]["ticket_kind"] == "RETURN"


@pytest.mark.django_db
def test_retail_return_uses_current_open_cash_session_and_idempotency_contract():
    company, branch = _mk_org()
    _, terminal, item = _seed_retail_catalog(company=company, branch=branch)
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "retail.pos.use",
            "retail.ticket.create",
            "retail.ticket.update",
            "retail.ticket.checkout",
            "retail.return.create",
            "retail.catalog.read",
            "retail.sale.read",
            "payments.intent.read",
            "payments.intent.create",
            "payments.intent.capture",
            "payments.intent.refund",
            "payments.cash_session.read",
            "payments.cash_session.open",
            "payments.cash_session.close",
            "payments.cash_movement.create",
        ],
    )

    session_1 = client.post("/api/backend/payments/cash-sessions/open/", {"opening_amount": "0.00"}, format="json")
    assert session_1.status_code == 201

    ticket = client.post(
        "/api/backend/retail/tickets/",
        {"terminal_id": terminal.id, "cash_session_id": session_1.data["id"], "customer_name": "Cliente"},
        format="json",
    )
    assert ticket.status_code == 201
    line = client.post(
        f"/api/backend/retail/tickets/{ticket.data['id']}/lines/",
        {"expected_version": ticket.data["version"], "item_id": item.id, "qty": "2.0000"},
        format="json",
    )
    assert line.status_code == 201
    commit = client.post(
        f"/api/backend/retail/tickets/{ticket.data['id']}/checkout/commit/",
        {
            "expected_version": line.data["version"],
            "idempotency_key": f"checkout-{uuid.uuid4().hex[:8]}",
            "cash_received": "23.00",
        },
        format="json",
    )
    assert commit.status_code == 200

    close_1 = client.post(
        f"/api/backend/payments/cash-sessions/{session_1.data['id']}/close/",
        {"counted_amount": "23.00"},
        format="json",
    )
    assert close_1.status_code == 200

    session_2 = client.post("/api/backend/payments/cash-sessions/open/", {"opening_amount": "0.00"}, format="json")
    assert session_2.status_code == 201

    detail = client.get(f"/api/backend/retail/tickets/{ticket.data['id']}/")
    assert detail.status_code == 200
    original_line_id = int(detail.data["ticket"]["lines"][0]["id"])

    idem = f"return-fixed-{uuid.uuid4().hex[:8]}"
    create_return = client.post(
        "/api/backend/retail/returns/",
        {
            "sale_id": commit.data["sale_id"],
            "reason": "retorno caja nueva",
            "idempotency_key": idem,
            "lines": [{"line_id": original_line_id, "qty": "1.0000"}],
        },
        format="json",
    )
    assert create_return.status_code == 201
    assert create_return.data["idempotency_replayed"] is False
    refund_movement = CashMovement.objects.get(id=int(create_return.data["refund_cash_movement_id"]))
    assert int(refund_movement.session_id) == int(session_2.data["id"])

    replay = client.post(
        "/api/backend/retail/returns/",
        {
            "sale_id": commit.data["sale_id"],
            "reason": "retorno caja nueva",
            "idempotency_key": idem,
            "lines": [{"line_id": original_line_id, "qty": "1.0000"}],
        },
        format="json",
    )
    assert replay.status_code == 201
    assert replay.data["idempotency_replayed"] is True

    mismatch = client.post(
        "/api/backend/retail/returns/",
        {
            "sale_id": commit.data["sale_id"],
            "reason": "retorno distinto",
            "idempotency_key": idem,
            "lines": [{"line_id": original_line_id, "qty": "0.5000"}],
        },
        format="json",
    )
    assert mismatch.status_code == 409
    assert _error_code(mismatch) == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"


@pytest.mark.django_db
def test_payments_capture_and_refund_endpoints_emit_events():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "payments.intent.read",
            "payments.intent.create",
            "payments.intent.capture",
            "payments.intent.refund",
        ],
    )

    create = client.post(
        "/api/backend/payments/intents/",
        {
            "amount": "50.00",
            "currency": "NIO",
            "idempotency_key": f"intent-{uuid.uuid4().hex[:8]}",
            "external_ref": "PAY-TEST",
            "provider": "MANUAL",
        },
        format="json",
    )
    assert create.status_code == 201
    payment_id = create.data["payment_id"]

    capture = client.post(
        f"/api/backend/payments/intents/{payment_id}/capture/",
        {"amount": "50.00", "idempotency_key": f"cap-{uuid.uuid4().hex[:8]}"},
        format="json",
    )
    assert capture.status_code == 200
    assert capture.data["status"] == "CAPTURED"

    refund = client.post(
        f"/api/backend/payments/intents/{payment_id}/refund/",
        {"amount": "20.00", "idempotency_key": f"ref-{uuid.uuid4().hex[:8]}", "reason": "partial"},
        format="json",
    )
    assert refund.status_code == 200
    assert refund.data["status"] == "CAPTURED"
    assert refund.data["refunded_total"] == "20.00"

    final_refund = client.post(
        f"/api/backend/payments/intents/{payment_id}/refund/",
        {"amount": "30.00", "idempotency_key": f"ref-{uuid.uuid4().hex[:8]}", "reason": "final"},
        format="json",
    )
    assert final_refund.status_code == 200
    assert final_refund.data["status"] == "REFUNDED"
    assert final_refund.data["refunded_total"] == "50.00"

    payment_intent = PaymentIntent.objects.get(payment_id=payment_id)
    assert payment_intent.status == PaymentIntent.Status.REFUNDED

    payment_events = list(OutboxEvent.objects.filter(source_module="PAYMENTS").values_list("event_type", flat=True))
    assert "PaymentCaptured" in payment_events
    assert payment_events.count("RefundProcessed") >= 2
    assert AuditEvent.objects.filter(module="PAYMENTS", event_type="PAYMENT_CAPTURED").exists()
    assert AuditEvent.objects.filter(module="PAYMENTS", event_type="PAYMENT_REFUNDED").exists()
