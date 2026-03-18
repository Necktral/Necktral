import base64
import uuid
from types import SimpleNamespace
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apps.iam.models import OrgUnit
from apps.sync_engine.errors import SyncRejectError
from apps.sync_engine.models import AppliedCommand, Device
from apps.sync_engine.registry import register
from apps.sync_engine import services as sync_services
from apps.sync_engine.services import (
    SyncPolicy,
    enforce_device_active,
    ensure_scope_matches,
    process_batch,
    process_command,
    resolve_device,
)
from apps.sync_engine.signing import (
    build_command_signing_message,
    canon_json,
    occurred_at_canonical,
    sha256_hex,
    sha256_hex_bytes,
)


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _request(company: OrgUnit, branch: OrgUnit | None):
    return SimpleNamespace(company=company, branch=branch, META={}, path="/", method="POST")


def _device_with_key(company: OrgUnit, branch: OrgUnit | None):
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()
    device = Device.objects.create(company=company, branch=branch, public_key=pub, label="dev")
    return device, priv


def _build_command(
    *,
    priv: Ed25519PrivateKey,
    command_id: str,
    command_type: str,
    company_id: int,
    branch_id: int,
    payload: dict,
    sequence: int = 1,
    occurred_at=None,
    signature: str | None = None,
    payload_hash: str | None = None,
):
    occurred_dt = occurred_at or timezone.now()
    occurred_canon = occurred_at_canonical(occurred_dt)
    payload_hash = payload_hash or sha256_hex(canon_json(payload))
    msg = build_command_signing_message(
        command_id=command_id,
        command_type=command_type,
        company_id=company_id,
        branch_id=branch_id,
        occurred_at=occurred_canon,
        sequence=sequence,
        payload_hash=payload_hash,
        prev_hash="",
    )
    sig = signature or _b64(priv.sign(msg))
    return {
        "command_id": command_id,
        "command_type": command_type,
        "company_id": company_id,
        "branch_id": branch_id,
        "occurred_at": occurred_dt,
        "sequence": sequence,
        "payload": payload,
        "payload_hash": payload_hash,
        "prev_hash": "",
        "signature": sig,
    }


@pytest.mark.django_db
def test_process_command_payload_limit_exceeded():
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
            command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"data": "x" * 100},
    )

    policy = SyncPolicy(max_commands_per_batch=10, max_payload_bytes=10, max_device_clock_skew_seconds=3600, seq_tolerant=True)
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd, policy=policy)
    assert out["reason"] == "SYNC_LIMIT_EXCEEDED"


@pytest.mark.django_db
def test_process_command_handler_reject_and_crash():
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    @register("COVER_REJECT")
    def _rejecting(_ctx, _payload):
        raise SyncRejectError("INVENTORY_SCHEMA_INVALID", {"detail": "bad"})

    @register("COVER_CRASH")
    def _crashing(_ctx, _payload):
        raise RuntimeError("boom")

    cmd_reject = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type="COVER_REJECT",
        company_id=company.id,
        branch_id=branch.id,
        payload={"x": 1},
    )

    policy = SyncPolicy(max_commands_per_batch=10, max_payload_bytes=1000, max_device_clock_skew_seconds=3600, seq_tolerant=True)
    out_reject = process_command(request=req, actor_user=None, device=device, cmd=cmd_reject, policy=policy)
    assert out_reject["status"] == "REJECTED"
    assert out_reject["reason"] == "INVENTORY_SCHEMA_INVALID"
    assert out_reject["details"]["detail"] == "bad"

    cmd_crash = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type="COVER_CRASH",
        company_id=company.id,
        branch_id=branch.id,
        payload={"x": 1},
    )

    out_crash = process_command(request=req, actor_user=None, device=device, cmd=cmd_crash, policy=policy)
    assert out_crash["status"] == "REJECTED"
    assert out_crash["reason"] == "SYNC_INTERNAL_ERROR"


