from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.permissions import rbac_permission
from apps.iam.authentication import JWTAuthWithOrgContext
from apps.iam.models import CompanyLink, LinkGrant, OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org_tree(label: str) -> tuple[OrgUnit, OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H-{label}", code=f"H-{label}")
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        name=f"C-{label}",
        code=f"C-{label}",
        parent=holding,
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        name=f"B-{label}",
        code=f"B-{label}",
        parent=company,
    )
    return holding, company, branch


def _mk_user(*, label: str, password: str = "Pass12345!") -> User:
    return User.objects.create_user(username=f"user_{label}", email=f"{label}@test.com", password=password)


def _mk_token(user: User) -> str:
    return str(RefreshToken.for_user(user).access_token)


def _drf_request(
    *,
    token: str,
    company_id: int,
    branch_id: int | None = None,
    data_company_id: int | None = None,
    data_branch_id: int | None = None,
) -> Request:
    factory = APIRequestFactory()
    headers: dict[str, str] = {
        "HTTP_AUTHORIZATION": f"Bearer {token}",
        "HTTP_X_COMPANY_ID": str(company_id),
    }
    if branch_id is not None:
        headers["HTTP_X_BRANCH_ID"] = str(branch_id)
    if data_company_id is not None:
        headers["HTTP_X_DATA_COMPANY_ID"] = str(data_company_id)
    if data_branch_id is not None:
        headers["HTTP_X_DATA_BRANCH_ID"] = str(data_branch_id)
    return Request(factory.get("/api/iam/context/", **headers))


def _grant_local_permission(*, user: User, company: OrgUnit, branch: OrgUnit, permission_code: str) -> None:
    role = Role.objects.create(name=f"role-{uuid.uuid4().hex[:8]}", is_active=True)
    perm, _ = Permission.objects.get_or_create(
        code=permission_code,
        defaults={"description": permission_code, "is_active": True},
    )
    RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)


def _grant_intercompany_read(*, from_company: OrgUnit, to_company: OrgUnit, permission_code: str) -> None:
    perm, _ = Permission.objects.get_or_create(
        code=permission_code,
        defaults={"description": permission_code, "is_active": True},
    )
    link = CompanyLink.objects.create(from_company=from_company, to_company=to_company)
    LinkGrant.objects.create(link=link, permission=perm, access_mode=LinkGrant.AccessMode.READ)


def _login_client(*, user: User, password: str, company: OrgUnit, branch: OrgUnit) -> APIClient:
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": user.username, "password": password}, format="json")
    assert resp.status_code == 200
    access = resp.data.get("access")
    assert isinstance(access, str) and access
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {access}",
        HTTP_X_COMPANY_ID=str(company.id),
        HTTP_X_BRANCH_ID=str(branch.id),
    )
    return client


def _login_access_token(*, user: User, password: str) -> str:
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": user.username, "password": password}, format="json")
    assert resp.status_code == 200
    access = resp.data.get("access")
    assert isinstance(access, str) and access
    return access


@pytest.mark.django_db
def test_jwt_auth_marks_intercompany_data_scope_for_reads():
    _, company, branch = _mk_org_tree("main")
    _, foreign_company, _ = _mk_org_tree("foreign")
    user = _mk_user(label="intercompany")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    request = _drf_request(
        token=_mk_token(user),
        company_id=company.id,
        branch_id=branch.id,
        data_company_id=foreign_company.id,
    )

    auth_result = JWTAuthWithOrgContext().authenticate(request)

    assert auth_result is not None
    assert request.company.id == company.id
    assert request.branch.id == branch.id
    assert request.data_company.id == foreign_company.id
    assert request.data_branch is None
    assert request.data_scope == {"company_id": foreign_company.id, "branch_id": None}
    assert request.intercompany == {
        "from_company_id": foreign_company.id,
        "to_company_id": company.id,
        "mode": "READ",
    }


@pytest.mark.django_db
def test_jwt_auth_rejects_data_branch_bypass_inside_same_company():
    _, company, allowed_branch = _mk_org_tree("same-company")
    denied_branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        name="Other",
        code="OTHER",
        parent=company,
    )
    user = _mk_user(label="branch-bypass")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=allowed_branch, is_active=True)

    request = _drf_request(
        token=_mk_token(user),
        company_id=company.id,
        branch_id=allowed_branch.id,
        data_branch_id=denied_branch.id,
    )

    with pytest.raises(Exception) as exc_info:
        JWTAuthWithOrgContext().authenticate(request)

    assert "No se permite X-Data-Branch-Id distinto al contexto activo" in str(exc_info.value)


