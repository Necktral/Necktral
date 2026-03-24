from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote_plus

from django.conf import settings
from django.core.cache import cache
from django.core import signing
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit
from apps.modulos.rbac.selectors import get_effective_permissions_for_scope
from apps.modulos.reports.models import ReportDefinition
from apps.modulos.reports.services import ReportDomainError, create_definition, masked_result_for_actor, run_report

from .registry import WidgetSpec, WorkspaceSpec, catalog_payload, get_widget, get_workspace, workspace_payload

DASHBOARD_CACHE_TTL_SECONDS = 45
DASHBOARD_SLICE_CACHE_TTL_SECONDS = 120

KERNEL_PERMISSION_ALIASES: dict[str, tuple[str, ...]] = {
    "report.dashboard.read": ("report.dashboard.read", "dashboard.workspace.read"),
    "report.dataset.read": ("report.dataset.read", "dashboard.widget.read"),
}


def _get_request_id(request) -> str:
    return str(getattr(request, "request_id", "") or getattr(getattr(request, "ctx", None), "request_id", "") or "")


def _canon_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _scope_payload(*, company, branch, request) -> dict[str, Any]:
    data_scope = getattr(request, "data_scope", None) if request is not None else None
    payload = {
        "company_id": getattr(company, "id", None),
        "branch_id": getattr(branch, "id", None) if branch is not None else None,
    }
    if isinstance(data_scope, dict):
        payload["data_scope"] = dict(data_scope)
    return payload


def _effective_perms(*, user, company, branch) -> set[str]:
    return get_effective_permissions_for_scope(user, company=company, branch=branch, include_global=True)


def _require_permission(*, user, company, branch, permission_code: str) -> None:
    perms = _effective_perms(user=user, company=company, branch=branch)
    if permission_code not in perms and "*" not in perms:
        raise ReportDomainError(
            code="REPORT_FORBIDDEN",
            message="forbidden",
            http_status=403,
            details={"required_permission": permission_code},
        )


def _require_any_permission(*, user, company, branch, permission_codes: tuple[str, ...] | list[str]) -> str:
    perms = _effective_perms(user=user, company=company, branch=branch)
    if "*" in perms:
        return "*"
    normalized = tuple(str(code).strip() for code in permission_codes if str(code).strip())
    for code in normalized:
        if code in perms:
            return code
    raise ReportDomainError(
        code="REPORT_FORBIDDEN",
        message="forbidden",
        http_status=403,
        details={"required_permissions_any": list(normalized)},
    )


def _assert_dashboard_v3_enabled() -> None:
    if not bool(getattr(settings, "FF_DASHBOARD_V3_GLOBAL", False)):
        raise ReportDomainError(
            code="REPORT_FORBIDDEN",
            message="dashboard v3 disabled",
            http_status=403,
            details={"feature_flag": "FF_DASHBOARD_V3_GLOBAL"},
        )


def _cache_key(*, request, workspace_code: str, validated: dict[str, Any]) -> str:
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    payload = {
        "workspace_code": workspace_code,
        "company_id": int(company.id) if company is not None else None,
        "branch_id": int(branch.id) if branch is not None else None,
        "validated": validated,
    }
    digest = hashlib.sha256(_canon_json(payload).encode("utf-8")).hexdigest()
    return f"dashboard:v3:{workspace_code}:{digest[:24]}"


def _ensure_definition(*, request, actor, company, report_code: str) -> None:
    exists = ReportDefinition.objects.filter(company=company, code=report_code, is_active=True).exists()
    if exists:
        return
    create_definition(
        request=request,
        actor=None,
        company=company,
        code=report_code,
        name=report_code,
        description="Autoseeded dashboard v3 definition",
        schema_version=3,
        contract_version=3,
        is_active=True,
    )


def _resolve_workspace_or_404(workspace_code: str) -> WorkspaceSpec:
    workspace = get_workspace(workspace_code)
    if workspace is None:
        raise ReportDomainError(code="REPORT_NOT_FOUND", message="workspace not found", http_status=404)
    return workspace


