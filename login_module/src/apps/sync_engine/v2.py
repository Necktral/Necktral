from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status

from apps.sync.signing import verify_hmac_signature

from .models import Device, DeviceRequestNonce
from .services import process_batch
from .signing import canon_json, sha256_hex, verify_ed25519_signature


@dataclass(frozen=True)
class SyncV2Auth:
    scheme: str
    signature_b64: str
    key_id: str | None = None


class SyncV2Error(Exception):
    def __init__(self, *, error: str, status_code: int, details: dict[str, Any] | None = None):
        super().__init__(error)
        self.error = error
        self.status_code = status_code
        self.details = details or {}


def strip_signature_for_sign(data: dict[str, Any]) -> dict[str, Any]:
    body = copy.deepcopy(data)
    auth = body.get("auth")
    if isinstance(auth, dict):
        auth.pop("signature", None)
    return body


def build_string_to_sign(*, ts: int, nonce: str, body_for_sign: dict[str, Any]) -> bytes:
    body_hash = sha256_hex(canon_json(body_for_sign))
    s = f"{ts}.{nonce}.{body_hash}"
    return s.encode("utf-8")


def ensure_device_active(device: Device) -> None:
    if device.status == Device.Status.REVOKED:
        raise SyncV2Error(error="SYNC_DEVICE_REVOKED", status_code=status.HTTP_401_UNAUTHORIZED)
    if device.status == Device.Status.QUARANTINED:
        raise SyncV2Error(error="SYNC_DEVICE_QUARANTINED", status_code=status.HTTP_401_UNAUTHORIZED)


def verify_request_auth(*, device: Device, auth: SyncV2Auth, string_to_sign: bytes) -> None:
    if auth.scheme == "hmac":
        secret = device.hmac_secret_b64
        if not secret:
            raise SyncV2Error(error="SYNC_DEVICE_NO_HMAC_SECRET", status_code=status.HTTP_401_UNAUTHORIZED)
        if not verify_hmac_signature(secret, string_to_sign, auth.signature_b64):
            raise SyncV2Error(error="BAD_SIGNATURE", status_code=status.HTTP_401_UNAUTHORIZED)
        return

    if auth.scheme == "ed25519":
        if not device.public_key:
            raise SyncV2Error(error="SYNC_DEVICE_NO_PUBLIC_KEY", status_code=status.HTTP_401_UNAUTHORIZED)
        if not verify_ed25519_signature(public_key_raw=device.public_key, signature_b64=auth.signature_b64, message=string_to_sign):
            raise SyncV2Error(error="BAD_SIGNATURE", status_code=status.HTTP_401_UNAUTHORIZED)
        return

    raise SyncV2Error(error="UNSUPPORTED_AUTH_SCHEME", status_code=status.HTTP_400_BAD_REQUEST)


def reserve_nonce(*, device: Device, nonce: str, ts: int) -> None:
    try:
        with transaction.atomic():
            DeviceRequestNonce.objects.create(device=device, nonce=nonce, ts=ts)
    except IntegrityError:
        raise SyncV2Error(error="REPLAY_DETECTED", status_code=status.HTTP_401_UNAUTHORIZED)


def enforce_time_window(*, ts: int) -> None:
    max_skew = 300
    now = int(timezone.now().timestamp())
    if abs(now - ts) > max_skew:
        raise SyncV2Error(error="TS_OUT_OF_WINDOW", status_code=status.HTTP_401_UNAUTHORIZED)


def normalize_commands(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for c in commands:
        scope = c.get("scope") or {}
        normalized.append(
            {
                "command_id": c.get("command_id"),
                "command_type": c.get("type"),
                "company_id": scope.get("company_id"),
                "branch_id": scope.get("branch_id"),
                "occurred_at": c.get("occurred_at"),
                "sequence": c.get("sequence"),
                "payload": c.get("payload") or {},
                "payload_hash": c.get("payload_hash"),
                "prev_hash": c.get("prev_hash") or "",
                "signature": c.get("command_sig"),
            }
        )
    return normalized


def process_sync_v2(
    *,
    request,
    device: Device,
    batch_id,
    sent_at,
    ts: int,
    nonce: str,
    auth: SyncV2Auth,
    raw_body: dict[str, Any],
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    ensure_device_active(device)
    enforce_time_window(ts=ts)

    body_for_sign = strip_signature_for_sign(raw_body)
    string_to_sign = build_string_to_sign(ts=ts, nonce=nonce, body_for_sign=body_for_sign)

    verify_request_auth(device=device, auth=auth, string_to_sign=string_to_sign)
    reserve_nonce(device=device, nonce=nonce, ts=ts)

    normalized_commands = normalize_commands(commands)

    return process_batch(
        request=request,
        actor_user=getattr(request, "user", None),
        device=device,
        batch_id=batch_id,
        sent_at=sent_at,
        commands=normalized_commands,
        allow_unsigned=True,
    )
