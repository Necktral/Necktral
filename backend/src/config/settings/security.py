from __future__ import annotations

from typing import Iterable

# Umbral recomendado para HS256 (RFC 7518 §3.2): 256 bits = 32 bytes.
MIN_HS256_KEY_BYTES = 32

# Valores inseguros/de ejemplo que no deben llegar a producción.
INSECURE_DEFAULTS = {
    "",
    "unsafe-dev-secret",
    "change-me-please",
    "dev-audit-key-change-me",
    "pon-tu-clave-segura-aqui",
}


def key_size_bytes(value: str | None) -> int:
    if not value:
        return 0
    return len(value.encode("utf-8"))


def is_insecure_default(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip() in INSECURE_DEFAULTS


def is_hs256_key_strong(value: str | None, *, min_bytes: int = MIN_HS256_KEY_BYTES) -> bool:
    if not value:
        return False
    return key_size_bytes(value) >= min_bytes


def parse_keyring(raw: str | None) -> list[tuple[str, str]]:
    """Parsea AUDIT_HMAC_KEYS en formato `kid:key,kid2:key2`.

    Retorna una lista de (kid, key) validos (sin vacios).
    """
    if not raw:
        return []

    out: list[tuple[str, str]] = []
    for chunk in raw.split(","):
        part = chunk.strip()
        if not part or ":" not in part:
            continue
        kid, key = part.split(":", 1)
        kid = kid.strip()
        key = key.strip()
        if kid and key:
            out.append((kid, key))
    return out


def find_weak_keys(keys: Iterable[tuple[str, str]], *, min_bytes: int = MIN_HS256_KEY_BYTES) -> list[str]:
    weak_ids: list[str] = []
    for kid, key in keys:
        if is_insecure_default(key) or not is_hs256_key_strong(key, min_bytes=min_bytes):
            weak_ids.append(kid)
    return weak_ids
