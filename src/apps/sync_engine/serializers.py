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
    label = serializers.CharField(required=False, allow_blank=True, max_length=200)
    meta = serializers.JSONField(required=False)


class SyncCommandIn(serializers.Serializer):
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
    batch_id = serializers.UUIDField()
    device_id = serializers.UUIDField(required=False)
    sent_at = serializers.DateTimeField(required=False)
    commands = SyncCommandIn(many=True)
