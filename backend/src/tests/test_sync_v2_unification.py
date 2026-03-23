from __future__ import annotations

import base64
import os
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit
from apps.modulos.sync.models import DeviceEnrollment
from apps.modulos.sync.signing import canonical_string as legacy_canonical_string
from apps.modulos.sync.signing import hmac_signature_b64 as legacy_hmac_signature_b64
from apps.modulos.sync_engine.models import AppliedCommand as CoreAppliedCommand
from apps.modulos.sync_engine.models import Device as CoreSyncDevice
from apps.modulos.sync_engine.signing import (
    build_command_signing_message,
    build_request_signing_message,
    canon_json,
    hmac_signature_b64,
    occurred_at_canonical,
    request_body_without_signature,
    sha256_hex,
)


@pytest.fixture(autouse=True)
def _clear_sync_throttle_cache():
    cache.clear()
    yield
    cache.clear()


def _create_company() -> OrgUnit:
    suffix = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"H-sync-{suffix}",
        code=f"H-sync-{suffix}",
    )
    return OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        name=f"C-sync-{suffix}",
        code=f"C-sync-{suffix}",
        parent=holding,
    )


def _sign_v2_hmac(payload: dict, *, secret_b64: str) -> dict:
    unsigned = request_body_without_signature(payload)
    message = build_request_signing_message(
        ts=int(payload["ts"]),
        nonce=str(payload["nonce"]),
        body_without_signature=unsigned,
    )
    payload["auth"]["signature"] = hmac_signature_b64(secret_b64, message)
    return payload


@pytest.mark.django_db
def test_sync_batch_v2_hmac_happy_path_and_replay():
    client = APIClient()
    company = _create_company()

    secret = base64.b64encode(os.urandom(32)).decode("utf-8")
    device = CoreSyncDevice.objects.create(
        company=company,
        branch=None,
        label="v2-hmac-device",
        public_key=os.urandom(32),
        hmac_secret_b64=secret,
    )

    ts = int(timezone.now().timestamp())
    nonce = "v2-nonce-001"
    command_id = str(uuid.uuid4())
    payload = {
        "protocol_version": "2",
        "device_id": str(device.id),
        "ts": ts,
        "nonce": nonce,
        "auth": {"scheme": "hmac", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": command_id,
                "type": "DEMO_PING",
                "scope": {"company_id": company.id, "branch_id": None},
                "occurred_at": timezone.now().isoformat(),
                "payload": {"msg": "ok"},
            }
        ],
    }
    _sign_v2_hmac(payload, secret_b64=secret)

    r1 = client.post("/api/sync/batch/", data=payload, format="json")
    assert r1.status_code == 200
    out = r1.json()
    assert out["results"][0]["status"] == "APPLIED"
    assert out["results"][0]["refs"]["pong"] is True

    r2 = client.post("/api/sync/batch/", data=payload, format="json")
    assert r2.status_code == 401
    err = r2.json()["error"]
    assert err["code"] == "AUTH_UNAUTHENTICATED"
    assert err["message"] == "REPLAY_DETECTED"


@pytest.mark.django_db
def test_sync_batch_v2_hmac_bad_signature_rejected():
    client = APIClient()
    company = _create_company()

    secret = base64.b64encode(os.urandom(32)).decode("utf-8")
    device = CoreSyncDevice.objects.create(
        company=company,
        branch=None,
        label="v2-hmac-device-badsig",
        public_key=os.urandom(32),
        hmac_secret_b64=secret,
    )

    payload = {
        "protocol_version": "2",
        "device_id": str(device.id),
        "ts": int(timezone.now().timestamp()),
        "nonce": "v2-nonce-badsig",
        "auth": {"scheme": "hmac", "signature": "invalidsig=="},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": str(uuid.uuid4()),
                "type": "DEMO_PING",
                "scope": {"company_id": company.id, "branch_id": None},
                "occurred_at": timezone.now().isoformat(),
                "payload": {"msg": "ok"},
            }
        ],
    }

    r = client.post("/api/sync/batch/", data=payload, format="json")
    assert r.status_code == 401
    err = r.json()["error"]
    assert err["code"] == "AUTH_UNAUTHENTICATED"
    assert err["message"] == "BAD_SIGNATURE"