def _resolve_widget_or_422(*, workspace: WorkspaceSpec, widget_code: str) -> WidgetSpec:
    code = str(widget_code or "").strip()
    widget = get_widget(code)
    if widget is None or code not in workspace.widget_codes:
        raise ReportDomainError(
            code="REPORT_INVALID_PARAMS",
            message="invalid widget_code",
            http_status=422,
            details={"workspace_code": workspace.code, "widget_code": code},
        )
    return widget


def _resolve_widgets(*, workspace: WorkspaceSpec, widget_code: str) -> list[WidgetSpec]:
    if str(widget_code or "").strip():
        return [_resolve_widget_or_422(workspace=workspace, widget_code=widget_code)]
    widgets: list[WidgetSpec] = []
    for code in workspace.widget_codes:
        widget = get_widget(code)
        if widget is not None:
            widgets.append(widget)
    return widgets


def _resolve_company_targets(*, request, actor, workspace: WorkspaceSpec, company_ids: list[int], branch_id: int | None):
    current_company = getattr(request, "company", None)
    current_branch = getattr(request, "branch", None)
    if current_company is None:
        raise ReportDomainError(code="REPORT_INVALID_SCOPE", message="missing company scope", http_status=403)

    requested_ids = [int(x) for x in (company_ids or []) if int(x) > 0]
    if not requested_ids:
        requested_ids = [int(current_company.id)]
    requested_ids = list(dict.fromkeys(requested_ids))

    intercompany_requested = any(int(cid) != int(current_company.id) for cid in requested_ids)
    if intercompany_requested:
        if not bool(getattr(settings, "FF_DASHBOARD_V3_INTERCOMPANY", False)):
            raise ReportDomainError(
                code="REPORT_FORBIDDEN",
                message="intercompany dashboard disabled",
                http_status=403,
                details={"feature_flag": "FF_DASHBOARD_V3_INTERCOMPANY"},
            )
        if not workspace.intercompany_enabled:
            raise ReportDomainError(
                code="REPORT_FORBIDDEN",
                message="workspace does not allow intercompany",
                http_status=403,
                details={"workspace_code": workspace.code},
            )
        _require_permission(
            user=actor,
            company=current_company,
            branch=current_branch,
            permission_code="dashboard.intercompany.read",
        )

    companies = {
        int(row.id): row
        for row in OrgUnit.objects.filter(
            unit_type=OrgUnit.UnitType.COMPANY,
            id__in=requested_ids,
        )
    }
    missing = [cid for cid in requested_ids if cid not in companies]
    if missing:
        raise ReportDomainError(
            code="REPORT_INVALID_PARAMS",
            message="unknown company_ids",
            http_status=422,
            details={"company_ids": missing},
        )

    targets: list[tuple[OrgUnit, OrgUnit | None]] = []
    for company_id in requested_ids:
        company = companies[company_id]
        target_branch = None
        if branch_id is not None and int(company_id) == int(getattr(current_company, "id", 0)):
            if current_branch is not None and int(current_branch.id) == int(branch_id):
                target_branch = current_branch
            else:
                target_branch = OrgUnit.objects.filter(
                    unit_type=OrgUnit.UnitType.BRANCH,
                    id=int(branch_id),
                    parent_id=int(company_id),
                ).first()
                if target_branch is None:
                    raise ReportDomainError(
                        code="REPORT_INVALID_PARAMS",
                        message="invalid branch for company",
                        http_status=422,
                        details={"branch_id": branch_id, "company_id": company_id},
                    )

        # Filtro adicional: el usuario debe tener permiso dashboard.widget.read en el company target.
        _require_any_permission(
            user=actor,
            company=company,
            branch=target_branch,
            permission_codes=KERNEL_PERMISSION_ALIASES["report.dataset.read"],
        )
        targets.append((company, target_branch))
    return targets, intercompany_requested


def _dashboard_request_for_target(*, request, company, branch, path: str):
    return SimpleNamespace(
        request_id=_get_request_id(request),
        META=dict(getattr(request, "META", {}) or {}),
        method="POST",
        path=path,
        company=company,
        branch=branch,
        data_scope=getattr(request, "data_scope", None),
    )


