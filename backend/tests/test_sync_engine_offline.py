import base64
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RolePermission, RoleAssignment

from apps.sync_engine.signing import build_command_signing_message, sha256_hex, canon_json, occurred_at_canonical

User = get_user_model()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def sign_cmd(
    priv: Ed25519PrivateKey,
    *,
    command_id: str,
    command_type: str,
    company_id: int,
    branch_id: int | None,
    occurred_at_iso: str,
    sequence: int | None,
    payload_hash: str,
    prev_hash: str,
) -> str:
    msg = build_command_signing_message(
        command_id=command_id,
        command_type=command_type,
        company_id=company_id,
        branch_id=branch_id,
        occurred_at=occurred_at_iso,
        sequence=sequence,
        payload_hash=payload_hash,
        prev_hash=prev_hash,
    )
    sig = priv.sign(msg)
    return _b64(sig)


@pytest.mark.django_db
def test_enroll_and_sync_replay_is_duplicate():
    from apps.sync_engine.signing import verify_ed25519_signature, build_command_signing_message, occurred_at_canonical

    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)

    user = User.objects.create_user(username="owner", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    # Permisos RBAC necesarios (blindado)
    role, _ = Role.objects.get_or_create(name=f"admin_{uuid.uuid4().hex}", defaults={"is_active": True})
    if not role.is_active:
        role.is_active = True
        role.save(update_fields=["is_active"])
    p_enroll, _ = Permission.objects.get_or_create(
        code="sync.device.enroll", defaults={"is_active": True, "description": ""}
    )
    if not p_enroll.is_active:
        p_enroll.is_active = True
        p_enroll.save(update_fields=["is_active"])
    RolePermission.objects.get_or_create(role=role, permission=p_enroll)
    RoleAssignment.objects.get_or_create(user=user, role=role, org_unit=company, defaults={"is_active": True})

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "owner", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    # Crear challenge
    r = client.post(
        "/api/sync/enrollment/challenges/",
        {"branch_id": branch.id, "expires_in_minutes": 10, "label_hint": "Caja 1"},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
        HTTP_X_BRANCH_ID=str(branch.id),
    )
    assert r.status_code == 201
    code = r.data["enrollment_code"]

    # Crear keypair
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()

    # Enrolar (sin JWT)
    client2 = APIClient()
    r2 = client2.post(
        "/api/sync/enroll/",
        {"enrollment_code": code, "public_key_b64": _b64(pub), "label": "Tablet A"},
        format="json",
    )
    assert r2.status_code == 201
    device_id = r2.data["device_id"]

    # Batch con DEMO_PING
    command_id = str(uuid.uuid4())
    occurred = timezone.now()
    occurred_canon = occurred_at_canonical(occurred)
    payload = {"msg": "hola"}
    payload_hash = sha256_hex(canon_json(payload))
    sig = sign_cmd(
        priv,
        command_id=command_id,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at_iso=occurred_canon,
        sequence=1,
        payload_hash=payload_hash,
        prev_hash="",
    )

    # Assert local de firma
    msg = build_command_signing_message(
        command_id=command_id,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=occurred_canon,
        sequence=1,
        payload_hash=payload_hash,
        prev_hash="",
    )
    assert verify_ed25519_signature(public_key_raw=pub, signature_b64=sig, message=msg) is True

    # Permisos RBAC necesarios (blindado)
    role, _ = Role.objects.get_or_create(name="admin", defaults={"is_active": True})
    if not role.is_active:
        role.is_active = True
        role.save(update_fields=["is_active"])
    p_enroll, _ = Permission.objects.get_or_create(
        code="sync.device.enroll", defaults={"is_active": True, "description": ""}
    )
    if not p_enroll.is_active:
        p_enroll.is_active = True
        p_enroll.save(update_fields=["is_active"])
    RolePermission.objects.get_or_create(role=role, permission=p_enroll)
    RoleAssignment.objects.get_or_create(user=user, role=role, org_unit=company, defaults={"is_active": True})

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "owner", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    # Crear challenge
    r = client.post(
        "/api/sync/enrollment/challenges/",
        {"branch_id": branch.id, "expires_in_minutes": 10, "label_hint": "Caja 1"},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
        HTTP_X_BRANCH_ID=str(branch.id),
    )
    assert r.status_code == 201
    code = r.data["enrollment_code"]

    # Crear keypair
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()

    # Enrolar (sin JWT)
    client2 = APIClient()
    r2 = client2.post(
        "/api/sync/enroll/",
        {"enrollment_code": code, "public_key_b64": _b64(pub), "label": "Tablet A"},
        format="json",
    )
    assert r2.status_code == 201
    device_id = r2.data["device_id"]

    # Batch con DEMO_PING
    command_id = str(uuid.uuid4())
    occurred = timezone.now()
    occurred_canon = occurred_at_canonical(occurred)
    payload = {"msg": "hola"}
    payload_hash = sha256_hex(canon_json(payload))
    sig = sign_cmd(
        priv,
        command_id=command_id,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at_iso=occurred_canon,
        sequence=1,
        payload_hash=payload_hash,
        prev_hash="",
    )

    batch_id = str(uuid.uuid4())
    batch = {
        "batch_id": batch_id,
        "device_id": device_id,
        "sent_at": timezone.now().isoformat(),
        "commands": [
            {
                "command_id": command_id,
                "command_type": "DEMO_PING",
                "company_id": company.id,
                "branch_id": branch.id,
                "occurred_at": occurred_canon,
                "sequence": 1,
                "payload": payload,
                "payload_hash": payload_hash,
                "prev_hash": "",
                "signature": sig,
            }
        ],
    }

    rr = client2.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr.status_code == 200
    assert rr.data["results"][0]["status"] == "APPLIED"
    assert rr.data["results"][0]["refs"]["pong"] is True

    # Replay (mismo command_id, mismo payload_hash) => DUPLICATE
    rr2 = client2.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr2.status_code == 200
    assert rr2.data["results"][0]["status"] == "DUPLICATE"

    # Auditoría: existe aplicado
    assert AuditEvent.objects.filter(event_type="SYNC_COMMAND_APPLIED").exists()


@pytest.mark.django_db
def test_batch_partial_invalid_signature_does_not_break_other_commands():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)

    user = User.objects.create_user(username="owner2", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    role, _ = Role.objects.get_or_create(name="admin2", defaults={"is_active": True})
    if not role.is_active:
        role.is_active = True
        role.save(update_fields=["is_active"])
    p_enroll, _ = Permission.objects.get_or_create(
        code="sync.device.enroll", defaults={"is_active": True, "description": ""}
    )
    if not p_enroll.is_active:
        p_enroll.is_active = True
        p_enroll.save(update_fields=["is_active"])
    RolePermission.objects.get_or_create(role=role, permission=p_enroll)
    RoleAssignment.objects.get_or_create(user=user, role=role, org_unit=company, defaults={"is_active": True})

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "owner2", "password": "pass12345"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.post(
        "/api/sync/enrollment/challenges/",
        {"expires_in_minutes": 10},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    code = r.data["enrollment_code"]

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()

    client2 = APIClient()
    r2 = client2.post("/api/sync/enroll/", {"enrollment_code": code, "public_key_b64": _b64(pub)}, format="json")
    device_id = r2.data["device_id"]

    occurred = timezone.now()
    occurred_canon = occurred_at_canonical(occurred)
    payload_ok = {"msg": "ok"}
    payload_hash_ok = sha256_hex(canon_json(payload_ok))
    cmd_ok = str(uuid.uuid4())
    sig_ok = sign_cmd(
        priv,
        command_id=cmd_ok,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=None,
        occurred_at_iso=occurred_canon,
        sequence=1,
        payload_hash=payload_hash_ok,
        prev_hash="",
    )

    payload_bad = {"msg": "bad"}
    payload_hash_bad = sha256_hex(canon_json(payload_bad))
    cmd_bad = str(uuid.uuid4())
    sig_bad = "AAAA"  # inválida base64/ed25519

    batch = {
        "batch_id": str(uuid.uuid4()),
        "device_id": device_id,
        "sent_at": timezone.now().isoformat(),
        "commands": [
            {
                "command_id": cmd_ok,
                "command_type": "DEMO_PING",
                "company_id": company.id,
                "branch_id": None,
                "occurred_at": occurred_canon,
                "sequence": 1,
                "payload": payload_ok,
                "payload_hash": payload_hash_ok,
                "prev_hash": "",
                "signature": sig_ok,
            },
            {
                "command_id": cmd_bad,
                "command_type": "DEMO_PING",
                "company_id": company.id,
                "branch_id": None,
                "occurred_at": occurred_canon,
                "sequence": 2,
                "payload": payload_bad,
                "payload_hash": payload_hash_bad,
                "prev_hash": "",
                "signature": sig_bad,
            },
        ],
    }

    rr = client2.post("/api/sync/batch/", batch, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr.status_code == 200

    statuses = [x["status"] for x in rr.data["results"]]
    assert statuses[0] == "APPLIED"
    assert statuses[1] == "REJECTED"
    assert rr.data["results"][1]["reason"] == "SYNC_INVALID_SIGNATURE"


@pytest.mark.django_db
def test_payload_mismatch_same_command_id_is_rejected():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)

    user = User.objects.create_user(username="owner3", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    role, _ = Role.objects.get_or_create(name="admin3", defaults={"is_active": True})
    if not role.is_active:
        role.is_active = True
        role.save(update_fields=["is_active"])
    p_enroll, _ = Permission.objects.get_or_create(
        code="sync.device.enroll", defaults={"is_active": True, "description": ""}
    )
    if not p_enroll.is_active:
        p_enroll.is_active = True
        p_enroll.save(update_fields=["is_active"])
    RolePermission.objects.get_or_create(role=role, permission=p_enroll)
    RoleAssignment.objects.get_or_create(user=user, role=role, org_unit=company, defaults={"is_active": True})

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "owner3", "password": "pass12345"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.post(
        "/api/sync/enrollment/challenges/",
        {"expires_in_minutes": 10},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    code = r.data["enrollment_code"]

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()

    client2 = APIClient()
    r2 = client2.post("/api/sync/enroll/", {"enrollment_code": code, "public_key_b64": _b64(pub)}, format="json")
    device_id = r2.data["device_id"]

    occurred = timezone.now()
    command_id = str(uuid.uuid4())

    payload1 = {"msg": "one"}
    h1 = sha256_hex(canon_json(payload1))
    sig1 = sign_cmd(
        priv,
        command_id=command_id,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=None,
        occurred_at_iso=occurred.isoformat(),
        sequence=1,
        payload_hash=h1,
        prev_hash="",
    )

    payload2 = {"msg": "two"}
    h2 = sha256_hex(canon_json(payload2))
    sig2 = sign_cmd(
        priv,
        command_id=command_id,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=None,
        occurred_at_iso=occurred.isoformat(),
        sequence=1,
        payload_hash=h2,
        prev_hash="",
    )

    batch1 = {
        "batch_id": str(uuid.uuid4()),
        "device_id": device_id,
        "commands": [
            {
                "command_id": command_id,
                "command_type": "DEMO_PING",
                "company_id": company.id,
                "branch_id": None,
                "occurred_at": occurred.isoformat(),
                "sequence": 1,
                "payload": payload1,
                "payload_hash": h1,
                "prev_hash": "",
                "signature": sig1,
            }
        ],
    }

    batch2 = {
        "batch_id": str(uuid.uuid4()),
        "device_id": device_id,
        "commands": [
            {
                "command_id": command_id,
                "command_type": "DEMO_PING",
                "company_id": company.id,
                "branch_id": None,
                "occurred_at": occurred.isoformat(),
                "sequence": 1,
                "payload": payload2,
                "payload_hash": h2,
                "prev_hash": "",
                "signature": sig2,
            }
        ],
    }

    rr1 = client2.post("/api/sync/batch/", batch1, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr1.data["results"][0]["status"] == "APPLIED"

    rr2 = client2.post("/api/sync/batch/", batch2, format="json", HTTP_X_DEVICE_ID=device_id)
    assert rr2.data["results"][0]["status"] == "REJECTED"
    assert rr2.data["results"][0]["reason"] == "SYNC_PAYLOAD_MISMATCH"
