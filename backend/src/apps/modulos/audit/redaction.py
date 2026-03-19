from __future__ import annotations

import hashlib
import json
from typing import Any

REDACTED = "***REDACTED***"

_SENSITIVE_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "refresh",
    "access",
    "authorization",
    "cookie",
    "set-cookie",
    "api_key",
    "apikey",
    "private_key",
    "hmac",
)

_MAX_DEPTH = 8
_MAX_JSON_BYTES = 24000


def _is_sensitive_key(key: str) -> bool:
    k = key.lower().strip()
    return any(s in k for s in _SENSITIVE_SUBSTRINGS)


def _redact(obj: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return "<max_depth_reached>"

    if obj is None:
        return None
    if isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_redact(x, depth=depth + 1) for x in obj]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            try:
                ks = str(k)
            except Exception:
                ks = "<non_string_key>"
            if _is_sensitive_key(ks):
                out[ks] = REDACTED
            else:
                out[ks] = _redact(v, depth=depth + 1)
        return out

    return str(obj)


def _truncate_if_needed(obj: Any) -> Any:
    try:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except Exception:
        s = json.dumps(str(obj), ensure_ascii=False)

    b = s.encode("utf-8", errors="replace")
    if len(b) <= _MAX_JSON_BYTES:
        return obj

    h = hashlib.sha256(b).hexdigest()
    return {
        "_truncated": True,
        "_sha256": h,
        "_bytes": len(b),
    }


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = metadata or {}
    return _truncate_if_needed(_redact(metadata))


def sanitize_snapshot(snapshot: Any) -> Any:
    if snapshot is None:
        return None
    return _truncate_if_needed(_redact(snapshot))
