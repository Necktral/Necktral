"""Servicios del motor offline/sync (precedente).

Este módulo implementa el pipeline completo de procesamiento:
1) Política (límites)
2) Validación de scope (company/branch) contra el dispositivo
3) Canonicalización y verificación de firma (Ed25519)
4) Idempotencia (AppliedCommand) y concurrencia segura
5) Dispatch a handlers registrados
6) Auditoría por batch y por comando

Semántica de estados (respuesta por comando):
- APPLIED: aplicado y persistido
- DUPLICATE: mismo command_id y mismo payload_hash ya visto
- REJECTED: rechazado (firma inválida, scope prohibido, schema inválido, etc.)
"""

from __future__ import annotations
import logging

import json
from dataclasses import dataclass
from typing import Any, cast

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework.exceptions import PermissionDenied

from apps.audit.writer import write_event
from apps.iam.models import OrgUnit

from .errors import SyncRejectError
from .models import AppliedCommand, Device, SyncReceipt
from .registry import get_handler

# Import por side-effect: registra handlers demo en el registry.
from . import handlers_demo as _handlers_demo  # noqa: F401
# Import por side-effect: registra handlers inventory en el registry.
from . import handlers_inventory as _handlers_inventory  # noqa: F401
from .signing import (
    build_command_signing_message,
    canon_json,
    sha256_hex,
    verify_ed25519_signature,
    occurred_at_canonical,
)


@dataclass(frozen=True)
class SyncPolicy:
    max_commands_per_batch: int
    max_payload_bytes: int
    max_device_clock_skew_seconds: int
    seq_tolerant: bool


def get_policy() -> SyncPolicy:
    return SyncPolicy(
        max_commands_per_batch=int(getattr(settings, "SYNC_MAX_COMMANDS_PER_BATCH", 100)),
        max_payload_bytes=int(getattr(settings, "SYNC_MAX_PAYLOAD_BYTES", 64_000)),
        max_device_clock_skew_seconds=int(getattr(settings, "SYNC_MAX_DEVICE_CLOCK_SKEW_SECONDS", 6 * 3600)),
        seq_tolerant=bool(getattr(settings, "SYNC_SEQ_TOLERANT", True)),
    )


