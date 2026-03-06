import pytest
from django.core.management import call_command

from apps.audit.models import AuditEvent
from apps.rbac.models import Permission, Role, RolePermission


@pytest.mark.django_db
def test_seed_rbac_v01_command_creates_role_permissions_and_audit():
    call_command("seed_rbac_v01")

    role = Role.objects.get(name="company_admin")
    perm = Permission.objects.get(code="hr.position.create")
    assert RolePermission.objects.filter(role=role, permission=perm).exists()

    assert AuditEvent.objects.filter(event_type="RBAC_SEEDED_V01").exists()
