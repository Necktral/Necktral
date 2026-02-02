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
from apps.sync_engine.v2 import build_string_to_sign, strip_signature_for_sign


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def _sign(priv: Ed25519PrivateKey, *, msg: bytes) -> str:
    return _b64(priv.sign(msg))


def _sign_v2(priv: Ed25519PrivateKey, *, ts: int, nonce: str, body: dict) -> str:
    body_for_sign = strip_signature_for_sign(body)
    msg = build_string_to_sign(ts=ts, nonce=nonce, body_for_sign=body_for_sign)
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


def _setup_inventory_device():
    company, branch = _mk_scope()
    user = User.objects.create_user(username=f"u_sync_inv_{uuid.uuid4().hex[:6]}", password="x")

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

    r = c.post("/api/inventory/warehouses/", {"name": "Main", "code": "M"}, format="json")
    assert r.status_code == 201
    wh_id = r.data["id"]

    r = c.post("/api/inventory/items/", {"sku": "DIESEL", "name": "Diesel", "uom": "LITER"}, format="json")
    assert r.status_code == 201
    item_id = r.data["id"]

    r = c.post("/api/sync/enrollment/challenges/", {"branch_id": branch.id, "expires_in_minutes": 10}, format="json")
    assert r.status_code == 201
    code = r.data["enrollment_code"]

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

    return {
        "company": company,
        "branch": branch,
        "client": c,
        "device_client": device_client,
        "device_id": device_id,
        "priv": priv,
        "warehouse_id": wh_id,
        "item_id": item_id,
    }


def _build_command(
    *,
    priv: Ed25519PrivateKey,
    command_id: str,
    command_type: str,
    company_id: int,
    branch_id: int,
    occurred_at: str,
    sequence: int,
    payload: dict,
    prev_hash: str = "",
):
    payload_hash = sha256_hex(canon_json(payload))
    msg = build_command_signing_message(
        command_id=command_id,
        command_type=command_type,
        company_id=company_id,
        branch_id=branch_id,
        occurred_at=occurred_at,
        sequence=sequence,
        payload_hash=payload_hash,
        prev_hash=prev_hash,
    )
    sig = _sign(priv, msg=msg)
    return {
        "command_id": command_id,
        "type": command_type,
        "scope": {"company_id": company_id, "branch_id": branch_id},
        "occurred_at": occurred_at,
        "sequence": sequence,
        "payload": payload,
        "payload_hash": payload_hash,
        "prev_hash": prev_hash,
        "command_sig": sig,
    }