def _build_v3_params(*, workspace_code: str, widget_code: str, validated: dict[str, Any]) -> dict[str, Any]:
    return {
        "filters": dict(validated.get("filters") or {}),
        "group_by": list(validated.get("group_by") or []),
        "metrics": list(validated.get("metrics") or []),
        "sort": list(validated.get("sort") or []),
        "cursor": validated.get("cursor") or {},
        "comparison": dict(validated.get("comparison") or {}),
        "drill_path": list(validated.get("drill_path") or []),
        "workspace_code": workspace_code,
        "widget_code": widget_code,
    }


def _query_widget(
    *,
    request,
    actor,
    workspace_code: str,
    widget: WidgetSpec,
    company,
    branch,
    validated: dict[str, Any],
) -> dict[str, Any]:
    synthetic_request = _dashboard_request_for_target(
        request=request,
        company=company,
        branch=branch,
        path=f"/api/backend/dashboard/workspaces/{workspace_code}/query/",
    )
    _ensure_definition(request=synthetic_request, actor=actor, company=company, report_code=widget.report_code)

    run = run_report(
        request=synthetic_request,
        actor=actor,
        company=company,
        branch=branch,
        code=widget.report_code,
        params=_build_v3_params(workspace_code=workspace_code, widget_code=widget.widget_code, validated=validated),
        as_of=validated.get("as_of"),
        time_window=validated.get("time_window") or {},
        run_async=bool(validated.get("run_async", False)),
        priority=int(validated.get("priority") or 5),
        use_cache=bool(validated.get("use_cache", True)),
    )

    result_payload = {}
    if run.status != "QUEUED":
        result_payload = masked_result_for_actor(request=synthetic_request, actor=actor, run=run)

    rows = list(result_payload.get("rows") or [])
    for row in rows:
        if isinstance(row, dict):
            row.setdefault("company_id", int(company.id))
            if branch is not None:
                row.setdefault("branch_id", int(branch.id))

    return {
        "workspace_code": workspace_code,
        "widget_code": widget.widget_code,
        "widget_title": widget.title,
        "visual": widget.visual,
        "domain": widget.domain,
        "report_code": widget.report_code,
        "company_id": int(company.id),
        "branch_id": int(branch.id) if branch is not None else None,
        "execution_id": str(run.run_id),
        "status": run.status,
        "row_count": int(run.row_count or len(rows)),
        "duration_ms": int(run.duration_ms or 0),
        "warnings": list(run.warnings or []),
        "meta": dict(result_payload.get("meta") or {}),
        "rows": rows,
    }


def list_dashboard_catalog(*, request, actor) -> list[dict[str, object]]:
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    _require_any_permission(user=actor, company=company, branch=branch, permission_codes=KERNEL_PERMISSION_ALIASES["report.dashboard.read"])
    _assert_dashboard_v3_enabled()
    return catalog_payload()


def get_dashboard_workspace(*, request, actor, workspace_code: str) -> dict[str, object]:
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    _require_any_permission(user=actor, company=company, branch=branch, permission_codes=KERNEL_PERMISSION_ALIASES["report.dashboard.read"])
    _assert_dashboard_v3_enabled()
    workspace = _resolve_workspace_or_404(workspace_code)
    payload = workspace_payload(workspace.code)
    if payload is None:
        raise ReportDomainError(code="REPORT_NOT_FOUND", message="workspace not found", http_status=404)

    write_event(
        request=request,
        event_type="DASHBOARD_WORKSPACE_VIEWED",
        reason_code="REPORTS_OK",
        actor_user=actor,
        subject_type="DASHBOARD_WORKSPACE",
        subject_id=workspace.code,
        metadata={"workspace_code": workspace.code, "company_id": str(getattr(company, "id", ""))},
        module="DASHBOARD",
    )
    return payload


