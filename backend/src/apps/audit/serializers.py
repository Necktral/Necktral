from rest_framework import serializers
from .models import AuditEvent


class AuditEventListSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "event_id",
            "schema_version",
            "module",
            "event_type",
            "reason_code",
            "partition_key",
            "timestamp_server",
            "actor_user",
            "device_id",
            "ip_server_seen",
            "offline_mode",
            "path",
            "method",
            "subject_type",
            "subject_id",
            "metadata",
        ]


class AuditEventDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = "__all__"