def _build_batch(*, priv: Ed25519PrivateKey, device_id: str, commands: list[dict]):
    ts = int(timezone.now().timestamp())
    nonce = f"nonce-{uuid.uuid4().hex[:8]}"
    batch = {
        "protocol_version": "2",
        "device_id": device_id,
        "ts": ts,
        "nonce": nonce,
        "auth": {"scheme": "ed25519", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "sent_at": timezone.now().isoformat(),
        "batch": commands,
    }
    batch["auth"]["signature"] = _sign_v2(priv, ts=ts, nonce=nonce, body=batch)
    return batch


def _balance_qty(data: dict) -> str:
    if isinstance(data, dict) and "results" in data:
        results = data.get("results") or []
        if results:
            return results[0].get("qty_on_hand")
        return "0.0000"
    if isinstance(data, dict) and "qty_on_hand" in data:
        return data.get("qty_on_hand")
    return "0.0000"


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

    ts = int(timezone.now().timestamp())
    nonce = "nonce-v2-inv"
    batch = {
        "protocol_version": "2",
        "device_id": device_id,
        "ts": ts,
        "nonce": nonce,
        "auth": {"scheme": "ed25519", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "sent_at": timezone.now().isoformat(),
        "batch": [
            {
                "command_id": cmd1,
                "type": "INVENTORY_MOVEMENT_RECEIVE",
                "scope": {"company_id": company.id, "branch_id": branch.id},
                "occurred_at": occurred,
                "sequence": 1,
                "payload": payload1,
                "payload_hash": h1,
                "prev_hash": "",
                "command_sig": sig1,
            },
            {
                "command_id": cmd2,
                "type": "INVENTORY_MOVEMENT_ISSUE",
                "scope": {"company_id": company.id, "branch_id": branch.id},
                "occurred_at": occurred,
                "sequence": 2,
                "payload": payload2,
                "payload_hash": h2,
                "prev_hash": "",
                "command_sig": sig2,
            },
        ],
    }
    batch["auth"]["signature"] = _sign_v2(priv, ts=ts, nonce=nonce, body=batch)

    rr = device_client.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr.status_code == 200

    statuses = [x["status"] for x in rr.data["results"]]
    assert statuses == ["APPLIED", "APPLIED"]

    # Verificar stock via endpoint balance normal
    r = c.get(f"/api/inventory/balances/?warehouse_id={wh_id}&item_id={item_id}&limit=10&offset=0")
    assert r.status_code == 200
    assert _balance_qty(r.data) == "8.0000"

    # Auditoría: aplica y también se emiten eventos de inventario
    assert AuditEvent.objects.filter(event_type="SYNC_COMMAND_APPLIED").exists()
    assert AuditEvent.objects.filter(module="INVENTORY").exists()


@pytest.mark.django_db
def test_sync_inventory_duplicate_command_returns_duplicate():
    env = _setup_inventory_device()
    company = env["company"]
    branch = env["branch"]
    device_client = env["device_client"]
    device_id = env["device_id"]
    priv = env["priv"]
    wh_id = env["warehouse_id"]
    item_id = env["item_id"]

    occurred = occurred_at_canonical(timezone.now())
    cmd_id = str(uuid.uuid4())
    payload = {"warehouse_id": wh_id, "item_id": item_id, "qty": "5.0000", "unit_cost": "2.000000"}

    cmd1 = _build_command(
        priv=priv,
        command_id=cmd_id,
        command_type="INVENTORY_MOVEMENT_RECEIVE",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred,
        sequence=1,
        payload=payload,
    )
    cmd2 = _build_command(
        priv=priv,
        command_id=cmd_id,
        command_type="INVENTORY_MOVEMENT_RECEIVE",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred,
        sequence=2,
        payload=payload,
    )

    batch = _build_batch(priv=priv, device_id=device_id, commands=[cmd1, cmd2])
    rr = device_client.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr.status_code == 200
    assert [x["status"] for x in rr.data["results"]] == ["APPLIED", "DUPLICATE"]


@pytest.mark.django_db
def test_sync_inventory_idempotency_key_conflict_rejected():
    env = _setup_inventory_device()
    company = env["company"]
    branch = env["branch"]
    device_client = env["device_client"]
    device_id = env["device_id"]
    priv = env["priv"]
    wh_id = env["warehouse_id"]
    item_id = env["item_id"]

    occurred = occurred_at_canonical(timezone.now())
    idem = "idem-conflict-1"

    payload_ok = {
        "warehouse_id": wh_id,
        "item_id": item_id,
        "qty": "5.0000",
        "unit_cost": "2.000000",
        "idempotency_key": idem,
    }
    payload_conflict = {
        "warehouse_id": wh_id,
        "item_id": item_id,
        "qty": "6.0000",
        "unit_cost": "2.000000",
        "idempotency_key": idem,
    }

    cmd1 = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type="INVENTORY_MOVEMENT_RECEIVE",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred,
        sequence=1,
        payload=payload_ok,
    )
    cmd2 = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type="INVENTORY_MOVEMENT_RECEIVE",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred,
        sequence=2,
        payload=payload_conflict,
    )

    batch = _build_batch(priv=priv, device_id=device_id, commands=[cmd1, cmd2])
    rr = device_client.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr.status_code == 200
    assert rr.data["results"][0]["status"] == "APPLIED"
    assert rr.data["results"][1]["status"] == "REJECTED"
    assert rr.data["results"][1]["reason"] == "INVENTORY_IDEMPOTENCY_CONFLICT"


@pytest.mark.django_db
def test_sync_inventory_invalid_scope_rejected():
    env = _setup_inventory_device()
    company = env["company"]
    device_client = env["device_client"]
    device_id = env["device_id"]
    priv = env["priv"]
    wh_id = env["warehouse_id"]
    item_id = env["item_id"]

    _, other_branch = _mk_scope()
    occurred = occurred_at_canonical(timezone.now())
    payload = {"warehouse_id": wh_id, "item_id": item_id, "qty": "1.0000", "unit_cost": "1.000000"}

    cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type="INVENTORY_MOVEMENT_RECEIVE",
        company_id=company.id,
        branch_id=other_branch.id,
        occurred_at=occurred,
        sequence=1,
        payload=payload,
    )

    batch = _build_batch(priv=priv, device_id=device_id, commands=[cmd])
    rr = device_client.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr.status_code == 200
    assert rr.data["results"][0]["status"] == "REJECTED"
    assert rr.data["results"][0]["reason"] == "SYNC_FORBIDDEN_SCOPE"


