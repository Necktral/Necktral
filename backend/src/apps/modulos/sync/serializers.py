from __future__ import annotations

from rest_framework import serializers


class CommandSerializer(serializers.Serializer):
    command_id = serializers.UUIDField()
    type = serializers.CharField(max_length=64)
    payload = serializers.DictField(child=serializers.JSONField(), required=False, default=dict)


class SyncBatchSerializer(serializers.Serializer):
    commands = CommandSerializer(many=True)
