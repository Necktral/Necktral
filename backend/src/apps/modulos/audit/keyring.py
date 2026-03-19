from __future__ import annotations

from typing import Iterable

from django.conf import settings


def _parse_keyring_raw(raw) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []

    if isinstance(raw, (list, tuple)):
        for entry in raw:
            kid = ""
            key = ""
            if isinstance(entry, dict):
                kid = str(entry.get("kid") or entry.get("id") or "").strip()
                key = str(entry.get("key") or entry.get("secret") or "").strip()
            elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                kid = str(entry[0]).strip()
                key = str(entry[1]).strip()
            elif isinstance(entry, str):
                if ":" in entry:
                    kid, key = entry.split(":", 1)
                    kid = kid.strip()
                    key = key.strip()
            if kid and key:
                items.append((kid, key))
        return items

    if isinstance(raw, str):
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if not chunk or ":" not in chunk:
                continue
            kid, key = chunk.split(":", 1)
            kid = kid.strip()
            key = key.strip()
            if kid and key:
                items.append((kid, key))

    return items


def _dedupe_keyring(keyring: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for kid, key in keyring:
        if kid in seen:
            continue
        seen.add(kid)
        out.append((kid, key))
    return out


def get_audit_hmac_keyring() -> list[tuple[str, str]]:
    raw = getattr(settings, "AUDIT_HMAC_KEYS", "") or ""
    keyring = _parse_keyring_raw(raw)

    primary = getattr(settings, "AUDIT_HMAC_KEY", "") or ""
    if not keyring:
        if not primary:
            raise ValueError("AUDIT_HMAC_KEY requerido para firmar auditoria.")
        return [("primary", primary)]

    if primary and primary not in [key for _, key in keyring]:
        keyring.append(("legacy", primary))

    return _dedupe_keyring(keyring)


def get_active_audit_hmac_key() -> tuple[str, str]:
    keyring = get_audit_hmac_keyring()
    return keyring[0]