@pytest.mark.django_db
def test_sync_inventory_insufficient_stock_rejected():
    env = _setup_inventory_device()
    company = env["company"]
    branch = env["branch"]
    device_client = env["device_client"]
    device_id = env["device_id"]
    priv = env["priv"]
    wh_id = env["warehouse_id"]
    item_id = env["item_id"]

    occurred = occurred_at_canonical(timezone.now())

    receive_cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type="INVENTORY_MOVEMENT_RECEIVE",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred,
        sequence=1,
        payload={"warehouse_id": wh_id, "item_id": item_id, "qty": "5.0000", "unit_cost": "1.000000"},
    )
    issue_cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type="INVENTORY_MOVEMENT_ISSUE",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred,
        sequence=2,
        payload={"warehouse_id": wh_id, "item_id": item_id, "qty": "15.0000"},
    )

    batch = _build_batch(priv=priv, device_id=device_id, commands=[receive_cmd, issue_cmd])
    rr = device_client.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr.status_code == 200
    assert rr.data["results"][0]["status"] == "APPLIED"
    assert rr.data["results"][1]["status"] == "REJECTED"
    assert rr.data["results"][1]["reason"] == "INVENTORY_INSUFFICIENT_STOCK"


@pytest.mark.django_db
def test_sync_inventory_invalid_signature_rejected():
    env = _setup_inventory_device()
    company = env["company"]
    branch = env["branch"]
    device_client = env["device_client"]
    device_id = env["device_id"]
    priv = env["priv"]
    wh_id = env["warehouse_id"]
    item_id = env["item_id"]

    occurred = occurred_at_canonical(timezone.now())
    payload = {"warehouse_id": wh_id, "item_id": item_id, "qty": "1.0000", "unit_cost": "1.000000"}

    cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type="INVENTORY_MOVEMENT_RECEIVE",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred,
        sequence=1,
        payload=payload,
    )
    cmd["command_sig"] = "AAAA"  # firma inválida

    batch = _build_batch(priv=priv, device_id=device_id, commands=[cmd])
    rr = device_client.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr.status_code == 200
    assert rr.data["results"][0]["status"] == "REJECTED"
    assert rr.data["results"][0]["reason"] == "SYNC_INVALID_SIGNATURE"


@pytest.mark.django_db
def test_sync_inventory_payload_mismatch_rejected():
    env = _setup_inventory_device()
    company = env["company"]
    branch = env["branch"]
    device_client = env["device_client"]
    device_id = env["device_id"]
    priv = env["priv"]
    wh_id = env["warehouse_id"]
    item_id = env["item_id"]

    occurred = occurred_at_canonical(timezone.now())
    cmd_id = str(uuid.uuid4())

    payload1 = {"warehouse_id": wh_id, "item_id": item_id, "qty": "2.0000", "unit_cost": "1.000000"}
    payload2 = {"warehouse_id": wh_id, "item_id": item_id, "qty": "3.0000", "unit_cost": "1.000000"}

    cmd1 = _build_command(
        priv=priv,
        command_id=cmd_id,
        command_type="INVENTORY_MOVEMENT_RECEIVE",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred,
        sequence=1,
        payload=payload1,
    )
    cmd2 = _build_command(
        priv=priv,
        command_id=cmd_id,
        command_type="INVENTORY_MOVEMENT_RECEIVE",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred,
        sequence=2,
        payload=payload2,
    )

    batch = _build_batch(priv=priv, device_id=device_id, commands=[cmd1, cmd2])
    rr = device_client.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr.status_code == 200
    assert rr.data["results"][0]["status"] == "APPLIED"
    assert rr.data["results"][1]["status"] == "REJECTED"
    assert rr.data["results"][1]["reason"] == "SYNC_PAYLOAD_MISMATCH"


@pytest.mark.django_db
def test_sync_inventory_batch_limit_exceeded_rejected():
    env = _setup_inventory_device()
    company = env["company"]
    branch = env["branch"]
    device_client = env["device_client"]
    device_id = env["device_id"]
    priv = env["priv"]
    wh_id = env["warehouse_id"]
    item_id = env["item_id"]

    occurred = occurred_at_canonical(timezone.now())
    commands = []
    for i in range(101):
        payload = {
            "warehouse_id": wh_id,
            "item_id": item_id,
            "qty": "1.0000",
            "unit_cost": "1.000000",
        }
        commands.append(
            _build_command(
                priv=priv,
                command_id=str(uuid.uuid4()),
                command_type="INVENTORY_MOVEMENT_RECEIVE",
                company_id=company.id,
                branch_id=branch.id,
                occurred_at=occurred,
                sequence=i + 1,
                payload=payload,
            )
        )

    batch = _build_batch(priv=priv, device_id=device_id, commands=commands)
    rr = device_client.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr.status_code == 200
    assert rr.data["results"] == []
    assert rr.data["summary"]["received"] == 101
    assert rr.data["summary"]["rejected"] == 101
    assert rr.data["summary"]["applied"] == 0
