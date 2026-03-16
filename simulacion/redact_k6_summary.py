#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SENSITIVE_KEY_PARTS = {
    "token",
    "password",
    "secret",
    "authorization",
    "api_key",
    "apikey",
    "cookie",
}
JWT_PATTERN = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _redact_scalar(value: Any) -> Any:
    if isinstance(value, str) and JWT_PATTERN.match(value):
        return "__REDACTED_JWT__"
    return value


def _redact(node: Any, *, key_hint: str = "") -> Any:
    if _is_sensitive_key(key_hint):
        return "__REDACTED__"

    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            out[str(key)] = _redact(value, key_hint=str(key))
        return out

    if isinstance(node, list):
        return [_redact(item, key_hint=key_hint) for item in node]

    return _redact_scalar(node)


def main() -> int:
    parser = argparse.ArgumentParser(description="Redacta secretos/tokenes en un summary JSON de k6.")
    parser.add_argument("summary_path", help="Ruta al summary JSON.")
    parser.add_argument(
        "--in-place",
        action="store_true",
        default=True,
        help="Sobrescribe el archivo original (default).",
    )
    args = parser.parse_args()

    path = Path(args.summary_path)
    if not path.exists():
        raise SystemExit(f"summary no existe: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    redacted = _redact(raw)
    path.write_text(json.dumps(redacted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
