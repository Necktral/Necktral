"""Serializers del motor de sync (precedente).

Contrato de sync:
- Cada comando se firma (Ed25519) sobre un mensaje determinista (sin ambigüedad JSON).
- command_id es la clave de idempotencia.
- payload_hash puede enviarse (y se valida) o se calcula en servidor.
"""

from __future__ import annotations

from rest_framework import serializers


class EnrollmentChallengeCreateIn(serializers.Serializer):
    company_id = serializers.IntegerField(required=False)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    label_hint = serializers.CharField(required=False, allow_blank=True, max_length=200)
    expires_in_minutes = serializers.IntegerField(required=False, min_value=1, max_value=24 * 60)


class DeviceEnrollIn(serializers.Serializer):
    enrollment_code = serializers.CharField()
    public_key_b64 = serializers.CharField()
    label = serializers.CharField(required=False, allow_blank=True, max_length=200)  # type: ignore[assignment]
    meta = serializers.JSONField(required=False)


class SyncCommandIn(serializers.Serializer):
    """Entrada de un comando offline.

    Campos críticos:
    - command_id: idempotencia
    - occurred_at: timestamp del dispositivo (se canonicaliza para firma)
    - prev_hash: encadenamiento opcional (cliente) para detección de reordenamientos
    - signature: Ed25519 sobre el mensaje estable (ver signing.build_command_signing_message)
    """
    command_id = serializers.UUIDField()
    command_type = serializers.CharField(max_length=64)

    company_id = serializers.IntegerField()
    branch_id = serializers.IntegerField(required=False, allow_null=True)

    occurred_at = serializers.DateTimeField()
    sequence = serializers.IntegerField(required=False, allow_null=True)

    payload = serializers.JSONField()
    payload_hash = serializers.CharField(required=False, allow_blank=True, max_length=64)

    prev_hash = serializers.CharField(required=False, allow_blank=True, max_length=64)
    signature = serializers.CharField()


class SyncBatchIn(serializers.Serializer):
    """Entrada de un batch.

    Precedente:
    - device_id puede venir por body, pero X-Device-Id (header) tiene prioridad.
    - commands es una lista de comandos independientes (el servidor responde por comando).
    """
    batch_id = serializers.UUIDField()
    device_id = serializers.UUIDField(required=False)
    sent_at = serializers.DateTimeField(required=False)
    commands = SyncCommandIn(many=True)
