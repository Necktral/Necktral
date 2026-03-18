from __future__ import annotations

import hashlib
import json
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.rbac.selectors import get_effective_permissions_for_scope

from .models import AdminGrant, CompanyLink, LinkGrant, OrgUnit, UserMembership


def has_intercompany_grant(
    *,
    from_company: OrgUnit,
    to_company: OrgUnit,
    permission_code: str,
    mode: str = "READ",
    scope_branch: OrgUnit | None = None,
) -> bool:
    """
    Verifica si existe una concesión activa para permitir que `to_company` acceda a datos de `from_company`.

    Reglas:
      - Debe existir CompanyLink activo: from_company -> to_company
      - Debe existir LinkGrant activo con permission_code y access_mode
      - scope_branch:
          * si se provee, se acepta grant específico a esa branch O grant a toda la empresa (scope_org_unit NULL)
          * si no se provee, basta grant a toda la empresa (scope_org_unit NULL) o cualquier (pero aquí pedimos NULL)
    """
    if from_company.id == to_company.id:
        return True

    now = timezone.now()

    link = CompanyLink.objects.filter(
        from_company=from_company,
        to_company=to_company,
        is_active=True,
        status=CompanyLink.Status.ACTIVE,
    ).first()

    if not link:
        return False

    qs = (
        LinkGrant.objects.filter(
            link=link,
            is_active=True,
            access_mode=mode,
            permission__code=permission_code,
        )
        .filter(models.Q(valid_from__isnull=True) | models.Q(valid_from__lte=now))
        .filter(models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=now))
    )

    if scope_branch is None:
        # Para company-wide, requerimos scope_org_unit NULL
        return qs.filter(scope_org_unit__isnull=True).exists()

    # Para branch, aceptamos grant específico a la branch o grant global (NULL)
    return qs.filter(models.Q(scope_org_unit__isnull=True) | models.Q(scope_org_unit=scope_branch)).exists()


def _canon_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def get_accessible_companies(user) -> list[OrgUnit]:
    """
    Empresas accesibles por membresía:
    - membresía directa a COMPANY
    - membresía a BRANCH => se eleva a su parent COMPANY
    """
    memberships = UserMembership.objects.filter(user=user, is_active=True).select_related(
        "org_unit", "org_unit__parent"
    )
    company_ids: set[int] = set()

    for m in memberships:
        ou = m.org_unit
        if ou.unit_type == OrgUnit.UnitType.COMPANY:
            company_ids.add(ou.id)
        elif ou.unit_type == OrgUnit.UnitType.BRANCH and ou.parent_id:
            company_ids.add(ou.parent_id)

    return list(
        OrgUnit.objects.filter(id__in=company_ids, unit_type=OrgUnit.UnitType.COMPANY, is_active=True).order_by("name")
    )


def get_accessible_branches(user, company: OrgUnit) -> list[OrgUnit]:
    """
    Sucursales accesibles dentro de una compañía.
    Si hay membresía directa a COMPANY, se interpreta como acceso a todas las BRANCH de esa COMPANY.
    Si no, se limita a las BRANCH donde tenga membresía directa.
    """
    mem_company = UserMembership.objects.filter(user=user, org_unit=company, is_active=True).exists()
    if mem_company:
        return list(
            OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH, is_active=True).order_by("name")
        )

    branch_ids = UserMembership.objects.filter(
        user=user, is_active=True, org_unit__unit_type=OrgUnit.UnitType.BRANCH, org_unit__parent=company
    ).values_list("org_unit_id", flat=True)
    return list(OrgUnit.objects.filter(id__in=list(branch_ids), is_active=True).order_by("name"))


def get_admin_caps_snapshot(user, companies: list[OrgUnit]) -> dict[str, dict[str, bool]]:
    """
    Retorna capacidades admin por company_id:
      { "<company_id>": { "MANAGE_USERS": true, ... } }
    """
    grants = AdminGrant.objects.filter(user=user, is_active=True).select_related("org_unit")
    caps_by_company: dict[str, dict[str, bool]] = {}

    company_ids = {c.id for c in companies}

    for g in grants:
        ou = g.org_unit
        # Normalizamos el "scope principal" a compañía:
        if ou.unit_type == OrgUnit.UnitType.COMPANY and ou.id in company_ids:
            key = str(ou.id)
        elif ou.unit_type == OrgUnit.UnitType.BRANCH and ou.parent_id in company_ids:
            key = str(ou.parent_id)
        elif ou.unit_type == OrgUnit.UnitType.HOLDING:
            # Holding aplica a todas las companies accesibles del usuario
            for cid in company_ids:
                caps_by_company.setdefault(str(cid), {})[g.capability] = True
            continue
        else:
            continue

        caps_by_company.setdefault(key, {})[g.capability] = True

    # Completar faltantes con False para estabilidad en UI móvil
    all_caps = [c for c, _ in AdminGrant.Capability.choices]
    for c in companies:
        entry = caps_by_company.setdefault(str(c.id), {})
        for cap in all_caps:
            entry.setdefault(cap, False)

    return caps_by_company


def build_acl_snapshot(user) -> dict:
    """
    Snapshot de control de acceso para la PWA.
    - Diseñado para cache y offline
    - Permisos (por ahora) globales del usuario; luego se extiende a permisos por empresa/scope.
    """
    companies = get_accessible_companies(user)

    companies_payload: list[dict[str, Any]] = []
    for company in companies:
        branches = get_accessible_branches(user, company)
        include_global = bool(getattr(settings, "RBAC_INCLUDE_GLOBAL_USERROLES", True))
        perms_for_company = sorted(
            list(get_effective_permissions_for_scope(user, company=company, branch=None, include_global=include_global))
        )

        companies_payload.append(
            {
                "company_id": company.id,
                "company_name": company.name,
                "branches": [{"branch_id": b.id, "branch_name": b.name} for b in branches],
                "permissions": perms_for_company,
            }
        )

    admin_caps = get_admin_caps_snapshot(user, companies)

    payload: dict[str, Any] = {
        "user_id": user.id,
        "username": getattr(user, "username", ""),
        "server_time": timezone.now().isoformat(),
        "companies": companies_payload,
        "admin_caps_by_company": admin_caps,
    }

    acl_version = _sha256_hex(_canon_json(payload))
    payload["acl_version"] = acl_version

    # Recomendación de contexto inicial (mobile-first)
    if len(companies_payload) == 1:
        payload["recommended_company_id"] = companies_payload[0]["company_id"]
        payload["recommended_branch_id"] = (
            companies_payload[0]["branches"][0]["branch_id"] if companies_payload[0]["branches"] else None
        )
    else:
        payload["recommended_company_id"] = None
        payload["recommended_branch_id"] = None

    return payload
