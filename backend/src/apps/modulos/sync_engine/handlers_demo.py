from __future__ import annotations

from typing import Any

from .registry import register, HandlerResult


@register("DEMO_PING")
def handle_demo_ping(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    # Comando toy: valida pipeline end-to-end sin tocar dominios reales todavía.
    msg = str(payload.get("msg", ""))
    return {"refs": {"pong": True, "echo": msg}}
