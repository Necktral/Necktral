from __future__ import annotations

import base64
import os
import uuid

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.settings import api_settings
from django.utils import timezone
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIClient

from apps.sync.models import DeviceEnrollment, DeviceRequestNonce
from apps.sync.signing import canonical_string, hmac_signature_b64


@pytest.mark.django_db
def test_sync_batch_happy_path(settings):
    client = APIClient()

    secret = base64.b64encode(os.urandom(32)).decode("utf-8")
    device = DeviceEnrollment.objects.create(secret_b64=secret, device_name="t1")

    body = {
        "commands": [
            {"command_id": str(uuid.uuid4()), "type": "PING", "payload": {"x": 1}},
        ]
    }

    # Importante: el raw_body debe coincidir con el JSON que envía APIClient(format="json")
    raw = JSONRenderer().render(body)

    ts = int(timezone.now().timestamp())
    nonce = "nonce-1234567890abcdef"
    canon = canonical_string(ts=ts, nonce=nonce, raw_body=raw)
    sig = hmac_signature_b64(secret, canon)

    url = "/api/sync-hmac/batch/"  # endpoint HMAC (no colisiona con apps.sync_engine)
    res = client.post(
        url,
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
        HTTP_X_DEVICE_TS=str(ts),
        HTTP_X_DEVICE_NONCE=nonce,
        HTTP_X_DEVICE_SIGNATURE=sig,
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["device_id"] == str(device.id)
    assert payload["results"][0]["result"]["status"] == "OK"
    assert payload["results"][0]["result"]["data"]["pong"] is True


@pytest.mark.django_db
def test_sync_batch_bad_signature_rejected():
    client = APIClient()

    secret = base64.b64encode(os.urandom(32)).decode("utf-8")
    device = DeviceEnrollment.objects.create(secret_b64=secret, device_name="t1")

    body = {"commands": [{"command_id": str(uuid.uuid4()), "type": "PING", "payload": {}}]}
    ts = int(timezone.now().timestamp())
    nonce = "nonce-aaaaaaaaaaaaaaaa"
    url = "/api/sync-hmac/batch/"

    res = client.post(
        url,
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
        HTTP_X_DEVICE_TS=str(ts),
        HTTP_X_DEVICE_NONCE=nonce,
        HTTP_X_DEVICE_SIGNATURE="invalidsig==",
    )
    assert res.status_code == 401
    payload = res.json()
    assert payload["error"]["code"] == "AUTH_UNAUTHENTICATED"
    assert payload["error"]["message"] == "BAD_SIGNATURE"
    assert DeviceRequestNonce.objects.filter(device=device).count() == 0


@pytest.mark.django_db
def test_sync_batch_replay_nonce_rejected():
    client = APIClient()

    secret = base64.b64encode(os.urandom(32)).decode("utf-8")
    device = DeviceEnrollment.objects.create(secret_b64=secret, device_name="t1")

    cmd_id = str(uuid.uuid4())
    body = {"commands": [{"command_id": cmd_id, "type": "PING", "payload": {"a": 1}}]}
    raw = JSONRenderer().render(body)

    ts = int(timezone.now().timestamp())
    nonce = "nonce-replay-1234567890"
    canon = canonical_string(ts=ts, nonce=nonce, raw_body=raw)
    sig = hmac_signature_b64(secret, canon)

    url = "/api/sync-hmac/batch/"

    # 1st request OK
    r1 = client.post(
        url,
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
        HTTP_X_DEVICE_TS=str(ts),
        HTTP_X_DEVICE_NONCE=nonce,
        HTTP_X_DEVICE_SIGNATURE=sig,
    )
    assert r1.status_code == 200

    # 2nd request same nonce => replay detected
    r2 = client.post(
        url,
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
        HTTP_X_DEVICE_TS=str(ts),
        HTTP_X_DEVICE_NONCE=nonce,
        HTTP_X_DEVICE_SIGNATURE=sig,
    )
    assert r2.status_code == 401
    payload = r2.json()
    assert payload["error"]["code"] == "AUTH_UNAUTHENTICATED"
    assert payload["error"]["message"] == "REPLAY_DETECTED"


@pytest.mark.django_db
def test_idempotency_same_command_id_returns_cached(monkeypatch):
    client = APIClient()

    secret = base64.b64encode(os.urandom(32)).decode("utf-8")
    device = DeviceEnrollment.objects.create(secret_b64=secret, device_name="t1")

    # contamos llamadas del handler real via monkeypatch
    from apps.sync import handlers as h

    calls = {"n": 0}

    def fake_ping(_device, _cmd):
        calls["n"] += 1
        return {"pong": True}

    monkeypatch.setitem(h.HANDLERS, "PING", fake_ping)

    command_id = str(uuid.uuid4())
    body = {"commands": [{"command_id": command_id, "type": "PING", "payload": {}}]}
    raw = JSONRenderer().render(body)

    ts = int(timezone.now().timestamp())
    nonce1 = "nonce-1-xxxxxxxxxxxxxxxx"
    sig1 = hmac_signature_b64(secret, canonical_string(ts, nonce1, raw))

    url = "/api/sync-hmac/batch/"

    r1 = client.post(
        url,
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
        HTTP_X_DEVICE_TS=str(ts),
        HTTP_X_DEVICE_NONCE=nonce1,
        HTTP_X_DEVICE_SIGNATURE=sig1,
    )
    assert r1.status_code == 200

    # reenviamos el mismo command_id pero con nonce distinto (no es replay)
    nonce2 = "nonce-2-yyyyyyyyyyyyyyyy"
    sig2 = hmac_signature_b64(secret, canonical_string(ts, nonce2, raw))

    r2 = client.post(
        url,
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
        HTTP_X_DEVICE_TS=str(ts),
        HTTP_X_DEVICE_NONCE=nonce2,
        HTTP_X_DEVICE_SIGNATURE=sig2,
    )
    assert r2.status_code == 200

    assert calls["n"] == 1  # el handler solo corre una vez por command_id


@pytest.mark.django_db
def test_sync_batch_missing_headers_envelope_and_request_id():
    client = APIClient()

    res = client.post("/api/sync-hmac/batch/", data={}, format="json")

    assert res.status_code == 400
    payload = res.json()
    assert payload["error"]["code"] == "BAD_REQUEST"
    assert payload["error"]["message"] == "MISSING_HEADERS"
    assert res["X-Request-Id"] == payload["error"]["request_id"]


@pytest.mark.django_db
def test_sync_batch_invalid_request_id_sanitized():
    client = APIClient()

    res = client.post(
        "/api/sync-hmac/batch/",
        data={},
        format="json",
        HTTP_X_REQUEST_ID="bad\nvalue",
    )

    assert res.status_code == 400
    assert res["X-Request-Id"] != "bad\nvalue"


@pytest.mark.django_db
def test_sync_batch_throttling_enveloped():
    override = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (
            "rest_framework.throttling.AnonRateThrottle",
            "rest_framework.throttling.UserRateThrottle",
            "rest_framework.throttling.ScopedRateThrottle",
            "config.throttling.DeviceScopedRateThrottle",
        ),
        "DEFAULT_THROTTLE_RATES": {
            "anon": "1000/min",
            "user": "1000/min",
            "sync_batch": "1/min",
        },
    }

    with override_settings(REST_FRAMEWORK=override):
        cache.clear()
        api_settings.reload()

        client = APIClient()

        secret = base64.b64encode(os.urandom(32)).decode("utf-8")
        device = DeviceEnrollment.objects.create(secret_b64=secret, device_name="t1")

        body = {"commands": [{"command_id": str(uuid.uuid4()), "type": "PING", "payload": {}}]}
        raw = JSONRenderer().render(body)

        ts = int(timezone.now().timestamp())
        nonce1 = "nonce-throttle-1"
        sig1 = hmac_signature_b64(secret, canonical_string(ts, nonce1, raw))

        url = "/api/sync-hmac/batch/"

        r1 = client.post(
            url,
            data=body,
            format="json",
            HTTP_X_DEVICE_ID=str(device.id),
            HTTP_X_DEVICE_TS=str(ts),
            HTTP_X_DEVICE_NONCE=nonce1,
            HTTP_X_DEVICE_SIGNATURE=sig1,
        )
        assert r1.status_code == 200

        nonce2 = "nonce-throttle-2"
        sig2 = hmac_signature_b64(secret, canonical_string(ts, nonce2, raw))

        r2 = client.post(
            url,
            data=body,
            format="json",
            HTTP_X_DEVICE_ID=str(device.id),
            HTTP_X_DEVICE_TS=str(ts),
            HTTP_X_DEVICE_NONCE=nonce2,
            HTTP_X_DEVICE_SIGNATURE=sig2,
        )
        assert r2.status_code == 429
        payload = r2.json()
        assert payload["error"]["code"] == "RATE_LIMITED"
        assert r2["X-Request-Id"] == payload["error"]["request_id"]

    cache.clear()
    api_settings.reload()
