from __future__ import annotations

from django.db.models import Q


## from apps.iam.models import OrgUnit
## from .models import Permission, RolePermission, UserRole, RoleAssignment
def get_effective_permissions_for_scope(user, *, company: OrgUnit, branch: OrgUnit | None = None, include_global: bool = True) -> set[str]:
    """
    Permisos efectivos para un usuario en un contexto (company + opcional branch).

    Reglas:
      - si hay RoleAssignment a COMPANY aplica a toda la empresa (todas sus branches)
      - si hay RoleAssignment a BRANCH aplica solo a esa branch
      - include_global=True incluye UserRole (legacy) como permisos globales (transicional)
    """

    from .models import RoleAssignment, RolePermission, UserRole
    role_ids: set[int] = set()

    # Scoped: company roles
    company_role_ids = RoleAssignment.objects.filter(
        user=user,
        is_active=True,
        org_unit=company,
    ).values_list("role_id", flat=True)
    role_ids.update(company_role_ids)

    # Scoped: branch roles (solo si branch existe)
    if branch is not None:
        branch_role_ids = RoleAssignment.objects.filter(
            user=user,
            is_active=True,
            org_unit=branch,
        ).values_list("role_id", flat=True)
        role_ids.update(branch_role_ids)

    # Legacy/global (transición)
    if include_global:
        global_role_ids = UserRole.objects.filter(user=user).values_list("role_id", flat=True)
        role_ids.update(global_role_ids)

    if not role_ids:
        return set()

    perm_codes = RolePermission.objects.filter(role_id__in=list(role_ids)).select_related("permission").values_list("permission__code", flat=True)
    return set(perm_codes)


def get_effective_permissions(user) -> list[str]:
    if user.is_superuser:
        return ["*"]

    from .models import Permission, RolePermission, UserRole
    role_ids = UserRole.objects.filter(user=user).values_list("role_id", flat=True)
    perm_ids = RolePermission.objects.filter(role_id__in=role_ids).values_list("permission_id", flat=True)

    perms = (
        Permission.objects.filter(Q(id__in=perm_ids), is_active=True)
        .values_list("code", flat=True)
    )
    return sorted(set(perms))
