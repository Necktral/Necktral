from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import password_validation
from django.db.models import Q
from rest_framework import serializers

from apps.rbac.models import Role
from apps.rbac.selectors import get_effective_permissions
from apps.iam.models import UserMembership

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


class BootstrapInitSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        username = attrs.get("username", "").strip()
        if not username:
            raise serializers.ValidationError({"username": "Requerido"})
        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError({"username": "Ya existe"})

        email = attrs.get("email", None)
        if email:
            email = str(email).strip()
            if User.objects.filter(email=email).exists():
                raise serializers.ValidationError({"email": "Ya existe"})
            attrs["email"] = email

        # Password validators (mínimo robusto)
        password_validation.validate_password(attrs["password"])
        return attrs


class BootstrapOrgSerializer(serializers.Serializer):
    holding_name = serializers.CharField()
    company_name = serializers.CharField()
    company_tax_id = serializers.CharField(required=False, allow_blank=True)
    branch_name = serializers.CharField()
    branch_address = serializers.CharField(required=False, allow_blank=True)


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


class AxesUnlockSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    ip_address = serializers.IPAddressField(required=False, allow_blank=True)


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
        # Roles:
        # - Nuevo modelo: RoleAssignment (scoped por OrgUnit) => related_name "assignments"
        # - Legacy/transición: UserRole (global) => reverse relation "userrole"
        role_names = Role.objects.filter(
            Q(assignments__user=user, assignments__is_active=True) | Q(userrole__user=user)
        ).values_list("name", flat=True)
        perms = get_effective_permissions(user)

        # Setup global: depende de si el usuario tiene al menos una membership activa
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
