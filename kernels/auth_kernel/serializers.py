from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import password_validation
from django.db.models import Q
from rest_framework import serializers

from apps.modulos.iam.models import UserMembership
from apps.modulos.rbac.models import Role
from apps.modulos.rbac.selectors import get_effective_permissions

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_null=True)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        username = (attrs.get("username") or "").strip()
        email = (attrs.get("email") or "").strip()

        if not username and email:
            user_by_email = User.objects.filter(email=email).first()
            if user_by_email is None:
                raise serializers.ValidationError("Credenciales inválidas.", code="invalid_credentials")
            username = user_by_email.username

        if not username:
            raise serializers.ValidationError({"username": "Requerido"})

        user = authenticate(request=request, username=username, password=attrs["password"])
        if user is None:
            raise serializers.ValidationError("Credenciales inválidas.", code="invalid_credentials")
        if not user.is_active:
            raise serializers.ValidationError("Usuario inactivo.", code="user_disabled")
        attrs["user"] = user
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate(self, attrs):
        newp = attrs["new_password"]
        conf = attrs.get("confirm_password", "")
        if conf and conf != newp:
            raise serializers.ValidationError({"confirm_password": "No coincide"})
        password_validation.validate_password(newp)
        return attrs


class TwoFactorSetupConfirmSerializer(serializers.Serializer):
    code = serializers.CharField()


class TwoFactorVerifySerializer(serializers.Serializer):
    challenge = serializers.CharField()
    code = serializers.CharField()


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_null=True)
    roles = serializers.ListField(child=serializers.CharField())
    permissions = serializers.ListField(child=serializers.CharField())
    must_change_password = serializers.BooleanField()
    is_setup_complete = serializers.BooleanField()

    @staticmethod
    def from_user(user):
        role_names = Role.objects.filter(
            Q(assignments__user=user, assignments__is_active=True) | Q(userrole__user=user)
        ).values_list("name", flat=True)
        perms = get_effective_permissions(user)
        is_setup_complete = UserMembership.objects.filter(user=user, is_active=True).exists()
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "roles": sorted(set(role_names)),
            "permissions": perms,
            "must_change_password": bool(getattr(user, "must_change_password", False)),
            "is_setup_complete": bool(is_setup_complete),
        }