@pytest.mark.django_db
def test_resolve_device_and_enforce_active():
    company, branch = _mk_scope()
    device, _ = _device_with_key(company, branch)

    assert resolve_device(device_id=str(device.id)).id == device.id

    device.status = Device.Status.REVOKED
    device.save(update_fields=["status"])
    with pytest.raises(Exception):
        enforce_device_active(device)

    device.status = Device.Status.QUARANTINED
    device.save(update_fields=["status"])
    with pytest.raises(Exception):
        enforce_device_active(device)

    with pytest.raises(Exception):
        resolve_device(device_id=str(uuid.uuid4()))


@pytest.mark.django_db
def test_process_batch_handles_internal_errors(monkeypatch):
    company, branch = _mk_scope()
    device, _ = _device_with_key(company, branch)
    req = _request(company, branch)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(sync_services, "process_command", _boom)

    out = process_batch(
        request=req,
        actor_user=None,
        device=device,
        batch_id=uuid.uuid4(),
        sent_at=timezone.now(),
        commands=[{"command_id": "c1", "command_type": "DEMO_PING"}],
    )

    assert out["summary"]["rejected"] == 1
    assert out["results"][0]["reason"] == "SYNC_INTERNAL_ERROR"


@pytest.mark.django_db
def test_ensure_scope_matches_company_branch():
    company, branch = _mk_scope()
    other_company, other_branch = _mk_scope()
    device, _ = _device_with_key(company, None)

    assert ensure_scope_matches(device=device, company_id=company.id, branch_id=branch.id) is True
    assert ensure_scope_matches(device=device, company_id=other_company.id, branch_id=other_branch.id) is False


@pytest.mark.django_db
def test_process_command_device_status_rejected():
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)
    cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
            command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"ping": True},
    )

    device.status = Device.Status.REVOKED
    device.save(update_fields=["status"])
    policy = SyncPolicy(max_commands_per_batch=10, max_payload_bytes=1000, max_device_clock_skew_seconds=3600, seq_tolerant=True)
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd, policy=policy)
    assert out["reason"] == "SYNC_DEVICE_REVOKED"

    device.status = Device.Status.QUARANTINED
    device.save(update_fields=["status"])
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd, policy=policy)
    assert out["reason"] == "SYNC_DEVICE_QUARANTINED"


@pytest.mark.django_db
def test_process_command_time_skew_quarantines_device():
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    old = timezone.now() - timedelta(days=2)
    cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
            command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        occurred_at=old,
        payload={"ping": True},
    )

    policy = SyncPolicy(max_commands_per_batch=10, max_payload_bytes=1000, max_device_clock_skew_seconds=1, seq_tolerant=True)
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd, policy=policy)
    device.refresh_from_db()
    assert out["reason"] == "SYNC_TIME_SKEW"
    assert device.status == Device.Status.QUARANTINED


@pytest.mark.django_db
def test_process_command_payload_hash_mismatch():
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
            command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"ping": True},
        payload_hash="bad",
    )

    policy = SyncPolicy(max_commands_per_batch=10, max_payload_bytes=1000, max_device_clock_skew_seconds=3600, seq_tolerant=True)
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd, policy=policy)
    assert out["reason"] == "SYNC_SCHEMA_INVALID"


@pytest.mark.django_db
def test_process_command_with_warnings():
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    warn_type = f"WARN_{uuid.uuid4().hex}"

    @register(warn_type)
    def _warn(_ctx, _payload):
        return {"warnings": ["low_stock"]}

    cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type=warn_type,
        company_id=company.id,
        branch_id=branch.id,
        payload={"x": 1},
    )

    policy = SyncPolicy(max_commands_per_batch=10, max_payload_bytes=1000, max_device_clock_skew_seconds=3600, seq_tolerant=True)
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd, policy=policy)
    assert out["status"] == "APPLIED"
    assert out["warnings"] == ["low_stock"]


