import pytest

from apps.rbac.models import Permission
from apps.rbac.permissions_registry import PERMISSIONS_REGISTRY
from apps.rbac.seed_v01 import seed_rbac_v01


@pytest.mark.django_db
def test_permissions_registry_covers_seeded_permissions():
    seed_rbac_v01()
    codes = set(Permission.objects.values_list("code", flat=True))
    missing = codes - set(PERMISSIONS_REGISTRY.keys())
    assert not missing, f"Permisos sin registry: {sorted(missing)}"
