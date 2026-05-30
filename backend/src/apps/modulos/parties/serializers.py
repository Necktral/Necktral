from __future__ import annotations

from rest_framework import serializers

from .models import Party, PartyRole


class PartyRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartyRole
        fields = ["id", "role", "is_active", "valid_from", "valid_to", "created_at"]
        read_only_fields = ["id", "created_at"]


class PartyListSerializer(serializers.ModelSerializer):
    roles = PartyRoleSerializer(many=True, read_only=True, source="roles")

    class Meta:
        model = Party
        fields = [
            "id",
            "company_id",
            "party_type",
            "display_name",
            "legal_name",
            "tax_id",
            "national_id",
            "email",
            "phone",
            "status",
            "created_at",
            "updated_at",
            "roles",
        ]
        read_only_fields = ["id", "company_id", "created_at", "updated_at"]


class PartyCreateSerializer(serializers.Serializer):
    party_type = serializers.ChoiceField(choices=Party.PartyType.choices)
    display_name = serializers.CharField(max_length=200)
    legal_name = serializers.CharField(max_length=255, required=False, default="")
    tax_id = serializers.CharField(max_length=64, required=False, default="")
    national_id = serializers.CharField(max_length=64, required=False, default="")
    email = serializers.EmailField(required=False, default="")
    phone = serializers.CharField(max_length=64, required=False, default="")
    status = serializers.ChoiceField(choices=Party.Status.choices, required=False, default=Party.Status.ACTIVE)


class PartyUpdateSerializer(serializers.Serializer):
    party_type = serializers.ChoiceField(choices=Party.PartyType.choices, required=False)
    display_name = serializers.CharField(max_length=200, required=False)
    legal_name = serializers.CharField(max_length=255, required=False)
    tax_id = serializers.CharField(max_length=64, required=False)
    national_id = serializers.CharField(max_length=64, required=False)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(max_length=64, required=False)
    status = serializers.ChoiceField(choices=Party.Status.choices, required=False)


class PartyRoleAssignSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=PartyRole.Role.choices)
    valid_from = serializers.DateTimeField(required=False, allow_null=True)


class PartyRoleRevokeSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=PartyRole.Role.choices)
    valid_to = serializers.DateTimeField(required=False, allow_null=True)
