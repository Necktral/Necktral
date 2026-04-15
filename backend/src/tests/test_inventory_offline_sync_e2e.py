from __future__ import annotations

import base64
import copy
import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_scope() -> tuple[OrgUnit, OrgUnit]:
    token = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Holding {token}",
        code=f"H-{token}",
    )
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name=f"Company {token}",
        code=f"C-{token}",
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Branch {token}",
        code=f"B-{token}",
    )
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"inv_e2e_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(
        username=username,
        email=f"{username}@test.local",
        password="pass12345",
    )
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
    access = login.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _build_request_signing_message(*, ts: int, nonce: str, canonical_body_bytes: bytes) -> bytes:
    body_hash = hashlib.sha256(canonical_body_bytes).hexdigest()
    return f"{int(ts)}.{str(nonce)}.{body_hash}".encode("utf-8")


def _canon_json(obj: Any) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sign_batch_v2(payload: dict[str, Any], private_key: Ed25519PrivateKey) -> str:
    signable = copy.deepcopy(payload)
    signable["auth"]["signature"] = ""
    canonical_body = _canon_json(signable).encode("utf-8")
    message = _build_request_signing_message(
        ts=int(payload["ts"]),
        nonce=str(payload["nonce"]),
        canonical_body_bytes=canonical_body,
    )
    return base64.b64encode(private_key.sign(message)).decode("utf-8")


@pytest.mark.django_db
def test_inventory_offline_sync_private_lane_flow_applies_receive_command():
    company, branch = _mk_scope()
    user_client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "inventory.warehouse.create",
            "inventory.item.create",
            "inventory.balance.read",
            "sync.device.enroll",
        ],
    )

    bootstrap = user_client.get(
        "/api/auth/bootstrap/session/",
        HTTP_X_DEVICE_CLASS="mobile",
        HTTP_X_SOURCE_DEVICE="qa-inventory-offline-e2e",
    )
    assert bootstrap.status_code == 200
    assert bootstrap.data["shell_mode"] == "mobile"
    assert "inventory" in (bootstrap.data.get("allowed_modules") or [])

    wh_resp = user_client.post(
        "/api/inventory/warehouses/",
        {"name": "Main E2E", "code": "E2E"},
        format="json",
    )
    assert wh_resp.status_code == 201
    warehouse_id = int(wh_resp.data["id"])

    item_resp = user_client.post(
        "/api/inventory/items/",
        {"sku": f"E2E-{uuid.uuid4().hex[:6]}", "name": "Diesel E2E", "uom": "LITER"},
        format="json",
    )
    assert item_resp.status_code == 201
    item_id = int(item_resp.data["id"])

    challenge = user_client.post(
        "/api/sync/enrollment/challenges/",
        {
            "company_id": company.id,
            "branch_id": branch.id,
            "label_hint": "inventory-e2e-device",
            "expires_in_minutes": 15,
        },
        format="json",
    )
    assert challenge.status_code == 201
    enrollment_code = str(challenge.data["enrollment_code"])

    private = Ed25519PrivateKey.generate()
    public_b64 = base64.b64encode(
        private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("utf-8")

    enroll_client = APIClient(raise_request_exception=True)
    enroll = enroll_client.post(
        "/api/sync/enroll/",
        {
            "enrollment_code": enrollment_code,
            "public_key_b64": public_b64,
            "label": "inventory-e2e-device",
            "meta": {"source": "qa-inventory-offline-private-e2e"},
        },
        format="json",
    )
    assert enroll.status_code == 201
    device_id = str(enroll.data["device_id"])

    ts = int(time.time())
    nonce = f"inv-offline-{uuid.uuid4().hex[:12]}"
    command_id = str(uuid.uuid4())
    body: dict[str, Any] = {
        "protocol_version": "2",
        "device_id": device_id,
        "ts": ts,
        "nonce": nonce,
        "auth": {"scheme": "ed25519", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": command_id,
                "type": "INVENTORY.MOVEMENT.RECEIVE",
                "scope": {"company_id": company.id, "branch_id": branch.id},
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "warehouse_id": warehouse_id,
                    "item_id": item_id,
                    "qty": "5.0000",
                    "unit_cost": "1.200000",
                    "idempotency_key": f"offline-e2e-{uuid.uuid4().hex[:12]}",
                    "note": "captura offline e2e",
                },
            }
        ],
    }
    body["auth"]["signature"] = _sign_batch_v2(body, private)

    sync_client = APIClient(raise_request_exception=True)
    batch = sync_client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=device_id)
    assert batch.status_code == 200
    assert isinstance(batch.data.get("results"), list)
    row = next((entry for entry in batch.data["results"] if entry.get("command_id") == command_id), None)
    assert row is not None
    assert row["status"] in {"APPLIED", "DUPLICATE"}

    balance = user_client.get(f"/api/inventory/balances/?warehouse_id={warehouse_id}&item_id={item_id}")
    assert balance.status_code == 200
    assert balance.data["qty_on_hand"] == "5.0000"


@pytest.mark.django_db
def test_inventory_private_lane_denies_access_without_inventory_permission():
    company, branch = _mk_scope()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["sync.device.enroll"],
    )

    bootstrap = client.get(
        "/api/auth/bootstrap/session/",
        HTTP_X_DEVICE_CLASS="desktop",
        HTTP_X_SOURCE_DEVICE="qa-inventory-offline-e2e-deny",
    )
    assert bootstrap.status_code == 200
    assert bootstrap.data["shell_mode"] == "desktop"
    assert "inventory" not in (bootstrap.data.get("allowed_modules") or [])

    denied = client.get("/api/inventory/warehouses/")
    assert denied.status_code == 403
