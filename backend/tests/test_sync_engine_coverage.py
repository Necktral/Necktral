import base64
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apps.modulos.iam.models import OrgUnit
from apps.modulos.sync_engine.errors import SyncRejectError
from apps.modulos.sync_engine.models import Device, DeviceEnrollmentChallenge
from apps.modulos.sync_engine.registry import register
from apps.modulos.sync_engine.services import SyncPolicy, process_command
from apps.modulos.sync_engine.signing import (
    b64decode_strict,
    build_command_signing_message,
    canon_json,
    occurred_at_canonical,
    public_key_from_b64,
    sha256_hex,
    verify_ed25519_signature,
)


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _mk_request(*, company=None, branch=None):
    return SimpleNamespace(META={}, path="/api/sync/batch/", method="POST", company=company, branch=branch)


def _build_cmd(
    *,
    priv: Ed25519PrivateKey,
    command_type: str,
    company_id: int,
    branch_id: int | None,
    payload: dict,
    command_id: str | None = None,
    sequence: int | None = 1,
    occurred_at: timezone.datetime | None = None,
    prev_hash: str = "",
    payload_hash_override: str | None = None,
    signature_override: str | None = None,
):
    cmd_id = command_id or str(uuid.uuid4())
    occ_dt = occurred_at or timezone.now()
    occ = occurred_at_canonical(occ_dt)
    payload_hash = payload_hash_override or sha256_hex(canon_json(payload))
    msg = build_command_signing_message(
        command_id=cmd_id,
        command_type=command_type,
        company_id=company_id,
        branch_id=branch_id,
        occurred_at=occ,
        sequence=sequence,
        payload_hash=payload_hash,
        prev_hash=prev_hash,
    )
    sig = signature_override or _b64(priv.sign(msg))
    return {
        "command_id": cmd_id,
        "command_type": command_type,
        "company_id": company_id,
        "branch_id": branch_id,
        "occurred_at": occ_dt,
        "sequence": sequence,
        "payload": payload,
        "payload_hash": payload_hash,
        "prev_hash": prev_hash,
        "signature": sig,
    }


@pytest.mark.django_db
def test_signing_helpers_invalid_inputs():
    naive = datetime(2024, 1, 1, 12, 0, 0)
    assert "+00:00" in occurred_at_canonical(naive)

    with pytest.raises(Exception):
        b64decode_strict("@@notb64@@")

    bad_pk = _b64(b"short")
    with pytest.raises(ValueError):
        public_key_from_b64(bad_pk)

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()
    msg = b"hello"
    assert verify_ed25519_signature(public_key_raw=pub, signature_b64=_b64(b"short"), message=msg) is False
    assert verify_ed25519_signature(public_key_raw=b"bad", signature_b64=_b64(b"0" * 64), message=msg) is False


@pytest.mark.django_db
def test_registry_duplicate_registration_raises():
    @register("TEST_DUP_COVERAGE")
    def _handler(_ctx, _payload):
        return {"refs": {"ok": True}}

    with pytest.raises(RuntimeError):
        @register("TEST_DUP_COVERAGE")
        def _handler2(_ctx, _payload):
            return {"refs": {"ok": False}}


@pytest.mark.django_db
def test_models_clean_and_helpers():
    company, branch = _mk_scope()
    other_holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H2")
    other_company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C2", parent=other_holding)
    other_branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B2", parent=other_company)
    user = get_user_model().objects.create_user(username=f"u_cov_{uuid.uuid4().hex[:6]}", password="x")

    dev = Device(company=company, branch=other_branch, public_key=b"0" * 32)
    with pytest.raises(ValidationError):
        dev.full_clean()

    ch = DeviceEnrollmentChallenge(
        company=company,
        branch=other_branch,
        enrollment_code_hash="x" * 64,
        expires_at=timezone.now() + timedelta(minutes=5),
        created_by_user=user,
    )
    with pytest.raises(ValidationError):
        ch.full_clean()

    ch2 = DeviceEnrollmentChallenge(
        company=company,
        branch=branch,
        enrollment_code_hash="y" * 64,
        expires_at=timezone.now() - timedelta(seconds=1),
        created_by_user=user,
    )
    assert ch2.is_valid_now() is False

    ch3 = DeviceEnrollmentChallenge(
        company=company,
        branch=branch,
        enrollment_code_hash="z" * 64,
        expires_at=timezone.now() + timedelta(minutes=5),
        created_by_user=user,
    )
    ch3.used_at = timezone.now()
    assert ch3.is_valid_now() is False

    dev2 = Device.objects.create(company=company, branch=branch, public_key=b"1" * 32)
    dev2.mark_seen()
    dev2.revoke()
    dev2.refresh_from_db()
    assert dev2.status == Device.Status.REVOKED
    assert dev2.revoked_at is not None


