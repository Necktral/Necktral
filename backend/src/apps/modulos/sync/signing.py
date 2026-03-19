from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_string(ts: int, nonce: str, raw_body: bytes) -> bytes:
    body_hash = sha256_hex(raw_body)
    s = f"{ts}.{nonce}.{body_hash}"
    return s.encode("utf-8")


def hmac_signature_b64(secret_b64: str, canonical: bytes) -> str:
    secret = base64.b64decode(secret_b64.encode("utf-8"))
    mac = hmac.new(secret, canonical, hashlib.sha256).digest()
    return base64.b64encode(mac).decode("utf-8")


def verify_hmac_signature(secret_b64: str, canonical: bytes, provided_sig_b64: str) -> bool:
    expected = hmac_signature_b64(secret_b64, canonical)
    # compare_digest evita timing attacks
    return hmac.compare_digest(expected, provided_sig_b64)


@dataclass(frozen=True)
class SignatureInputs:
    device_id: str
    ts: int
    nonce: str
    signature_b64: str
