from __future__ import annotations

from rest_framework.exceptions import NotFound, ParseError, PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.iam.models import OrgUnit, UserMembership


class JWTAuthWithOrgContext(JWTAuthentication):
    """
    Autenticación JWT + contexto organizacional:
      - Autentica al usuario
      - En endpoints operativos exige X-Company-Id
      - Opcional X-Branch-Id
      - Inyecta request.company y request.branch en DRF Request y HttpRequest
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

    def authenticate(self, request):
        auth_result = super().authenticate(request)
        if auth_result is None:
            return None

        user, token = auth_result

        path = getattr(request, "path", "") or ""
        if any(path.startswith(p) for p in self.EXEMPT_PATH_PREFIXES):
            return (user, token)

        # --- Context headers ---
        company_id = request.headers.get("X-Company-Id")
        branch_id = request.headers.get("X-Branch-Id")

        if not company_id:
            raise ParseError("X-Company-Id requerido.")

        try:
            company_id_int = int(company_id)
        except ValueError:
            raise ParseError("X-Company-Id inválido.")

        company = OrgUnit.objects.filter(
            id=company_id_int,
            unit_type=OrgUnit.UnitType.COMPANY,
            is_active=True,
        ).first()
        if not company:
            raise NotFound("Empresa no encontrada o inactiva.")

        # Membresía a company o a alguna branch bajo company
        has_company_membership = UserMembership.objects.filter(user=user, org_unit=company, is_active=True).exists()
        has_branch_under_company = UserMembership.objects.filter(
            user=user,
            is_active=True,
            org_unit__unit_type=OrgUnit.UnitType.BRANCH,
            org_unit__parent=company,
        ).exists()

        if not (has_company_membership or has_branch_under_company):
            # deja rastro de scope requerido para auditoría
            self._set_required_scope(request, company_id=company.id, branch_id=None)
            raise PermissionDenied("Sin acceso a esta empresa.")

        branch = None
        if branch_id:
            try:
                branch_id_int = int(branch_id)
            except ValueError:
                raise ParseError("X-Branch-Id inválido.")

            branch = OrgUnit.objects.filter(
                id=branch_id_int,
                unit_type=OrgUnit.UnitType.BRANCH,
                parent=company,
                is_active=True,
            ).first()
            if not branch:
                raise NotFound("Sucursal no encontrada o inactiva.")

            if not has_company_membership:
                has_branch_membership = UserMembership.objects.filter(user=user, org_unit=branch, is_active=True).exists()
                if not has_branch_membership:
                    self._set_required_scope(request, company_id=company.id, branch_id=branch.id)
                    raise PermissionDenied("Sin acceso a esta sucursal.")

        # Inyectar contexto
        self._set_context(request, company=company, branch=branch)

        # -----------------------------
        # Data scope (opcional): permite pedir datos de otra empresa
        # Headers:
        #   X-Data-Company-Id
        #   X-Data-Branch-Id
        # -----------------------------
        data_company_id = request.headers.get("X-Data-Company-Id")
        data_branch_id = request.headers.get("X-Data-Branch-Id")

        data_company = company
        data_branch = branch

        if data_company_id:
            try:
                data_company_id_int = int(data_company_id)
            except ValueError:
                raise ParseError("X-Data-Company-Id inválido.")

            dc = OrgUnit.objects.filter(
                id=data_company_id_int,
                unit_type=OrgUnit.UnitType.COMPANY,
                is_active=True,
            ).first()
            if not dc:
                raise NotFound("Data company no encontrada o inactiva.")

            data_company = dc
            data_branch = None  # si cambia la data-company, la branch se re-resuelve

        if data_branch_id:
            try:
                data_branch_id_int = int(data_branch_id)
            except ValueError:
                raise ParseError("X-Data-Branch-Id inválido.")

            db = OrgUnit.objects.filter(
                id=data_branch_id_int,
                unit_type=OrgUnit.UnitType.BRANCH,
                parent=data_company,
                is_active=True,
            ).first()
            if not db:
                raise NotFound("Data branch no encontrada o inactiva.")

            data_branch = db

        # Regla fuerte en esta fase:
        # No se permite data_branch distinto al branch activo si la data_company es la misma.
        if data_company.id == company.id and branch is not None and data_branch is not None and data_branch.id != branch.id:
            raise ParseError("No se permite X-Data-Branch-Id distinto al contexto activo en la misma empresa.")

        # Inyectar data scope en request (DRF y Django HttpRequest)
        self._set_context(request, company=company, branch=branch)
        setattr(request, "data_company", data_company)
        setattr(request, "data_branch", data_branch)
        raw = getattr(request, "_request", None)
        if raw is not None:
            setattr(raw, "data_company", data_company)
            setattr(raw, "data_branch", data_branch)

        data_scope = {"company_id": data_company.id, "branch_id": getattr(data_branch, "id", None)}
        setattr(request, "data_scope", data_scope)
        if raw is not None:
            setattr(raw, "data_scope", data_scope)

        if data_company.id != company.id:
            intercompany_meta = {
                "from_company_id": data_company.id,
                "to_company_id": company.id,
                "mode": "READ",
            }
            setattr(request, "intercompany", intercompany_meta)
            if raw is not None:
                setattr(raw, "intercompany", intercompany_meta)

        return (user, token)

    @staticmethod
    def _set_context(request, *, company, branch):
        # DRF Request
        setattr(request, "company", company)
        setattr(request, "branch", branch)

        # Django HttpRequest (por si algún middleware/otra capa lo lee)
        raw = getattr(request, "_request", None)
        if raw is not None:
            setattr(raw, "company", company)
            setattr(raw, "branch", branch)

    @staticmethod
    def _set_required_scope(request, *, company_id, branch_id):
        scope = {"company_id": company_id, "branch_id": branch_id}
        setattr(request, "required_scope", scope)
        raw = getattr(request, "_request", None)
        if raw is not None:
            setattr(raw, "required_scope", scope)