@pytest.mark.django_db
def test_process_command_rejections_and_duplicates():
    company, branch = _mk_scope()
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()
    device = Device.objects.create(company=company, branch=branch, public_key=pub)

    policy = SyncPolicy(
        max_commands_per_batch=10,
        max_payload_bytes=32,
        max_device_clock_skew_seconds=1,
        seq_tolerant=True,
    )

    request = _mk_request(company=company, branch=branch)

    # payload size limit
    big_payload = {"data": "x" * 100}
    cmd = _build_cmd(
        priv=priv,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload=big_payload,
    )
    out = process_command(request=request, actor_user=None, device=device, cmd=cmd, policy=policy)
    assert out["status"] == "REJECTED"
    assert out["reason"] == "SYNC_LIMIT_EXCEEDED"

    # device revoked
    device.status = Device.Status.REVOKED
    device.save(update_fields=["status"])
    cmd2 = _build_cmd(
        priv=priv,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"msg": "hi"},
    )
    out2 = process_command(request=request, actor_user=None, device=device, cmd=cmd2, policy=policy)
    assert out2["status"] == "REJECTED"
    assert out2["reason"] == "SYNC_DEVICE_REVOKED"

    # device quarantined
    device.status = Device.Status.QUARANTINED
    device.save(update_fields=["status"])
    cmd3 = _build_cmd(
        priv=priv,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"msg": "hi"},
    )
    out3 = process_command(request=request, actor_user=None, device=device, cmd=cmd3, policy=policy)
    assert out3["status"] == "REJECTED"
    assert out3["reason"] == "SYNC_DEVICE_QUARANTINED"


@pytest.mark.django_db
def test_process_command_scope_hash_signature_and_mismatch():
    company, branch = _mk_scope()
    priv = Ed25519PrivateKey.generate()
    other_priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()
    device = Device.objects.create(company=company, branch=branch, public_key=pub)

    policy = SyncPolicy(
        max_commands_per_batch=10,
        max_payload_bytes=1000,
        max_device_clock_skew_seconds=1,
        seq_tolerant=True,
    )

    request = _mk_request(company=company, branch=branch)

    # time skew -> quarantined
    occurred = timezone.now() - timedelta(seconds=120)
    cmd_skew = _build_cmd(
        priv=priv,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"msg": "hi"},
        occurred_at=occurred,
    )
    out = process_command(request=request, actor_user=None, device=device, cmd=cmd_skew, policy=policy)
    assert out["status"] == "REJECTED"
    assert out["reason"] == "SYNC_TIME_SKEW"
    device.refresh_from_db()
    assert device.status == Device.Status.QUARANTINED

    # forbidden scope
    device.status = Device.Status.ACTIVE
    device.save(update_fields=["status"])
    cmd_scope = _build_cmd(
        priv=priv,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=None,
        payload={"msg": "hi"},
    )
    out_scope = process_command(request=request, actor_user=None, device=device, cmd=cmd_scope, policy=policy)
    assert out_scope["status"] == "REJECTED"
    assert out_scope["reason"] == "SYNC_FORBIDDEN_SCOPE"

    # payload hash mismatch
    cmd_hash = _build_cmd(
        priv=priv,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"msg": "hi"},
        payload_hash_override="deadbeef",
        signature_override=_b64(b"0" * 64),
    )
    out_hash = process_command(request=request, actor_user=None, device=device, cmd=cmd_hash, policy=policy)
    assert out_hash["status"] == "REJECTED"
    assert out_hash["reason"] == "SYNC_SCHEMA_INVALID"

    # invalid signature
    cmd_sig = _build_cmd(
        priv=other_priv,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"msg": "hi"},
    )
    out_sig = process_command(request=request, actor_user=None, device=device, cmd=cmd_sig, policy=policy)
    assert out_sig["status"] == "REJECTED"
    assert out_sig["reason"] == "SYNC_INVALID_SIGNATURE"

    # unknown command type
    cmd_unknown = _build_cmd(
        priv=priv,
        command_type="UNKNOWN_TYPE",
        company_id=company.id,
        branch_id=branch.id,
        payload={"msg": "hi"},
    )
    out_unknown = process_command(request=request, actor_user=None, device=device, cmd=cmd_unknown, policy=policy)
    assert out_unknown["status"] == "REJECTED"
    assert out_unknown["reason"] == "SYNC_SCHEMA_INVALID"


@pytest.mark.django_db
def test_process_command_duplicate_and_payload_mismatch():
    company, branch = _mk_scope()
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()
    device = Device.objects.create(company=company, branch=branch, public_key=pub)

    policy = SyncPolicy(
        max_commands_per_batch=10,
        max_payload_bytes=1000,
        max_device_clock_skew_seconds=600,
        seq_tolerant=True,
    )

    request = _mk_request(company=company, branch=branch)
    cmd_id = str(uuid.uuid4())
    payload1 = {"msg": "one"}
    payload2 = {"msg": "two"}

    cmd1 = _build_cmd(
        priv=priv,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload=payload1,
        command_id=cmd_id,
    )
    out1 = process_command(request=request, actor_user=None, device=device, cmd=cmd1, policy=policy)
    assert out1["status"] == "APPLIED"

    out_dup = process_command(request=request, actor_user=None, device=device, cmd=cmd1, policy=policy)
    assert out_dup["status"] == "DUPLICATE"

    cmd2 = _build_cmd(
        priv=priv,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload=payload2,
        command_id=cmd_id,
    )
    out_mismatch = process_command(request=request, actor_user=None, device=device, cmd=cmd2, policy=policy)
    assert out_mismatch["status"] == "REJECTED"
    assert out_mismatch["reason"] == "SYNC_PAYLOAD_MISMATCH"


@pytest.mark.django_db
def test_sync_reject_error_str():
    err = SyncRejectError("INVENTORY_SCHEMA_INVALID", {"detail": "x"})
    assert str(err) == "INVENTORY_SCHEMA_INVALID"