@pytest.mark.django_db
def test_process_command_canon_json_error_rejected(monkeypatch):
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"ping": True},
    )

    def _boom(_payload):
        raise ValueError("bad json")

    monkeypatch.setattr(sync_services, "canon_json", _boom)

    policy = SyncPolicy(max_commands_per_batch=10, max_payload_bytes=1000, max_device_clock_skew_seconds=3600, seq_tolerant=True)
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd, policy=policy)
    assert out["reason"] == "SYNC_INVALID_SIGNATURE"


@pytest.mark.django_db
def test_process_command_invalid_signature_and_unknown_handler():
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    cmd_invalid_sig = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
            command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"ping": True},
        signature=_b64(b"invalid"),
    )

    policy = SyncPolicy(max_commands_per_batch=10, max_payload_bytes=1000, max_device_clock_skew_seconds=3600, seq_tolerant=True)
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd_invalid_sig, policy=policy)
    assert out["reason"] == "SYNC_INVALID_SIGNATURE"

    cmd_unknown = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type="UNKNOWN_COMMAND",
        company_id=company.id,
        branch_id=branch.id,
        payload={"ping": True},
    )
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd_unknown, policy=policy)
    assert out["reason"] == "SYNC_SCHEMA_INVALID"


@pytest.mark.django_db
def test_process_command_reject_and_internal_error_paths():
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    reject_type = f"REJECT_{uuid.uuid4().hex}"
    crash_type = f"CRASH_{uuid.uuid4().hex}"

    @register(reject_type)
    def _reject_handler(ctx, payload):
        raise SyncRejectError("INVENTORY_SCHEMA_INVALID", {"detail": "bad"})

    @register(crash_type)
    def _crash_handler(ctx, payload):
        raise RuntimeError("boom")

    cmd_reject = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type=reject_type,
        company_id=company.id,
        branch_id=branch.id,
        payload={"x": 1},
    )
    cmd_crash = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type=crash_type,
        company_id=company.id,
        branch_id=branch.id,
        payload={"x": 1},
    )
    policy = SyncPolicy(max_commands_per_batch=10, max_payload_bytes=1000, max_device_clock_skew_seconds=3600, seq_tolerant=True)

    out = process_command(request=req, actor_user=None, device=device, cmd=cmd_reject, policy=policy)
    assert out["reason"] == "INVENTORY_SCHEMA_INVALID"

    out = process_command(request=req, actor_user=None, device=device, cmd=cmd_crash, policy=policy)
    assert out["reason"] == "SYNC_INTERNAL_ERROR"


@pytest.mark.django_db
def test_process_command_duplicate_and_mismatch():
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    payload = {"ping": True}
    payload_hash = sha256_hex(canon_json(payload))
    cmd_id = uuid.uuid4()

    AppliedCommand.objects.create(
        command_id=cmd_id,
        device=device,
        company=company,
        branch=branch,
            command_type="DEMO_PING",
        occurred_at=timezone.now(),
        sequence=1,
        payload_hash=payload_hash,
        prev_hash="",
        result_status=AppliedCommand.ResultStatus.APPLIED,
        result_ref={"pong": True},
        error={},
    )

    cmd = _build_command(
        priv=priv,
        command_id=str(cmd_id),
            command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload=payload,
        payload_hash=payload_hash,
    )

    policy = SyncPolicy(max_commands_per_batch=10, max_payload_bytes=1000, max_device_clock_skew_seconds=3600, seq_tolerant=True)
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd, policy=policy)
    assert out["status"] == "DUPLICATE"

    cmd_bad = _build_command(
        priv=priv,
        command_id=str(cmd_id),
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"ping": False},
    )
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd_bad, policy=policy)
    assert out["reason"] == "SYNC_PAYLOAD_MISMATCH"


