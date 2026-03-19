"""Primitivas de firma del motor offline/sync (precedente).

Precedente:
- El mensaje firmado NO es JSON: es un formato concatenado estable para evitar ambigüedad.
- occurred_at se canonicaliza a UTC con microsegundos para firma determinista.
"""

import base64
import datetime as dt
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def occurred_at_canonical(dt_value: dt.datetime) -> str:
    """
    Representación determinista para firma:
    - Si es naive, se asume UTC (para evitar que DRF lo convierta a otra tz)
    - Se convierte a UTC
    - Se fija timespec a microseconds (siempre 6 dígitos)
    """
    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=dt.timezone.utc)
    dt_utc = dt_value.astimezone(dt.timezone.utc)
    return dt_utc.isoformat(timespec="microseconds")


def canon_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_hex_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def b64decode_strict(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"), validate=True)


def public_key_from_b64(pk_b64: str) -> bytes:
    raw = b64decode_strict(pk_b64)
    if len(raw) != 32:
        raise ValueError("public_key inválida: Ed25519 requiere 32 bytes.")
    return raw


def build_command_signing_message(
    *,
    command_id: str,
    command_type: str,
    company_id: int,
    branch_id: int | None,
    occurred_at: str,
    sequence: int | None,
    payload_hash: str,
    prev_hash: str,
) -> bytes:
    """
    Mensaje estable (sin ambigüedad por JSON):
      command_id|command_type|company_id|branch_id|occurred_at|sequence|payload_hash|prev_hash
    """
    b = "" if branch_id is None else str(branch_id)
    s = "" if sequence is None else str(sequence)
    msg = f"{command_id}|{command_type}|{company_id}|{b}|{occurred_at}|{s}|{payload_hash}|{prev_hash}"
    return msg.encode("utf-8")


def verify_ed25519_signature(*, public_key_raw: bytes, signature_b64: str, message: bytes) -> bool:
    try:
        sig = b64decode_strict(signature_b64)
        # Firma Ed25519 siempre son 64 bytes
        if len(sig) != 64:
            return False
        # PostgreSQL/Django puede devolver memoryview; normalizamos a bytes
        pk_bytes = bytes(public_key_raw)
        # Public key Ed25519 siempre son 32 bytes
        if len(pk_bytes) != 32:
            return False
        pk = Ed25519PublicKey.from_public_bytes(pk_bytes)
        pk.verify(sig, message)
        return True
    except Exception:
        return False