def query_dashboard_workspace(*, request, actor, workspace_code: str, validated: dict[str, Any]):
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    _require_any_permission(user=actor, company=company, branch=branch, permission_codes=KERNEL_PERMISSION_ALIASES["report.dashboard.read"])
    _require_any_permission(user=actor, company=company, branch=branch, permission_codes=KERNEL_PERMISSION_ALIASES["report.dataset.read"])
    _assert_dashboard_v3_enabled()

    workspace = _resolve_workspace_or_404(workspace_code)
    widgets = _resolve_widgets(workspace=workspace, widget_code=str(validated.get("widget_code") or ""))
    targets, intercompany_requested = _resolve_company_targets(
        request=request,
        actor=actor,
        workspace=workspace,
        company_ids=list(validated.get("company_ids") or []),
        branch_id=validated.get("branch_id"),
    )

    use_cache = bool(validated.get("use_cache", True)) and not bool(validated.get("run_async", False))
    cache_key = _cache_key(request=request, workspace_code=workspace.code, validated=validated)
    if use_cache:
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            body = dict(cached)
            body.setdefault("meta", {})
            body["meta"]["cache_hit"] = True
            return body

    widget_rows: list[dict[str, Any]] = []
    for widget in widgets:
        for target_company, target_branch in targets:
            widget_rows.append(
                _query_widget(
                    request=request,
                    actor=actor,
                    workspace_code=workspace.code,
                    widget=widget,
                    company=target_company,
                    branch=target_branch,
                    validated=validated,
                )
            )

    summary = {
        "workspace_code": workspace.code,
        "workspace_title": workspace.title,
        "widget_count": len(widgets),
        "execution_count": len(widget_rows),
        "intercompany_requested": bool(intercompany_requested),
        "company_count": len({int(row["company_id"]) for row in widget_rows}),
    }
    results = {
        "widgets": widget_rows,
        "query": {
            "filters": dict(validated.get("filters") or {}),
            "group_by": list(validated.get("group_by") or []),
            "metrics": list(validated.get("metrics") or []),
            "sort": list(validated.get("sort") or []),
            "comparison": dict(validated.get("comparison") or {}),
            "drill_path": list(validated.get("drill_path") or []),
        },
    }

    write_event(
        request=request,
        event_type="DASHBOARD_WIDGET_QUERIED",
        reason_code="REPORTS_OK",
        actor_user=actor,
        subject_type="DASHBOARD_WORKSPACE",
        subject_id=workspace.code,
        metadata={
            "workspace_code": workspace.code,
            "widget_codes": [w.widget_code for w in widgets],
            "execution_count": len(widget_rows),
            "intercompany": bool(intercompany_requested),
            "company_id": str(getattr(company, "id", "")),
        },
        module="DASHBOARD",
    )

    body = {
        "summary": summary,
        "results": results,
        "warnings": [],
        "cache_ttl_seconds": DASHBOARD_SLICE_CACHE_TTL_SECONDS,
        "cache_hit": False,
    }
    if use_cache:
        cache.set(cache_key, body, timeout=DASHBOARD_SLICE_CACHE_TTL_SECONDS)
    return body


def drilldown_dashboard(*, request, actor, validated: dict[str, Any]):
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    _require_any_permission(user=actor, company=company, branch=branch, permission_codes=KERNEL_PERMISSION_ALIASES["report.dashboard.read"])
    _require_any_permission(user=actor, company=company, branch=branch, permission_codes=KERNEL_PERMISSION_ALIASES["report.dataset.read"])
    _require_any_permission(
        user=actor,
        company=company,
        branch=branch,
        permission_codes=("dashboard.drilldown.read",),
    )
    _assert_dashboard_v3_enabled()

    workspace_code = str(validated.get("workspace_code") or "")
    workspace = _resolve_workspace_or_404(workspace_code)
    widget = _resolve_widget_or_422(workspace=workspace, widget_code=str(validated.get("widget_code") or ""))
    targets, intercompany_requested = _resolve_company_targets(
        request=request,
        actor=actor,
        workspace=workspace,
        company_ids=list(validated.get("company_ids") or []),
        branch_id=validated.get("branch_id"),
    )

    query_payload = {
        "widget_code": widget.widget_code,
        "filters": dict(validated.get("filters") or {}),
        "group_by": list(validated.get("group_by") or []),
        "metrics": list(validated.get("metrics") or []),
        "sort": list(validated.get("sort") or []),
        "cursor": validated.get("cursor") or {},
        "comparison": dict(validated.get("comparison") or {}),
        "drill_path": list(validated.get("drill_path") or []),
        "time_window": {},
        "as_of": None,
        "run_async": False,
        "priority": 5,
        "use_cache": False,
        "company_ids": [int(target.id) for target, _ in targets],
        "branch_id": validated.get("branch_id"),
    }

    rows: list[dict[str, Any]] = []
    for target_company, target_branch in targets:
        rows.append(
            _query_widget(
                request=request,
                actor=actor,
                workspace_code=workspace.code,
                widget=widget,
                company=target_company,
                branch=target_branch,
                validated=query_payload,
            )
        )

    summary = {
        "workspace_code": workspace.code,
        "widget_code": widget.widget_code,
        "drill_path": list(validated.get("drill_path") or []),
        "execution_count": len(rows),
        "intercompany_requested": bool(intercompany_requested),
    }
    results = {
        "drilldown": rows,
    }

    write_event(
        request=request,
        event_type="DASHBOARD_DRILLDOWN_EXECUTED",
        reason_code="REPORTS_OK",
        actor_user=actor,
        subject_type="DASHBOARD_WORKSPACE",
        subject_id=workspace.code,
        metadata={
            "workspace_code": workspace.code,
            "widget_code": widget.widget_code,
            "drill_path": list(validated.get("drill_path") or []),
            "company_id": str(getattr(company, "id", "")),
        },
        module="DASHBOARD",
    )

    return {
        "summary": summary,
        "results": results,
        "warnings": [],
    }