@pytest.mark.django_db
def test_process_command_integrity_error_paths(monkeypatch):
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    payload = {"ping": True}
    payload_hash = sha256_hex(canon_json(payload))
    cmd_id = uuid.uuid4()

    existing = AppliedCommand.objects.create(
        command_id=cmd_id,
        device=device,
        company=company,
        branch=branch,
        command_type="DEMO_PING",
        occurred_at=timezone.now(),
        sequence=1,
        payload_hash=payload_hash,
        prev_hash="",
        result_status=AppliedCommand.ResultStatus.APPLIED,
        result_ref={"pong": True},
        error={},
    )

    class _FakeSelect:
        def __init__(self, row):
            self._row = row

        def filter(self, *args, **kwargs):
            class _FakeFilter:
                def first(self_inner):
                    return None

            return _FakeFilter()

        def get(self, *args, **kwargs):
            return self._row

    def _raise_integrity(*_args, **_kwargs):
        raise IntegrityError("forced")

    monkeypatch.setattr(AppliedCommand.objects, "select_for_update", lambda *args, **kwargs: _FakeSelect(existing))
    monkeypatch.setattr(AppliedCommand.objects, "create", _raise_integrity)

    cmd = _build_command(
        priv=priv,
        command_id=str(cmd_id),
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload=payload,
        payload_hash=payload_hash,
    )

    policy = SyncPolicy(max_commands_per_batch=10, max_payload_bytes=1000, max_device_clock_skew_seconds=3600, seq_tolerant=True)
    out = process_command(request=req, actor_user=None, device=device, cmd=cmd, policy=policy)
    assert out["status"] == "DUPLICATE"

    existing.payload_hash = "other"
    existing.save(update_fields=["payload_hash"])

    cmd_bad = _build_command(
        priv=priv,
        command_id=str(cmd_id),
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"ping": False},
    )
    out_bad = process_command(request=req, actor_user=None, device=device, cmd=cmd_bad, policy=policy)
    assert out_bad["reason"] == "SYNC_PAYLOAD_MISMATCH"


@pytest.mark.django_db
def test_process_batch_limit_exceeded(settings):
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    settings.SYNC_MAX_COMMANDS_PER_BATCH = 1

    cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
            command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"ping": True},
    )
    cmd2 = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
            command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"ping": True},
    )

    out = process_batch(
        request=req,
        actor_user=None,
        device=device,
        batch_id=uuid.uuid4(),
        sent_at=timezone.now(),
        commands=[cmd, cmd2],
    )

    assert out["errors"][0]["reason"] == "SYNC_LIMIT_EXCEEDED"


@pytest.mark.django_db
def test_process_batch_applies_and_updates_receipt():
    company, branch = _mk_scope()
    device, priv = _device_with_key(company, branch)
    req = _request(company, branch)

    cmd = _build_command(
        priv=priv,
        command_id=str(uuid.uuid4()),
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=branch.id,
        payload={"msg": "ok"},
    )

    out = process_batch(
        request=req,
        actor_user=None,
        device=device,
        batch_id=uuid.uuid4(),
        sent_at=timezone.now(),
        commands=[cmd],
    )
    assert out["summary"]["applied"] == 1


@pytest.mark.django_db
def test_signing_helpers_invalid_public_key():
    from apps.sync_engine.signing import public_key_from_b64, verify_ed25519_signature

    with pytest.raises(ValueError):
        public_key_from_b64(_b64(b"short"))

    assert verify_ed25519_signature(public_key_raw=b"short", signature_b64=_b64(b"sig"), message=b"msg") is False

    assert sha256_hex_bytes(b"abc") == sha256_hex("abc")