@pytest.mark.django_db
def test_sync_hmac_wrapper_uses_core_and_preserves_legacy_shape():
    client = APIClient()
    secret = base64.b64encode(os.urandom(32)).decode("utf-8")
    device = DeviceEnrollment.objects.create(secret_b64=secret, device_name="legacy-wrapper")

    command_id = str(uuid.uuid4())
    body = {"commands": [{"command_id": command_id, "type": "PING", "payload": {"x": 1}}]}
    raw = JSONRenderer().render(body)
    ts = int(timezone.now().timestamp())
    nonce = "legacy-nonce-1"
    sig = legacy_hmac_signature_b64(secret, legacy_canonical_string(ts=ts, nonce=nonce, raw_body=raw))

    res = client.post(
        "/api/sync-hmac/batch/",
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
        HTTP_X_DEVICE_TS=str(ts),
        HTTP_X_DEVICE_NONCE=nonce,
        HTTP_X_DEVICE_SIGNATURE=sig,
    )
    assert res.status_code == 200
    out = res.json()
    assert out["device_id"] == str(device.id)
    assert out["results"][0]["result"]["status"] == "OK"
    assert out["results"][0]["result"]["data"]["pong"] is True
    assert res["Deprecation"] == "true"
    assert res.get("Sunset") in (None, "")
    assert "CONTRACT_PACK_v2.0.md" in res["Link"]

    device.refresh_from_db()
    assert device.core_device_id is not None
    assert CoreAppliedCommand.objects.filter(device_id=device.core_device_id, command_id=command_id).count() == 1


@pytest.mark.django_db
def test_sync_hmac_wrapper_replay_detected_by_core_nonce():
    client = APIClient()
    secret = base64.b64encode(os.urandom(32)).decode("utf-8")
    device = DeviceEnrollment.objects.create(secret_b64=secret, device_name="legacy-wrapper-replay")

    body = {"commands": [{"command_id": str(uuid.uuid4()), "type": "PING", "payload": {}}]}
    raw = JSONRenderer().render(body)
    ts = int(timezone.now().timestamp())
    nonce = "legacy-replay-core"
    sig = legacy_hmac_signature_b64(secret, legacy_canonical_string(ts=ts, nonce=nonce, raw_body=raw))

    r1 = client.post(
        "/api/sync-hmac/batch/",
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
        HTTP_X_DEVICE_TS=str(ts),
        HTTP_X_DEVICE_NONCE=nonce,
        HTTP_X_DEVICE_SIGNATURE=sig,
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/sync-hmac/batch/",
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
        HTTP_X_DEVICE_TS=str(ts),
        HTTP_X_DEVICE_NONCE=nonce,
        HTTP_X_DEVICE_SIGNATURE=sig,
    )
    assert r2.status_code == 401
    assert r2.json()["error"]["message"] == "REPLAY_DETECTED"


@pytest.mark.django_db
def test_sync_batch_legacy_schema_still_supported():
    client = APIClient()
    company = _create_company()

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    device = CoreSyncDevice.objects.create(
        company=company,
        branch=None,
        label="legacy-schema-device",
        public_key=public_key,
    )

    occurred_at = timezone.now()
    payload = {"msg": "legacy"}
    payload_hash = sha256_hex(canon_json(payload))
    command_id = str(uuid.uuid4())
    signing_message = build_command_signing_message(
        command_id=command_id,
        command_type="DEMO_PING",
        company_id=company.id,
        branch_id=None,
        occurred_at=occurred_at_canonical(occurred_at),
        sequence=1,
        payload_hash=payload_hash,
        prev_hash="",
    )
    signature = base64.b64encode(private_key.sign(signing_message)).decode("utf-8")

    body = {
        "batch_id": str(uuid.uuid4()),
        "device_id": str(device.id),
        "commands": [
            {
                "command_id": command_id,
                "command_type": "DEMO_PING",
                "company_id": company.id,
                "branch_id": None,
                "occurred_at": occurred_at.isoformat(),
                "sequence": 1,
                "payload": payload,
                "payload_hash": payload_hash,
                "prev_hash": "",
                "signature": signature,
            }
        ],
    }

    res = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(device.id))
    assert res.status_code == 200
    out = res.json()
    assert out["results"][0]["status"] == "APPLIED"
    assert out["results"][0]["refs"]["pong"] is True


@pytest.mark.django_db
@override_settings(SYNC_HMAC_LEGACY_SUNSET="2030-01-01T00:00:00Z")
def test_sync_hmac_wrapper_includes_sunset_when_configured():
    client = APIClient()
    res = client.post("/api/sync-hmac/batch/", data={}, format="json")
    assert res.status_code == 400
    assert res["Deprecation"] == "true"
    assert res["Sunset"] == "2030-01-01T00:00:00Z"
    assert "CONTRACT_PACK_v2.0.md" in res["Link"]


