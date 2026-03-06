from __future__ import annotations

from config.settings.security import (
    MIN_HS256_KEY_BYTES,
    find_weak_keys,
    is_hs256_key_strong,
    is_insecure_default,
    key_size_bytes,
    parse_keyring,
)


def test_key_size_bytes_uses_utf8_length():
    assert key_size_bytes("abc") == 3
    assert key_size_bytes("") == 0
    assert key_size_bytes(None) == 0


def test_is_insecure_default_detects_placeholders():
    assert is_insecure_default("") is True
    assert is_insecure_default("change-me-please") is True
    assert is_insecure_default("unsafe-dev-secret") is True
    assert is_insecure_default("real-secret-1234567890-abcdefghijklmnopqrstuvwxyz") is False


def test_is_hs256_key_strong_enforces_minimum_bytes():
    weak = "x" * (MIN_HS256_KEY_BYTES - 1)
    strong = "x" * MIN_HS256_KEY_BYTES
    assert is_hs256_key_strong(weak, min_bytes=MIN_HS256_KEY_BYTES) is False
    assert is_hs256_key_strong(strong, min_bytes=MIN_HS256_KEY_BYTES) is True


def test_parse_keyring_skips_invalid_entries():
    raw = "primary:very-strong-key-abcdefghijklmnopqrstuvwxyz,invalid,legacy:other-strong-key-abcdefghijklmnopqrstuvwxyz, :bad"
    parsed = parse_keyring(raw)
    assert parsed == [
        ("primary", "very-strong-key-abcdefghijklmnopqrstuvwxyz"),
        ("legacy", "other-strong-key-abcdefghijklmnopqrstuvwxyz"),
    ]


def test_find_weak_keys_reports_insecure_or_short_keys():
    keys = [
        ("ok", "x" * MIN_HS256_KEY_BYTES),
        ("short", "x" * 8),
        ("placeholder", "change-me-please"),
    ]
    weak = find_weak_keys(keys, min_bytes=MIN_HS256_KEY_BYTES)
    assert set(weak) == {"short", "placeholder"}
