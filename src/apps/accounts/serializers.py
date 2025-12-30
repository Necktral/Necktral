from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

from apps.rbac.models import UserRole
from apps.rbac.selectors import get_effective_permissions

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(request=request, username=attrs["username"], password=attrs["password"])
        if user is None:
            raise serializers.ValidationError("Credenciales inválidas.", code="invalid_credentials")
        if not user.is_active:
            raise serializers.ValidationError("Usuario inactivo.", code="user_disabled")
        attrs["user"] = user
        return attrs


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_null=True)
    roles = serializers.ListField(child=serializers.CharField())
    permissions = serializers.ListField(child=serializers.CharField())

    @staticmethod
    def from_user(user):
        role_names = list(
            UserRole.objects.filter(user=user)
            .select_related("role")
            .values_list("role__name", flat=True)
        )
        perms = get_effective_permissions(user)
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "roles": sorted(set(role_names)),
            "permissions": perms,
        }