@pytest.mark.django_db
def test_sync_batch_v2_hmac_ts_out_of_window_rejected():
    client = APIClient()
    company = _create_company()
    secret = base64.b64encode(os.urandom(32)).decode("utf-8")
    device = CoreSyncDevice.objects.create(
        company=company,
        branch=None,
        label="v2-hmac-device-ts",
        public_key=os.urandom(32),
        hmac_secret_b64=secret,
    )

    payload = {
        "protocol_version": "2",
        "device_id": str(device.id),
        "ts": int(timezone.now().timestamp()) - 7200,
        "nonce": "v2-nonce-stale",
        "auth": {"scheme": "hmac", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": str(uuid.uuid4()),
                "type": "DEMO_PING",
                "scope": {"company_id": company.id, "branch_id": None},
                "occurred_at": timezone.now().isoformat(),
                "payload": {"msg": "ok"},
            }
        ],
    }
    _sign_v2_hmac(payload, secret_b64=secret)

    res = client.post("/api/sync/batch/", data=payload, format="json")
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "AUTH_UNAUTHENTICATED"
    assert err["message"] == "TS_OUT_OF_WINDOW"


@pytest.mark.django_db
def test_sync_cross_endpoint_equivalence_and_idempotency():
    client = APIClient()
    secret = base64.b64encode(os.urandom(32)).decode("utf-8")
    legacy_device = DeviceEnrollment.objects.create(secret_b64=secret, device_name="legacy-cross-endpoint")

    # 1) APPLIED via legacy wrapper
    command_id_legacy = str(uuid.uuid4())
    body_legacy = {"commands": [{"command_id": command_id_legacy, "type": "PING", "payload": {"x": 1}}]}
    raw_legacy = JSONRenderer().render(body_legacy)
    ts_legacy = int(timezone.now().timestamp())
    nonce_legacy = "legacy-cross-1"
    sig_legacy = legacy_hmac_signature_b64(
        secret,
        legacy_canonical_string(ts=ts_legacy, nonce=nonce_legacy, raw_body=raw_legacy),
    )
    r_legacy = client.post(
        "/api/sync-hmac/batch/",
        data=body_legacy,
        format="json",
        HTTP_X_DEVICE_ID=str(legacy_device.id),
        HTTP_X_DEVICE_TS=str(ts_legacy),
        HTTP_X_DEVICE_NONCE=nonce_legacy,
        HTTP_X_DEVICE_SIGNATURE=sig_legacy,
    )
    assert r_legacy.status_code == 200
    assert r_legacy.json()["results"][0]["result"]["status"] == "OK"

    legacy_device.refresh_from_db()
    assert legacy_device.core_device_id is not None
    core_device_id = str(legacy_device.core_device_id)

    # 2) APPLIED via v2 sobre mismo core con mismo handler de negocio (PING)
    command_id_v2 = str(uuid.uuid4())
    payload_v2 = {
        "protocol_version": "2",
        "device_id": core_device_id,
        "ts": int(timezone.now().timestamp()),
        "nonce": "v2-cross-2",
        "auth": {"scheme": "hmac", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": command_id_v2,
                "type": "PING",
                "scope": {"company_id": legacy_device.core_device.company_id, "branch_id": None},
                "occurred_at": timezone.now().isoformat(),
                "payload": {"x": 1},
            }
        ],
    }
    _sign_v2_hmac(payload_v2, secret_b64=secret)
    r_v2 = client.post("/api/sync/batch/", data=payload_v2, format="json")
    assert r_v2.status_code == 200
    out_v2 = r_v2.json()
    assert out_v2["results"][0]["status"] == "APPLIED"
    assert out_v2["results"][0]["refs"]["pong"] is True
    assert out_v2["results"][0]["refs"]["echo"] == {"x": 1}

    # 3) Idempotencia cross-endpoint: reenviar command_id_v2 por legacy => DUPLICATE mapeado a OK
    body_legacy_dup = {"commands": [{"command_id": command_id_v2, "type": "PING", "payload": {"x": 1}}]}
    raw_legacy_dup = JSONRenderer().render(body_legacy_dup)
    ts_legacy_dup = int(timezone.now().timestamp())
    nonce_legacy_dup = "legacy-cross-3"
    sig_legacy_dup = legacy_hmac_signature_b64(
        secret,
        legacy_canonical_string(ts=ts_legacy_dup, nonce=nonce_legacy_dup, raw_body=raw_legacy_dup),
    )
    r_legacy_dup = client.post(
        "/api/sync-hmac/batch/",
        data=body_legacy_dup,
        format="json",
        HTTP_X_DEVICE_ID=str(legacy_device.id),
        HTTP_X_DEVICE_TS=str(ts_legacy_dup),
        HTTP_X_DEVICE_NONCE=nonce_legacy_dup,
        HTTP_X_DEVICE_SIGNATURE=sig_legacy_dup,
    )
    assert r_legacy_dup.status_code == 200
    out_legacy_dup = r_legacy_dup.json()
    assert out_legacy_dup["results"][0]["result"]["status"] == "OK"
    assert out_legacy_dup["results"][0]["result"]["data"]["pong"] is True
