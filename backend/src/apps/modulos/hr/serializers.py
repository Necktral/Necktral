from __future__ import annotations

from rest_framework import serializers


# Payload para reset password provisional
class ResetTempPasswordSerializer(serializers.Serializer):
    temp_password = serializers.CharField(required=False, allow_blank=True, default="")


class EmployeeRevokeAccessSerializer(serializers.Serializer):
    # Si True: intenta setear user.is_active=False, pero solo si el usuario ya no tiene
    # memberships activas en ninguna otra org_unit
    disable_user = serializers.BooleanField(required=False, default=False)


class PositionCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class PositionUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    code = serializers.CharField(max_length=64, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class PositionRoleMapUpdateSerializer(serializers.Serializer):
    maps = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=True,
    )


class EmployeeCreateSerializer(serializers.Serializer):
    employee_code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    party_id = serializers.IntegerField(required=False)
    first_name = serializers.CharField(max_length=120)
    last_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False, default=True)
    linked_user_id = serializers.IntegerField(required=False)


class EmployeeUpdateSerializer(serializers.Serializer):
    employee_code = serializers.CharField(max_length=64, required=False, allow_blank=True)
    party_id = serializers.IntegerField(required=False, allow_null=True)
    first_name = serializers.CharField(max_length=120, required=False)
    last_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    linked_user_id = serializers.IntegerField(required=False, allow_null=True)


class AssignmentCreateSerializer(serializers.Serializer):
    position_id = serializers.IntegerField()
    branch_id = serializers.IntegerField(required=False, allow_null=True)


class EmployeeProvisionUserSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    temp_password = serializers.CharField(required=False, allow_blank=True, default="")