def _payload_size_bytes(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def resolve_device(*, device_id: str) -> Device:
    try:
        return Device.objects.select_related("company", "branch").get(id=device_id)
    except Device.DoesNotExist:
        raise PermissionDenied("Dispositivo no enrolado o no existe.")


def enforce_device_active(device: Device) -> None:
    if device.status == Device.Status.REVOKED:
        raise PermissionDenied("Dispositivo revocado.")
    if device.status == Device.Status.QUARANTINED:
        raise PermissionDenied("Dispositivo en cuarentena.")


def ensure_scope_matches(*, device: Device, company_id: int, branch_id: int | None) -> bool:
    if device.company_id != company_id:
        return False
    if device.branch_id is None:
        # Device a nivel empresa: permite branch_id null o cualquier branch bajo company.
        if branch_id is None:
            return True
        # Validación fuerte: branch declarada debe existir y pertenecer a company.
        return OrgUnit.objects.filter(
            id=branch_id,
            unit_type=OrgUnit.UnitType.BRANCH,
            parent_id=company_id,
            is_active=True,
        ).exists()
    # Device amarrado a una sucursal específica:
    return branch_id == device.branch_id


def process_batch(
    *, request, actor_user, device: Device, batch_id, sent_at, commands: list[dict[str, Any]]
) -> dict[str, Any]:
    policy = get_policy()
    if len(commands) > policy.max_commands_per_batch:
        write_event(
            request=request,
            event_type="SYNC_BATCH_RECEIVED",
            reason_code="SYNC_LIMIT_EXCEEDED",
            actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
            subject_type="DEVICE",
            subject_id=str(device.id),
            device_id=str(device.id),
            offline_mode=True,
            metadata={
                "batch_id": str(batch_id),
                "received_count": len(commands),
                "limit": policy.max_commands_per_batch,
            },
        )
        return {
            "batch_id": str(batch_id),
            "server_time": timezone.now().isoformat(),
            "device_id": str(device.id),
            "device_status": device.status,
            "results": [],
            "summary": {
                "received": len(commands),
                "applied": 0,
                "rejected": len(commands),
                "duplicate": 0,
            },
            "errors": [{"reason": "SYNC_LIMIT_EXCEEDED"}],
        }

    results: list[dict[str, Any]] = []
    applied = 0
    rejected = 0
    duplicate = 0
    errors_summary: dict[str, int] = {}

    # Auditoría “batch recibido”
    write_event(
        request=request,
        event_type="SYNC_BATCH_RECEIVED",
        reason_code="SYNC_OK",
        actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
        subject_type="DEVICE",
        subject_id=str(device.id),
        device_id=str(device.id),
        offline_mode=True,
        metadata={"batch_id": str(batch_id), "received_count": len(commands)},
    )

    for c in commands:
        try:
            r = process_command(request=request, actor_user=actor_user, device=device, cmd=c, policy=policy)
        except Exception as e:
            # 1) auditar
            write_event(
                request=request,
                event_type="SYNC_COMMAND_REJECTED",
                reason_code="SYNC_INTERNAL_ERROR",
                actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
                subject_type="DEVICE",
                subject_id=str(device.id),
                device_id=str(device.id),
                offline_mode=True,
                metadata={
                    "error": str(e),
                    "command_type": c.get("command_type"),
                    "command_id": str(c.get("command_id")),
                },
            )
            # 2) responder REJECTED para ese comando, sin tumbar el batch
            r = {"command_id": str(c.get("command_id")), "status": "REJECTED", "reason": "SYNC_INTERNAL_ERROR"}
        results.append(r)
        st = r.get("status")
        if st == "APPLIED":
            applied += 1
        elif st == "DUPLICATE":
            duplicate += 1
        else:
            rejected += 1
            reason = str(r.get("reason", "SYNC_INTERNAL_ERROR"))
            errors_summary[reason] = errors_summary.get(reason, 0) + 1

    SyncReceipt.objects.update_or_create(
        batch_id=batch_id,
        defaults={
            "device": device,
            "sent_at": sent_at,
            "received_count": len(commands),
            "applied_count": applied,
            "rejected_count": rejected,
            "duplicate_count": duplicate,
            "errors_summary": errors_summary,
        },
    )

    # Last seen (al final del batch)
    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])

    return {
        "server_time": timezone.now().isoformat(),
        "batch_id": str(batch_id),
        "device_id": str(device.id),
        "device_status": device.status,
        "results": results,
        "summary": {
            "received": len(commands),
            "applied": applied,
            "rejected": rejected,
            "duplicate": duplicate,
        },
    }


