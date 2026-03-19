from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict

from django.db import transaction

from .models import AppliedCommand, DeviceEnrollment


class CommandError(Exception):
    pass


@dataclass(frozen=True)
class Command:
    command_id: str  # UUID string
    type: str
    payload: Dict[str, Any]


HandlerFn = Callable[[DeviceEnrollment, Command], Dict[str, Any]]

HANDLERS: Dict[str, HandlerFn] = {}


def register(command_type: str) -> Callable[[HandlerFn], HandlerFn]:
    def _decorator(fn: HandlerFn) -> HandlerFn:
        HANDLERS[command_type] = fn
        return fn

    return _decorator


@register("PING")
def handle_ping(device: DeviceEnrollment, cmd: Command) -> Dict[str, Any]:
    # Handler de prueba/health. Útil para testear canal y firma.
    return {"pong": True, "echo": cmd.payload}


def command_request_hash(cmd: Command) -> str:
    # Hash estable del comando: tipo + payload (ordenado)
    raw = json.dumps({"type": cmd.type, "payload": cmd.payload}, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


@transaction.atomic
def apply_command_idempotent(device: DeviceEnrollment, cmd: Command) -> Dict[str, Any]:
    """
    Si el comando ya fue aplicado, devuelve la respuesta cacheada.
    Si no existe, ejecuta handler, guarda AppliedCommand y devuelve respuesta.
    """

    req_hash = command_request_hash(cmd)

    existing = AppliedCommand.objects.filter(device=device, command_id=cmd.command_id).first()
    if existing:
        # Defensa adicional: si reusan command_id con payload distinto, eso es sospechoso.
        if existing.request_hash != req_hash:
            raise CommandError("IDEMPOTENCY_CONFLICT: command_id reused with different payload")
        return existing.response_json

    response: Dict[str, Any]
    handler = HANDLERS.get(cmd.type)
    if not handler:
        response = {"status": "ERROR", "error": f"UNKNOWN_COMMAND_TYPE: {cmd.type}"}
        AppliedCommand.objects.create(
            device=device,
            command_id=cmd.command_id,
            command_type=cmd.type,
            request_hash=req_hash,
            status="ERROR",
            response_json=response,
        )
        return response

    try:
        payload_response = handler(device, cmd)
        response = {"status": "OK", "data": payload_response}
        AppliedCommand.objects.create(
            device=device,
            command_id=cmd.command_id,
            command_type=cmd.type,
            request_hash=req_hash,
            status="OK",
            response_json=response,
        )
        return response
    except Exception as e:
        response = {"status": "ERROR", "error": str(e)}
        AppliedCommand.objects.create(
            device=device,
            command_id=cmd.command_id,
            command_type=cmd.type,
            request_hash=req_hash,
            status="ERROR",
            response_json=response,
        )
        return response
