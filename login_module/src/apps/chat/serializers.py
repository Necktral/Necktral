from __future__ import annotations

from rest_framework import serializers

from .models import Message


class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source="sender.username", read_only=True)

    class Meta:
        model = Message
        fields = ["id", "sender_username", "content", "created_at"]
        read_only_fields = ["id", "sender_username", "created_at"]


class MessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=4000)
