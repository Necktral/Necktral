from __future__ import annotations

from typing import Callable, Dict, TypedDict, Any


class HandlerResult(TypedDict, total=False):
    refs: dict[str, Any]
    warnings: list[str]


CommandHandler = Callable[[dict[str, Any], dict[str, Any]], HandlerResult]

_REGISTRY: Dict[str, CommandHandler] = {}


def register(command_type: str):
    def _wrap(fn: CommandHandler) -> CommandHandler:
        if command_type in _REGISTRY:
            raise RuntimeError(f"command_type duplicado en registry: {command_type}")
        _REGISTRY[command_type] = fn
        return fn

    return _wrap


def get_handler(command_type: str) -> CommandHandler | None:
    return _REGISTRY.get(command_type)
