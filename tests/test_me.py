import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.rbac.models import Permission, Role, RolePermission, UserRole

User = get_user_model()


@pytest.mark.django_db
def test_me_returns_roles_and_permissions():
    user = User.objects.create_user(username="u3", password="pass12345")

    role = Role.objects.create(name="warehouse")
    perm = Permission.objects.create(code="inventory.read")
    RolePermission.objects.create(role=role, permission=perm)
    UserRole.objects.create(user=user, role=role)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "u3", "password": "pass12345"}, format="json")
    access = login.data["access"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert "warehouse" in me.data["roles"]
    assert "inventory.read" in me.data["permissions"]

