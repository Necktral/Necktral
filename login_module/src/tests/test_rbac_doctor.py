from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.rbac.permissions_registry import PERMISSIONS_REGISTRY, PermissionMeta
from apps.rbac.seed_v01 import seed_rbac_v01


@pytest.mark.django_db
def test_rbac_doctor_fails_on_expired_registry_permission():
    seed_rbac_v01()

    code = "org.company.create"
    original = PERMISSIONS_REGISTRY[code]

    try:
        PERMISSIONS_REGISTRY[code] = PermissionMeta(
            owner_team=original.owner_team,
            risk_level=original.risk_level,
            default_roles=original.default_roles,
            expires_at=timezone.now().date() - timedelta(days=1),
        )

        with pytest.raises(SystemExit) as exc:
            call_command("rbac_doctor")

        assert exc.value.code == 2
    finally:
        PERMISSIONS_REGISTRY[code] = original