def process_command(*, request, actor_user, device: Device, cmd: dict[str, Any], policy: SyncPolicy) -> dict[str, Any]:
    """Procesa un comando individual.

    Precondición:
    - cmd ya fue validado por serializer (tipos base y formato).

    Pipeline:
    - límites de payload (protección DoS / abuso)
    - status del device + política de skew (cuarentena)
    - scope enforcement (company/branch)
    - canonicalización (payload_hash + occurred_at) y verificación Ed25519
    - idempotencia AppliedCommand (command_id)
    - dispatch a handler
    - auditoría por resultado (APPLIED/DUPLICATE/REJECTED)
    """
    command_id = cmd["command_id"]
    command_type = cmd["command_type"]
    company_id = cmd["company_id"]
    branch_id = cmd.get("branch_id")
    occurred_at = cmd["occurred_at"]
    sequence = cmd.get("sequence")
    payload = cmd["payload"]
    signature = cmd["signature"]
    prev_hash = cmd.get("prev_hash") or ""

    # Límite de payload (regla fuerte: evita batches gigantes y firma sobre datos arbitrarios)
    if _payload_size_bytes(payload) > policy.max_payload_bytes:
        return _reject_without_db(
            request=request,
            actor_user=actor_user,
            device=device,
            command_id=str(command_id),
            command_type=command_type,
            reason="SYNC_LIMIT_EXCEEDED",
            details={"max_payload_bytes": policy.max_payload_bytes},
        )

    # Device status
    if device.status == Device.Status.REVOKED:
        return _reject_without_db(
            request=request,
            actor_user=actor_user,
            device=device,
            command_id=str(command_id),
            command_type=command_type,
            reason="SYNC_DEVICE_REVOKED",
            details={},
        )
    if device.status == Device.Status.QUARANTINED:
        return _reject_without_db(
            request=request,
            actor_user=actor_user,
            device=device,
            command_id=str(command_id),
            command_type=command_type,
            reason="SYNC_DEVICE_QUARANTINED",
            details={},
        )

    # Time skew policy: occurred_at no es “verdad”, pero sí se controla desvío extremo.
    # Regla fuerte: si el desfase es muy grande, se pone el device en cuarentena.
    now = timezone.now()
    skew = abs((now - occurred_at).total_seconds())
    if skew > policy.max_device_clock_skew_seconds:
        # Política robusta: manda a cuarentena si el desfase es extremo
        device.status = Device.Status.QUARANTINED
        device.save(update_fields=["status"])
        return _reject_without_db(
            request=request,
            actor_user=actor_user,
            device=device,
            command_id=str(command_id),
            command_type=command_type,
            reason="SYNC_TIME_SKEW",
            details={"skew_seconds": int(skew), "limit_seconds": policy.max_device_clock_skew_seconds},
        )

    # Scope enforcement: el dispositivo no puede emitir comandos para otra empresa/sucursal.
    if not ensure_scope_matches(device=device, company_id=company_id, branch_id=branch_id):
        return _reject_without_db(
            request=request,
            actor_user=actor_user,
            device=device,
            command_id=str(command_id),
            command_type=command_type,
            reason="SYNC_FORBIDDEN_SCOPE",
            details={"company_id": company_id, "branch_id": branch_id},
        )

    # payload_hash: si viene, se valida; si no viene, se calcula.
    # Precedente: el hash se calcula sobre JSON canónico (canon_json).
    try:
        payload_canon = canon_json(payload)
        computed_payload_hash = sha256_hex(payload_canon)
        provided_payload_hash = (cmd.get("payload_hash") or "").strip()
        if provided_payload_hash and provided_payload_hash != computed_payload_hash:
            return _reject_without_db(
                request=request,
                actor_user=actor_user,
                device=device,
                command_id=str(command_id),
                command_type=command_type,
                reason="SYNC_SCHEMA_INVALID",
                details={"payload_hash": "mismatch"},
            )

        # Mensaje firmado estable: evita ambigüedad de JSON (orden de keys, espacios, etc.)
        msg = build_command_signing_message(
            command_id=str(command_id),
            command_type=command_type,
            company_id=int(company_id),
            branch_id=int(branch_id) if branch_id is not None else None,
            occurred_at=occurred_at_canonical(occurred_at),
            sequence=int(sequence) if sequence is not None else None,
            payload_hash=computed_payload_hash,
            prev_hash=prev_hash,
        )
        if not verify_ed25519_signature(public_key_raw=device.public_key, signature_b64=signature, message=msg):
            return _reject_with_db(
                request=request,
                actor_user=actor_user,
                device=device,
                command_id=command_id,
                company_id=company_id,
                branch_id=branch_id,
                command_type=command_type,
                occurred_at=occurred_at,
                sequence=sequence,
                payload_hash=computed_payload_hash,
                prev_hash=prev_hash,
                reason="SYNC_INVALID_SIGNATURE",
                details={},
            )
    except (ValueError, TypeError) as e:
        # Errores típicos de canonicalización/firma/base64
        return _reject_with_db(
            request=request,
            actor_user=actor_user,
            device=device,
            command_id=command_id,
            company_id=company_id,
            branch_id=branch_id,
            command_type=command_type,
            occurred_at=occurred_at,
            sequence=sequence,
            payload_hash=cmd.get("payload_hash") or "",
            prev_hash=prev_hash,
            reason="SYNC_INVALID_SIGNATURE",
            details={"error": str(e)},
        )

    handler = get_handler(command_type)
    if handler is None:
        return _reject_with_db(
            request=request,
            actor_user=actor_user,
            device=device,
            command_id=command_id,
            company_id=company_id,
            branch_id=branch_id,
            command_type=command_type,
            occurred_at=occurred_at,
            sequence=sequence,
            payload_hash=computed_payload_hash,
            prev_hash=prev_hash,
            reason="SYNC_SCHEMA_INVALID",
            details={"unknown_command_type": command_type},
        )

    # Idempotencia + aplicación transaccional (por comando) con SAVEPOINT robusto.
    # Precedente: command_id es la clave; mismo ID con payload distinto se rechaza.

    with transaction.atomic():
        # Lock del command_id si existe
        row = AppliedCommand.objects.select_for_update().filter(command_id=command_id).first()
        if row:
            if row.payload_hash == computed_payload_hash:
                write_event(
                    request=request,
                    event_type="SYNC_COMMAND_DUPLICATE",
                    reason_code="SYNC_DUPLICATE",
                    actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
                    subject_type="DEVICE",
                    subject_id=str(device.id),
                    device_id=str(device.id),
                    offline_mode=True,
                    metadata={"command_id": str(command_id), "command_type": command_type},
                )
                return {
                    "command_id": str(command_id),
                    "status": "DUPLICATE",
                    "refs": row.result_ref or {},
                }
            # Mismo ID, payload distinto (colisión o bug serio)
            write_event(
                request=request,
                event_type="SYNC_COMMAND_REJECTED",
                reason_code="SYNC_PAYLOAD_MISMATCH",
                actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
                subject_type="DEVICE",
                subject_id=str(device.id),
                device_id=str(device.id),
                offline_mode=True,
                metadata={
                    "command_id": str(command_id),
                    "command_type": command_type,
                    "existing_payload_hash": row.payload_hash,
                    "incoming_payload_hash": computed_payload_hash,
                },
            )
            return {
                "command_id": str(command_id),
                "status": "REJECTED",
                "reason": "SYNC_PAYLOAD_MISMATCH",
            }

        # Patrón robusto: reserva idempotente y concurrencia segura
        ctx = {
            "request": request,
            "actor_user": actor_user if getattr(actor_user, "is_authenticated", False) else None,
            "device": device,
            "company_id": company_id,
            "branch_id": branch_id,
            "command_id": str(command_id),
            "command_type": command_type,
            "occurred_at": occurred_at_canonical(occurred_at),
            "sequence": sequence,
        }

        # Reserva idempotente
        sid = transaction.savepoint()
        try:
            row = AppliedCommand.objects.create(
                command_id=command_id,
                device=device,
                company_id=company_id,
                branch_id=branch_id,
                command_type=command_type,
                occurred_at=occurred_at,
                sequence=sequence,
                payload_hash=computed_payload_hash,
                prev_hash=prev_hash,
                result_status=AppliedCommand.ResultStatus.REJECTED,  # provisional
                result_ref={},
                error={},
            )
            transaction.savepoint_commit(sid)
        except IntegrityError:
            transaction.savepoint_rollback(sid)
            row = AppliedCommand.objects.select_for_update().get(command_id=command_id)
            if row.payload_hash == computed_payload_hash:
                write_event(
                    request=request,
                    event_type="SYNC_COMMAND_DUPLICATE",
                    reason_code="SYNC_DUPLICATE",
                    actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
                    subject_type="DEVICE",
                    subject_id=str(device.id),
                    device_id=str(device.id),
                    offline_mode=True,
                    metadata={"command_id": str(command_id), "command_type": command_type},
                )
                return {"command_id": str(command_id), "status": "DUPLICATE", "refs": row.result_ref or {}}
            # PAYLOAD_MISMATCH
            write_event(
                request=request,
                event_type="SYNC_COMMAND_REJECTED",
                reason_code="SYNC_PAYLOAD_MISMATCH",
                actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
                subject_type="DEVICE",
                subject_id=str(device.id),
                device_id=str(device.id),
                offline_mode=True,
                metadata={
                    "command_id": str(command_id),
                    "command_type": command_type,
                    "existing_payload_hash": row.payload_hash,
                    "incoming_payload_hash": computed_payload_hash,
                },
            )
            return {"command_id": str(command_id), "status": "REJECTED", "reason": "SYNC_PAYLOAD_MISMATCH"}

        # Ejecutar handler fuera del savepoint pero dentro del atomic
        logger = logging.getLogger(__name__)
        try:
            res = handler(ctx, payload) or {}
            refs: dict[str, Any] = dict(res.get("refs", {}) or {})
            warnings: list[str] = list(res.get("warnings", []) or [])
        except SyncRejectError as e:
            # Rechazo controlado: negocio / contrato, NO internal error.
            reason = str(e.reason_code)
            details: dict[str, Any] = dict(e.details or {})

            row.result_status = AppliedCommand.ResultStatus.REJECTED
            row.error = cast(dict[str, Any], {"reason": reason, **details})
            row.save(update_fields=["result_status", "error"])

            write_event(
                request=request,
                event_type="SYNC_COMMAND_REJECTED",
                reason_code=reason,
                actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
                subject_type="DEVICE",
                subject_id=str(device.id),
                device_id=str(device.id),
                offline_mode=True,
                metadata={
                    "command_id": str(command_id),
                    "command_type": command_type,
                    "company_id": company_id,
                    "branch_id": branch_id,
                    **details,
                },
            )

            out: dict[str, Any] = {"command_id": str(command_id), "status": "REJECTED", "reason": reason}
            if details:
                out["details"] = details
            return out
        except Exception as e:
            logger.error(f"[SYNC_ENGINE][process_command] ERROR: {repr(e)}")
            row.result_status = AppliedCommand.ResultStatus.REJECTED
            row.error = cast(dict[str, Any], {"reason": "SYNC_INTERNAL_ERROR", "exception": str(e)})
            row.save(update_fields=["result_status", "error"])
            write_event(
                request=request,
                event_type="SYNC_COMMAND_REJECTED",
                reason_code="SYNC_INTERNAL_ERROR",
                actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
                subject_type="DEVICE",
                subject_id=str(device.id),
                device_id=str(device.id),
                offline_mode=True,
                metadata={"command_id": str(command_id), "command_type": command_type, "error": str(e)},
            )
            return {"command_id": str(command_id), "status": "REJECTED", "reason": "SYNC_INTERNAL_ERROR"}

        # Actualizar row a APPLIED
        row.result_status = AppliedCommand.ResultStatus.APPLIED
        row.applied_at = timezone.now()
        row.result_ref = refs
        row.error = cast(dict[str, Any], {})
        row.save(update_fields=["result_status", "applied_at", "result_ref", "error"])

        # Actualizar last_accepted_sequence (tolerante por defecto)
        if sequence is not None:
            if sequence > device.last_accepted_sequence:
                device.last_accepted_sequence = int(sequence)
                device.save(update_fields=["last_accepted_sequence"])

        write_event(
            request=request,
            event_type="SYNC_COMMAND_APPLIED",
            reason_code="SYNC_OK",
            actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
            subject_type="DEVICE",
            subject_id=str(device.id),
            device_id=str(device.id),
            offline_mode=True,
            metadata={
                "command_id": str(command_id),
                "command_type": command_type,
                "company_id": company_id,
                "branch_id": branch_id,
                "sequence": sequence,
                "warnings": warnings,
            },
        )

        out = {"command_id": str(command_id), "status": "APPLIED", "refs": refs}
        if warnings:
            out["warnings"] = warnings
        return out


