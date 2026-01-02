from __future__ import annotations

from rest_framework import serializers

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
    first_name = serializers.CharField(max_length=120)
    last_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    linked_user_id = serializers.IntegerField(required=False)

class EmployeeUpdateSerializer(serializers.Serializer):
    employee_code = serializers.CharField(max_length=64, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=120, required=False)
    last_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    linked_user_id = serializers.IntegerField(required=False, allow_null=True)

class AssignmentCreateSerializer(serializers.Serializer):
    position_id = serializers.IntegerField()
    branch_id = serializers.IntegerField(required=False, allow_null=True)
