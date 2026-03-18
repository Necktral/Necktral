"""Verificación de integridad de auditoría (precedente).

Este verificador re-calcula hashes y firmas a partir del payload canónico y valida:
- event_hash (SHA256 del JSON canónico)
- signature (HMAC del event_hash)
- consistencia del encadenamiento por partición (prev_event_hash)

Importante:
- La verificación de cadena NO asume orden temporal; opera por partición y referencias de hash.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from django.db.models import QuerySet

from .keyring import get_audit_hmac_keyring
from .models import AuditChainHeadV2, AuditEvent


def _canon_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _hmac_hex(message_hex: str, *, key: str) -> str:
    return hmac.new(key.encode("utf-8"), message_hex.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class AuditIntegrityError:
    partition_key: str
    event_id: str
    code: str
    message: str
    expected: str | None = None
    got: str | None = None


@dataclass(frozen=True)
class AuditIntegrityReport:
    ok: bool
    partitions_scanned: int
    events_scanned: int
    errors: list[AuditIntegrityError]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "partitions_scanned": self.partitions_scanned,
            "events_scanned": self.events_scanned,
            "errors": [asdict(e) for e in self.errors],
        }


def _payload_for_event(ev: AuditEvent) -> dict[str, Any]:
    return {
        "event_id": str(ev.event_id),
        "schema_version": ev.schema_version,
        "module": ev.module,
        "event_type": ev.event_type,
        "reason_code": ev.reason_code,
        "subject_type": ev.subject_type,
        "subject_id": ev.subject_id,
        "partition_key": ev.partition_key,
        "timestamp_server": ev.timestamp_server.isoformat(),
        "actor_user_id": (str(ev.actor_user_id) if ev.actor_user_id else ""),
        "device_id": ev.device_id,
        "ip_server_seen": (str(ev.ip_server_seen) if ev.ip_server_seen else ""),
        "offline_mode": bool(ev.offline_mode),
        "user_agent": ev.user_agent,
        "path": ev.path,
        "method": ev.method,
        "before_snapshot": ev.before_snapshot or {},
        "after_snapshot": ev.after_snapshot or {},
        "metadata": ev.metadata or {},
        "prev_event_hash": ev.prev_event_hash or "",
    }


def verify_events(events: Iterable[AuditEvent]) -> AuditIntegrityReport:
    """Verifica hashes/firmas evento por evento.

    Contrato:
    - Retorna ok=True si no hay discrepancias.
    - No valida orden de encadenamiento (eso se hace en verify_queryset).
    """
    errors: list[AuditIntegrityError] = []
    events_scanned = 0
    partitions: set[str] = set()
    keyring = get_audit_hmac_keyring()
    key_map = {kid: key for kid, key in keyring}

    for ev in events:
        events_scanned += 1
        pk = ev.partition_key or ""
        partitions.add(pk)

        payload = _payload_for_event(ev)
        canonical = _canon_json(payload)
        expected_hash = _sha256_hex(canonical)
        got_hash = (ev.event_hash or "")
        if not got_hash:
            errors.append(
                AuditIntegrityError(
                    partition_key=pk,
                    event_id=str(ev.event_id),
                    code="MISSING_EVENT_HASH",
                    message="event_hash está vacío/null",
                    expected=expected_hash,
                    got=got_hash,
                )
            )
        elif got_hash != expected_hash:
            errors.append(
                AuditIntegrityError(
                    partition_key=pk,
                    event_id=str(ev.event_id),
                    code="EVENT_HASH_MISMATCH",
                    message="event_hash no coincide con el calculado desde el payload canónico",
                    expected=expected_hash,
                    got=got_hash,
                )
            )

        got_sig = (ev.signature or "")
        signature_ok = False
        expected_sig = None

        if ev.signature_key_id:
            key = key_map.get(ev.signature_key_id)
            if key:
                expected_sig = _hmac_hex(expected_hash, key=key)
                signature_ok = got_sig == expected_sig

        if not signature_ok:
            for kid, key in keyring:
                candidate = _hmac_hex(expected_hash, key=key)
                if got_sig == candidate:
                    signature_ok = True
                    if expected_sig is None:
                        expected_sig = candidate
                    break

        if expected_sig is None and keyring:
            expected_sig = _hmac_hex(expected_hash, key=keyring[0][1])

        if not got_sig:
            errors.append(
                AuditIntegrityError(
                    partition_key=pk,
                    event_id=str(ev.event_id),
                    code="MISSING_SIGNATURE",
                    message="signature está vacía/null",
                    expected=expected_sig,
                    got=got_sig,
                )
            )
        elif not signature_ok:
            errors.append(
                AuditIntegrityError(
                    partition_key=pk,
                    event_id=str(ev.event_id),
                    code="SIGNATURE_MISMATCH",
                    message="signature no coincide con HMAC(event_hash)",
                    expected=expected_sig,
                    got=got_sig,
                )
            )

    ok = len(errors) == 0
    return AuditIntegrityReport(
        ok=ok,
        partitions_scanned=len(partitions),
        events_scanned=events_scanned,
        errors=errors,
    )


def verify_queryset(qs: QuerySet[AuditEvent]) -> AuditIntegrityReport:
    """Verifica integridad completa desde la base.

    Incluye:
    - Re-cálculo de hashes/firmas
    - Reglas de encadenamiento por partición (génesis único, tail único, head existente)
    """
    ordered = list(qs.order_by("partition_key", "id"))
    report = verify_events(ordered)

    if not ordered:
        return report

    errors = list(report.errors)

    # Validación del encadenamiento por partición SIN asumir orden temporal.
    idx = 0
    while idx < len(ordered):
        pk = ordered[idx].partition_key
        group: list[AuditEvent] = []
        while idx < len(ordered) and ordered[idx].partition_key == pk:
            group.append(ordered[idx])
            idx += 1

        # 1) head
        try:
            head = AuditChainHeadV2.objects.get(partition_key=pk)
        except AuditChainHeadV2.DoesNotExist:
            errors.append(
                AuditIntegrityError(
                    partition_key=pk,
                    event_id=str(group[-1].event_id),
                    code="MISSING_CHAIN_HEAD",
                    message="No existe AuditChainHeadV2 para esta partición",
                )
            )
            continue

        # 2) mapa hash -> evento
        hash_to_event: dict[str, AuditEvent] = {}
        referenced_prev: set[str] = set()
        genesis_count = 0

        for ev in group:
            ev_hash = ev.event_hash or ""
            if not ev_hash:
                continue
            hash_to_event[ev_hash] = ev
            if ev.prev_event_hash:
                referenced_prev.add(ev.prev_event_hash)
            else:
                genesis_count += 1

        if genesis_count != 1:
            errors.append(
                AuditIntegrityError(
                    partition_key=pk,
                    event_id=str(group[-1].event_id),
                    code="CHAIN_GENESIS_COUNT",
                    message="La partición debe tener exactamente un evento génesis (prev_event_hash='')",
                    expected="1",
                    got=str(genesis_count),
                )
            )

        # 3) tail: el que no es prev de nadie
        tails = [
            ev
            for ev in group
            if (ev.event_hash or "") and (ev.event_hash not in referenced_prev)
        ]
        if len(tails) != 1:
            errors.append(
                AuditIntegrityError(
                    partition_key=pk,
                    event_id=str(group[-1].event_id),
                    code="CHAIN_TAIL_COUNT",
                    message="La partición debe tener exactamente un tail (último evento)",
                    expected="1",
                    got=str(len(tails)),
                )
            )
            continue

        tail = tails[0]

        # 4) head debe apuntar al tail
        if (head.last_event_hash or "") != (tail.event_hash or ""):
            errors.append(
                AuditIntegrityError(
                    partition_key=pk,
                    event_id=str(tail.event_id),
                    code="CHAIN_HEAD_MISMATCH",
                    message="AuditChainHeadV2.last_event_hash no coincide con el tail",
                    expected=(tail.event_hash or ""),
                    got=(head.last_event_hash or ""),
                )
            )

        # 5) recorrido desde el head para detectar ciclos/desconexiones
        start_hash = head.last_event_hash or (tail.event_hash or "")
        if not start_hash or start_hash not in hash_to_event:
            errors.append(
                AuditIntegrityError(
                    partition_key=pk,
                    event_id=str(tail.event_id),
                    code="CHAIN_HEAD_UNKNOWN_HASH",
                    message="El head apunta a un hash inexistente en los eventos",
                    got=(head.last_event_hash or ""),
                )
            )
            continue

        visited: set[str] = set()
        cur = hash_to_event[start_hash]
        while True:
            cur_hash = cur.event_hash or ""
            if not cur_hash:
                break
            if cur_hash in visited:
                errors.append(
                    AuditIntegrityError(
                        partition_key=pk,
                        event_id=str(cur.event_id),
                        code="CHAIN_CYCLE",
                        message="Se detectó un ciclo en la cadena",
                    )
                )
                break
            visited.add(cur_hash)

            prev = cur.prev_event_hash or ""
            if not prev:
                break
            prev_ev = hash_to_event.get(prev)
            if not prev_ev:
                errors.append(
                    AuditIntegrityError(
                        partition_key=pk,
                        event_id=str(cur.event_id),
                        code="CHAIN_MISSING_PREV_LINK",
                        message="prev_event_hash apunta a un hash inexistente",
                        got=prev,
                    )
                )
                break
            cur = prev_ev

        if len(visited) != len(hash_to_event):
            errors.append(
                AuditIntegrityError(
                    partition_key=pk,
                    event_id=str(tail.event_id),
                    code="CHAIN_DISCONNECTED",
                    message="La cadena no cubre todos los eventos (posible rama o desconexión)",
                    expected=str(len(hash_to_event)),
                    got=str(len(visited)),
                )
            )

    return AuditIntegrityReport(
        ok=len(errors) == 0,
        partitions_scanned=report.partitions_scanned,
        events_scanned=report.events_scanned,
        errors=errors,
    )