@pytest.mark.django_db
def test_context_endpoint_denies_branch_without_membership_and_returns_required_scope():
    _, company, allowed_branch = _mk_org_tree("ctx")
    denied_branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        name="Denied",
        code="DENIED",
        parent=company,
    )
    password = "Pass12345!"
    user = _mk_user(label="branch-membership", password=password)
    UserMembership.objects.create(user=user, org_unit=allowed_branch, is_active=True)

    client = _login_client(user=user, password=password, company=company, branch=denied_branch)
    response = client.get("/api/iam/context/")

    assert response.status_code == 403
    assert response.data["error"]["code"] == "SCOPE_FORBIDDEN"
    assert response.data["error"]["details"]["required_scope"] == {
        "company_id": company.id,
        "branch_id": denied_branch.id,
    }


@pytest.mark.django_db
def test_context_endpoint_requires_company_header():
    _, company, branch = _mk_org_tree("ctx-company-required")
    password = "Pass12345!"
    user = _mk_user(label="missing-company", password=password)
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    access = _login_access_token(user=user, password=password)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}", HTTP_X_BRANCH_ID=str(branch.id))
    response = client.get("/api/iam/context/")

    assert response.status_code == 400
    assert response.data["error"]["code"] == "BAD_REQUEST"
    assert "X-Company-Id requerido" in response.data["error"]["message"]


@pytest.mark.django_db
def test_context_endpoint_rejects_invalid_branch_header():
    _, company, branch = _mk_org_tree("ctx-invalid-branch")
    password = "Pass12345!"
    user = _mk_user(label="invalid-branch", password=password)
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    access = _login_access_token(user=user, password=password)
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {access}",
        HTTP_X_COMPANY_ID=str(company.id),
        HTTP_X_BRANCH_ID="abc",
    )
    response = client.get("/api/iam/context/")

    assert response.status_code == 400
    assert response.data["error"]["code"] == "BAD_REQUEST"
    assert "X-Branch-Id inválido" in response.data["error"]["message"]


@pytest.mark.django_db
def test_context_endpoint_denies_company_without_membership_and_returns_required_scope():
    _, target_company, target_branch = _mk_org_tree("target-company")
    _, other_company, other_branch = _mk_org_tree("other-company")
    password = "Pass12345!"
    user = _mk_user(label="no-company-membership", password=password)
    UserMembership.objects.create(user=user, org_unit=other_company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=other_branch, is_active=True)

    access = _login_access_token(user=user, password=password)
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {access}",
        HTTP_X_COMPANY_ID=str(target_company.id),
        HTTP_X_BRANCH_ID=str(target_branch.id),
    )
    response = client.get("/api/iam/context/")

    assert response.status_code == 403
    assert response.data["error"]["code"] == "SCOPE_FORBIDDEN"
    assert response.data["error"]["details"]["required_scope"] == {
        "company_id": target_company.id,
        "branch_id": None,
    }


@pytest.mark.django_db
def test_rbac_permission_requires_intercompany_read_grant():
    _, company, branch = _mk_org_tree("active")
    _, foreign_company, _ = _mk_org_tree("foreign-scope")
    user = _mk_user(label="rbac-intercompany")

    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    _grant_local_permission(user=user, company=company, branch=branch, permission_code="inventory.balance.read")

    permission = rbac_permission("inventory.balance.read")()
    raw_request = SimpleNamespace()
    request = SimpleNamespace(
        user=user,
        company=company,
        branch=branch,
        data_company=foreign_company,
        data_branch=None,
        _request=raw_request,
    )

    allowed_without_grant = permission.has_permission(request, view=None)
    assert allowed_without_grant is False
    assert request.required_scope == {"company_id": foreign_company.id, "branch_id": None}

    _grant_intercompany_read(
        from_company=foreign_company,
        to_company=company,
        permission_code="inventory.balance.read",
    )

    request_with_grant = SimpleNamespace(
        user=user,
        company=company,
        branch=branch,
        data_company=foreign_company,
        data_branch=None,
        _request=SimpleNamespace(),
    )
    allowed_with_grant = permission.has_permission(request_with_grant, view=None)
    assert allowed_with_grant is True
    assert request_with_grant.intercompany["grant_found"] is True
