from __future__ import annotations

from rest_framework import serializers

from .models import InboxEvent


class OutboxMarkSentIn(serializers.Serializer):
    published_at = serializers.DateTimeField(required=False)


class InboxAckIn(serializers.Serializer):
    status = serializers.ChoiceField(choices=[InboxEvent.Status.PROCESSED, InboxEvent.Status.FAILED], required=False)
    error = serializers.CharField(max_length=255, required=False, allow_blank=True)