def _reject_without_db(
    *, request, actor_user, device: Device, command_id: str, command_type: str, reason: str, details: dict
) -> dict[str, Any]:
    write_event(
        request=request,
        event_type="SYNC_COMMAND_REJECTED",
        reason_code=reason,
        actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
        subject_type="DEVICE",
        subject_id=str(device.id),
        device_id=str(device.id),
        offline_mode=True,
        metadata={"command_id": command_id, "command_type": command_type, **(details or {})},
    )
    return {"command_id": command_id, "status": "REJECTED", "reason": reason}


def _reject_with_db(
    *,
    request,
    actor_user,
    device: Device,
    command_id,
    company_id: int,
    branch_id: int | None,
    command_type: str,
    occurred_at,
    sequence,
    payload_hash: str,
    prev_hash: str,
    reason: str,
    details: dict,
) -> dict[str, Any]:
    try:
        with transaction.atomic():
            try:
                AppliedCommand.objects.create(
                    command_id=command_id,
                    device=device,
                    company_id=company_id,
                    branch_id=branch_id,
                    command_type=command_type,
                    occurred_at=occurred_at,
                    sequence=sequence,
                    payload_hash=payload_hash,
                    prev_hash=prev_hash,
                    result_status=AppliedCommand.ResultStatus.REJECTED,
                    result_ref={},
                    error={"reason": reason, **(details or {})},
                )
            except IntegrityError as e:
                # Puede ser: duplicate command_id, o falla de inserción por constraint (y no queda fila creada).
                row = AppliedCommand.objects.filter(command_id=command_id).first()

                if row is None:
                    # El INSERT falló y no existe fila => no permitimos que esto rompa el batch ni cambie el reason.
                    write_event(
                        request=request,
                        event_type="SYNC_COMMAND_REJECTED",
                        reason_code="SYNC_INTERNAL_ERROR",
                        actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
                        subject_type="DEVICE",
                        subject_id=str(device.id),
                        device_id=str(device.id),
                        offline_mode=True,
                        metadata={
                            "command_id": str(command_id),
                            "command_type": command_type,
                            "persist_error": repr(e),
                            "returned_reason": reason,
                        },
                    )
                    return {"command_id": str(command_id), "status": "REJECTED", "reason": reason}

                # Si existe y hash coincide => duplicate (incluye duplicates de rechazos previos)
                if row.payload_hash == payload_hash:
                    write_event(
                        request=request,
                        event_type="SYNC_COMMAND_DUPLICATE",
                        reason_code="SYNC_DUPLICATE",
                        actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
                        subject_type="DEVICE",
                        subject_id=str(device.id),
                        device_id=str(device.id),
                        offline_mode=True,
                        metadata={"command_id": str(command_id), "command_type": command_type},
                    )
                    return {"command_id": str(command_id), "status": "DUPLICATE", "refs": row.result_ref or {}}

                # Mismo ID, payload distinto => mismatch serio
                write_event(
                    request=request,
                    event_type="SYNC_COMMAND_REJECTED",
                    reason_code="SYNC_PAYLOAD_MISMATCH",
                    actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
                    subject_type="DEVICE",
                    subject_id=str(device.id),
                    device_id=str(device.id),
                    offline_mode=True,
                    metadata={
                        "command_id": str(command_id),
                        "command_type": command_type,
                        "existing_payload_hash": row.payload_hash,
                        "incoming_payload_hash": payload_hash,
                    },
                )
                return {"command_id": str(command_id), "status": "REJECTED", "reason": "SYNC_PAYLOAD_MISMATCH"}
    except Exception as e:
        # Blindaje final: jamás romper el batch por un problema de persistencia
        write_event(
            request=request,
            event_type="SYNC_COMMAND_REJECTED",
            reason_code="SYNC_INTERNAL_ERROR",
            actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
            subject_type="DEVICE",
            subject_id=str(device.id),
            device_id=str(device.id),
            offline_mode=True,
            metadata={
                "command_id": str(command_id),
                "command_type": command_type,
                "persist_error": repr(e),
                "returned_reason": reason,
            },
        )
        return {"command_id": str(command_id), "status": "REJECTED", "reason": reason}

    write_event(
        request=request,
        event_type="SYNC_COMMAND_REJECTED",
        reason_code=reason,
        actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
        subject_type="DEVICE",
        subject_id=str(device.id),
        device_id=str(device.id),
        offline_mode=True,
        metadata={"command_id": str(command_id), "command_type": command_type, **(details or {})},
    )
    return {"command_id": str(command_id), "status": "REJECTED", "reason": reason}
