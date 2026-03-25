from __future__ import annotations

import base64
import json
from typing import Any

from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _decode_payload_unverified(raw_token: str) -> dict[str, Any]:
    try:
        parts = raw_token.split(".")
        if len(parts) != 3:
            return {}
        payload_part = parts[1]
        padding = "=" * (-len(payload_part) % 4)
        decoded = base64.urlsafe_b64decode((payload_part + padding).encode("utf-8"))
        payload = json.loads(decoded.decode("utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


class ReportingEmbedJWTAuthentication(BaseAuthentication):
    keyword = b"Bearer"

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth:
            return None
        if auth[0].lower() != self.keyword.lower():
            return None
        if len(auth) != 2:
            raise AuthenticationFailed("Authorization header inválido.")
        try:
            token_raw = auth[1].decode("utf-8")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            raise AuthenticationFailed("Authorization header inválido.") from exc

        unverified = _decode_payload_unverified(token_raw)
        if str(unverified.get("purpose") or "") != "reporting_embed":
            return None

        try:
            token = AccessToken(token_raw)
        except TokenError as exc:
            raise AuthenticationFailed("Token reporting inválido o expirado.") from exc

        if str(token.get("purpose") or "") != "reporting_embed":
            raise AuthenticationFailed("Token reporting inválido.")

        user_id = token.get("user_id")
        company_id = token.get("company_id")
        branch_id = token.get("branch_id")
        if not user_id or not company_id:
            raise AuthenticationFailed("Token reporting incompleto.")

        user = User.objects.filter(id=user_id, is_active=True).first()
        if user is None:
            raise AuthenticationFailed("Usuario inválido para token reporting.")

        company = OrgUnit.objects.filter(
            id=company_id,
            unit_type=OrgUnit.UnitType.COMPANY,
            is_active=True,
        ).first()
        if company is None:
            raise AuthenticationFailed("Scope company inválido para token reporting.")

        branch = None
        if branch_id is not None:
            branch = OrgUnit.objects.filter(
                id=branch_id,
                unit_type=OrgUnit.UnitType.BRANCH,
                parent=company,
                is_active=True,
            ).first()
            if branch is None:
                raise AuthenticationFailed("Scope branch inválido para token reporting.")

        self._set_context(request=request, company=company, branch=branch)
        perm_codes = [str(code).strip() for code in list(token.get("perm_codes") or []) if str(code).strip()]
        setattr(request, "reporting_effective_permissions", perm_codes)
        setattr(request, "rbac_effective_permissions_override", perm_codes)
        setattr(request, "reporting_consumer_type", "DASHBOARD")
        workspace_key = str(token.get("workspace_key") or "").strip().lower()
        if workspace_key:
            setattr(request, "reporting_consumer_ref", f"workspace:{workspace_key}")

        return (user, token)

    @staticmethod
    def _set_context(*, request, company, branch):
        setattr(request, "company", company)
        setattr(request, "branch", branch)
        setattr(request, "data_company", company)
        setattr(request, "data_branch", branch)
        setattr(
            request,
            "data_scope",
            {"company_id": getattr(company, "id", None), "branch_id": getattr(branch, "id", None)},
        )

        raw = getattr(request, "_request", None)
        if raw is not None:
            setattr(raw, "company", company)
            setattr(raw, "branch", branch)
            setattr(raw, "data_company", company)
            setattr(raw, "data_branch", branch)
            setattr(
                raw,
                "data_scope",
                {"company_id": getattr(company, "id", None), "branch_id": getattr(branch, "id", None)},
            )
