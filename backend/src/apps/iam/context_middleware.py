"""Middleware de contexto organizacional (precedente).

Responsabilidad:
- Resolver e inyectar request.company y request.branch según headers.

Nota:
- En este repo también existe JWTAuthWithOrgContext que realiza una función similar.
    El precedente es que *alguna* de estas capas debe garantizar que las vistas operen con contexto.
"""

from __future__ import annotations

from django.http import JsonResponse

from apps.iam.context import attach_request_context
from apps.iam.models import OrgUnit, UserMembership


class OrgContextMiddleware:
    """
    Inyecta contexto organizacional:
      - request.company (OrgUnit COMPANY)
      - request.branch (OrgUnit BRANCH | None)

    En endpoints operativos exige X-Company-Id.
    """

    EXEMPT_PATH_PREFIXES = (
        "/admin/",
        "/api/auth/login/",
        "/api/auth/refresh/",
        "/api/auth/logout/",
        "/api/auth/me/",
        "/api/auth/me/acl/",
        "/api/schema/",
        "/api/docs/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = getattr(request, "path", "") or ""

        if any(path.startswith(p) for p in self.EXEMPT_PATH_PREFIXES):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            # Precedente: no devolvemos 401 aquí; dejamos que DRF lo gestione.
            # El middleware de auditoría capturará la denegación si corresponde.
            return self.get_response(request)

        # Regla fuerte: sin X-Company-Id no hay contexto operativo.
        company_id = request.headers.get("X-Company-Id")
        branch_id = request.headers.get("X-Branch-Id")

        if not company_id:
            return JsonResponse({"detail": "X-Company-Id requerido."}, status=400)

        try:
            company_id_int = int(company_id)
        except ValueError:
            return JsonResponse({"detail": "X-Company-Id inválido."}, status=400)

        company = OrgUnit.objects.filter(id=company_id_int, unit_type=OrgUnit.UnitType.COMPANY, is_active=True).first()
        if not company:
            return JsonResponse({"detail": "Empresa no encontrada o inactiva."}, status=404)

        # Verificar acceso a company por membresía:
        has_company_membership = UserMembership.objects.filter(user=user, org_unit=company, is_active=True).exists()
        has_branch_under_company = UserMembership.objects.filter(
            user=user,
            is_active=True,
            org_unit__unit_type=OrgUnit.UnitType.BRANCH,
            org_unit__parent=company,
        ).exists()

        if not (has_company_membership or has_branch_under_company):
            # marcar scope requerido para auditoría (lo leerá AuditAccessDeniedMiddleware)
            setattr(request, "required_scope", {"company_id": company.id, "branch_id": None})
            return JsonResponse({"detail": "Sin acceso a esta empresa."}, status=403)

        branch = None
        if branch_id:
            try:
                branch_id_int = int(branch_id)
            except ValueError:
                return JsonResponse({"detail": "X-Branch-Id inválido."}, status=400)

            branch = OrgUnit.objects.filter(
                id=branch_id_int,
                unit_type=OrgUnit.UnitType.BRANCH,
                parent=company,
                is_active=True,
            ).first()
            if not branch:
                return JsonResponse({"detail": "Sucursal no encontrada o inactiva."}, status=404)

            # Si tiene membresía a company, permite cualquier branch; si no, exige membresía exacta a branch
            if not has_company_membership:
                has_branch_membership = UserMembership.objects.filter(
                    user=user, org_unit=branch, is_active=True
                ).exists()
                if not has_branch_membership:
                    setattr(request, "required_scope", {"company_id": company.id, "branch_id": branch.id})
                    return JsonResponse({"detail": "Sin acceso a esta sucursal."}, status=403)

        # Inyectar contexto para vistas
        setattr(request, "company", company)
        setattr(request, "branch", branch)

        attach_request_context(
            request,
            company=company,
            branch=branch,
            data_company=company,
            data_branch=branch,
        )

        return self.get_response(request)
