import base64
import uuid

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.sync_engine.signing import build_command_signing_message, canon_json, occurred_at_canonical, sha256_hex


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def _sign(priv: Ed25519PrivateKey, *, msg: bytes) -> str:
    return _b64(priv.sign(msg))


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, user: User, company: OrgUnit, branch: OrgUnit, perms: list[str]) -> APIClient:
    UserMembership.objects.get_or_create(user=user, org_unit=company, defaults={"is_active": True})
    UserMembership.objects.get_or_create(user=user, org_unit=branch, defaults={"is_active": True})

    role = Role.objects.create(name=f"tmp_role_{uuid.uuid4().hex[:8]}", is_active=True)
    for p in perms:
        perm, _ = Permission.objects.get_or_create(code=p, defaults={"description": p, "is_active": True})
        if not perm.is_active:
            perm.is_active = True
            perm.save(update_fields=["is_active"])
        RolePermission.objects.get_or_create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=company, origin=RoleAssignment.Origin.MANUAL)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, origin=RoleAssignment.Origin.MANUAL)

    c = APIClient()
    login = c.post("/api/auth/login/", {"username": user.username, "password": "x"}, format="json")
    assert login.status_code == 200
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


@pytest.mark.django_db
def test_sync_batch_inventory_receive_issue_applies_and_updates_stock():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="u_sync_inv", password="x")

    c = _client_with_perms(
        user=user,
        company=company,
        branch=branch,
        perms=[
            "sync.device.enroll",
            "inventory.warehouse.create",
            "inventory.item.create",
            "inventory.balance.read",
        ],
    )

    # Crear warehouse + item por API normal (con JWT)
    r = c.post("/api/inventory/warehouses/", {"name": "Main", "code": "M"}, format="json")
    assert r.status_code == 201
    wh_id = r.data["id"]

    r = c.post("/api/inventory/items/", {"sku": "DIESEL", "name": "Diesel", "uom": "LITER"}, format="json")
    assert r.status_code == 201
    item_id = r.data["id"]

    # Crear challenge (JWT + contexto)
    r = c.post("/api/sync/enrollment/challenges/", {"branch_id": branch.id, "expires_in_minutes": 10}, format="json")
    assert r.status_code == 201
    code = r.data["enrollment_code"]

    # Enroll (sin JWT)
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()

    device_client = APIClient()
    r2 = device_client.post(
        "/api/sync/enroll/",
        {"enrollment_code": code, "public_key_b64": _b64(pub), "label": "Tablet"},
        format="json",
    )
    assert r2.status_code == 201
    device_id = r2.data["device_id"]

    occurred = occurred_at_canonical(timezone.now())

    # Command 1: RECEIVE
    cmd1 = str(uuid.uuid4())
    payload1 = {"warehouse_id": wh_id, "item_id": item_id, "qty": "10.0000", "unit_cost": "1.250000"}
    h1 = sha256_hex(canon_json(payload1))
    msg1 = build_command_signing_message(
        command_id=cmd1,
        command_type="INVENTORY_MOVEMENT_RECEIVE",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred,
        sequence=1,
        payload_hash=h1,
        prev_hash="",
    )
    sig1 = _sign(priv, msg=msg1)

    # Command 2: ISSUE
    cmd2 = str(uuid.uuid4())
    payload2 = {"warehouse_id": wh_id, "item_id": item_id, "qty": "2.0000"}
    h2 = sha256_hex(canon_json(payload2))
    msg2 = build_command_signing_message(
        command_id=cmd2,
        command_type="INVENTORY_MOVEMENT_ISSUE",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred,
        sequence=2,
        payload_hash=h2,
        prev_hash="",
    )
    sig2 = _sign(priv, msg=msg2)

    batch = {
        "batch_id": str(uuid.uuid4()),
        "device_id": device_id,
        "sent_at": timezone.now().isoformat(),
        "commands": [
            {
                "command_id": cmd1,
                "command_type": "INVENTORY_MOVEMENT_RECEIVE",
                "company_id": company.id,
                "branch_id": branch.id,
                "occurred_at": occurred,
                "sequence": 1,
                "payload": payload1,
                "payload_hash": h1,
                "prev_hash": "",
                "signature": sig1,
            },
            {
                "command_id": cmd2,
                "command_type": "INVENTORY_MOVEMENT_ISSUE",
                "company_id": company.id,
                "branch_id": branch.id,
                "occurred_at": occurred,
                "sequence": 2,
                "payload": payload2,
                "payload_hash": h2,
                "prev_hash": "",
                "signature": sig2,
            },
        ],
    }

    rr = device_client.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr.status_code == 200

    statuses = [x["status"] for x in rr.data["results"]]
    assert statuses == ["APPLIED", "APPLIED"]

    # Verificar stock via endpoint balance normal
    r = c.get(f"/api/inventory/balances/?warehouse_id={wh_id}&item_id={item_id}")
    assert r.status_code == 200
    assert r.data["qty_on_hand"] == "8.0000"

    # Auditoría: aplica y también se emiten eventos de inventario
    assert AuditEvent.objects.filter(event_type="SYNC_COMMAND_APPLIED").exists()
    assert AuditEvent.objects.filter(module="INVENTORY").exists()