def create_dashboard_embed_token(*, request, actor, validated: dict[str, Any]) -> dict[str, Any]:
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    _require_any_permission(
        user=actor,
        company=company,
        branch=branch,
        permission_codes=KERNEL_PERMISSION_ALIASES["report.dashboard.read"],
    )
    _assert_dashboard_v3_enabled()

    workspace_code = str(validated.get("workspace_code") or "")
    workspace = _resolve_workspace_or_404(workspace_code)
    targets, intercompany_requested = _resolve_company_targets(
        request=request,
        actor=actor,
        workspace=workspace,
        company_ids=list(validated.get("company_ids") or []),
        branch_id=validated.get("branch_id"),
    )

    default_ttl = int(getattr(settings, "DASH_EMBED_TOKEN_TTL_SECONDS", 600) or 600)
    ttl_seconds = int(validated.get("ttl_seconds") or default_ttl)
    ttl_seconds = max(60, min(ttl_seconds, 3600))
    issued_at = timezone.now()
    expires_at = issued_at + timedelta(seconds=ttl_seconds)

    payload = {
        "iss": "necktral.dashboard",
        "sub": str(getattr(actor, "id", "")),
        "workspace_code": workspace.code,
        "scope": {
            "company_id": int(company.id) if company is not None else None,
            "branch_id": int(branch.id) if branch is not None else None,
        },
        "targets": [
            {
                "company_id": int(target_company.id),
                "branch_id": int(target_branch.id) if target_branch is not None else None,
            }
            for target_company, target_branch in targets
        ],
        "theme": str(validated.get("theme") or ""),
        "locale": str(validated.get("locale") or ""),
        "intercompany_requested": bool(intercompany_requested),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "request_id": _get_request_id(request),
    }

    signing_key = str(getattr(settings, "DASH_EMBED_SIGNING_KEY", "") or getattr(settings, "JWT_SIGNING_KEY", ""))
    token = signing.dumps(payload, key=signing_key, salt="dashboard.embed.v1", compress=True)
    base_url = str(getattr(settings, "DASH_EMBED_BASE_URL", "") or "").strip().rstrip("/")
    embed_url = f"{base_url}/?token={quote_plus(token)}" if base_url else ""

    write_event(
        request=request,
        event_type="DASHBOARD_EMBED_TOKEN_ISSUED",
        reason_code="REPORTS_OK",
        actor_user=actor,
        subject_type="DASHBOARD_WORKSPACE",
        subject_id=workspace.code,
        metadata={
            "workspace_code": workspace.code,
            "ttl_seconds": ttl_seconds,
            "intercompany_requested": bool(intercompany_requested),
            "company_id": str(getattr(company, "id", "")),
        },
        module="DASHBOARD",
    )

    return {
        "workspace_code": workspace.code,
        "token_type": "signed-json",
        "token": token,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": ttl_seconds,
        "embed_url": embed_url,
        "scope": payload["scope"],
        "targets": payload["targets"],
    }
