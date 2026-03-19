from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from rest_framework import serializers

User = get_user_model()


class BootstrapInitAdminSerializer(serializers.Serializer):
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

        password_validation.validate_password(attrs["password"])
        return attrs