@pytest.mark.django_db
def test_registry_duplicate_handler_and_reject_with_db_paths(monkeypatch):
    command_type = f"DUP_{uuid.uuid4().hex}"

    @register(command_type)
    def _noop(ctx, payload):
        return {"refs": {"ok": True}}

    with pytest.raises(RuntimeError):
        @register(command_type)
        def _dup(ctx, payload):
            return {"refs": {"dup": True}}

    company, branch = _mk_scope()
    device, _ = _device_with_key(company, branch)
    req = _request(company, branch)
    cmd_id = uuid.uuid4()

    AppliedCommand.objects.create(
        command_id=cmd_id,
        device=device,
        company=company,
        branch=branch,
        command_type=command_type,
        occurred_at=timezone.now(),
        sequence=1,
        payload_hash="hash1",
        prev_hash="",
        result_status=AppliedCommand.ResultStatus.REJECTED,
        result_ref={"ref": "x"},
        error={"reason": "SYNC_INVALID_SIGNATURE"},
    )

    def _raise_integrity(*_args, **_kwargs):
        raise IntegrityError("forced")

    monkeypatch.setattr(AppliedCommand.objects, "create", _raise_integrity)

    out = sync_services._reject_with_db(
        request=req,
        actor_user=None,
        device=device,
        command_id=cmd_id,
        company_id=company.id,
        branch_id=branch.id,
        command_type=command_type,
        occurred_at=timezone.now(),
        sequence=1,
        payload_hash="hash1",
        prev_hash="",
        reason="SYNC_INVALID_SIGNATURE",
        details={},
    )
    assert out["status"] == "DUPLICATE"

    out = sync_services._reject_with_db(
        request=req,
        actor_user=None,
        device=device,
        command_id=cmd_id,
        company_id=company.id,
        branch_id=branch.id,
        command_type=command_type,
        occurred_at=timezone.now(),
        sequence=1,
        payload_hash="hash2",
        prev_hash="",
        reason="SYNC_INVALID_SIGNATURE",
        details={},
    )
    assert out["reason"] == "SYNC_PAYLOAD_MISMATCH"


@pytest.mark.django_db
def test_reject_with_db_handles_missing_row(monkeypatch):
    company, branch = _mk_scope()
    device, _ = _device_with_key(company, branch)
    req = _request(company, branch)

    def _raise_integrity(*_args, **_kwargs):
        raise IntegrityError("forced")

    class _FakeQS:
        def first(self):
            return None

    monkeypatch.setattr(AppliedCommand.objects, "create", _raise_integrity)
    monkeypatch.setattr(AppliedCommand.objects, "filter", lambda *args, **kwargs: _FakeQS())

    out = sync_services._reject_with_db(
        request=req,
        actor_user=None,
        device=device,
        command_id=uuid.uuid4(),
        company_id=company.id,
        branch_id=branch.id,
        command_type="DEMO_PING",
        occurred_at=timezone.now(),
        sequence=1,
        payload_hash="hash1",
        prev_hash="",
        reason="SYNC_INVALID_SIGNATURE",
        details={},
    )
    assert out["reason"] == "SYNC_INVALID_SIGNATURE"


@pytest.mark.django_db
def test_reject_with_db_handles_exception(monkeypatch):
    company, branch = _mk_scope()
    device, _ = _device_with_key(company, branch)
    req = _request(company, branch)

    def _raise_error(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(AppliedCommand.objects, "create", _raise_error)

    out = sync_services._reject_with_db(
        request=req,
        actor_user=None,
        device=device,
        command_id=uuid.uuid4(),
        company_id=company.id,
        branch_id=branch.id,
        command_type="DEMO_PING",
        occurred_at=timezone.now(),
        sequence=1,
        payload_hash="hash1",
        prev_hash="",
        reason="SYNC_INVALID_SIGNATURE",
        details={},
    )
    assert out["reason"] == "SYNC_INVALID_SIGNATURE"


@pytest.mark.django_db
def test_reject_with_db_successful_write():
    company, branch = _mk_scope()
    device, _ = _device_with_key(company, branch)
    req = _request(company, branch)

    out = sync_services._reject_with_db(
        request=req,
        actor_user=None,
        device=device,
        command_id=uuid.uuid4(),
        company_id=company.id,
        branch_id=branch.id,
        command_type="DEMO_PING",
        occurred_at=timezone.now(),
        sequence=1,
        payload_hash="hash1",
        prev_hash="",
        reason="SYNC_INVALID_SIGNATURE",
        details={"detail": "x"},
    )
    assert out["reason"] == "SYNC_INVALID_SIGNATURE"
