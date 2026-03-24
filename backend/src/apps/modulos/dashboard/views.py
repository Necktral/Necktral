from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission
from config.error_envelope import build_error_envelope

from .contracts import build_envelope
from .serializers import DashboardDrilldownIn, WorkspaceQueryIn
from .services import (
    ReportDomainError,
    drilldown_dashboard,
    get_dashboard_workspace,
    list_dashboard_catalog,
    query_dashboard_workspace,
)


def _error_response(request, *, message: str, http_status: int, code: str, details: dict[str, Any] | None = None) -> Response:
    setattr(request, "error_code_override", code)
    raw = getattr(request, "_request", None)
    if raw is not None:
        setattr(raw, "error_code_override", code)
    payload: dict[str, Any] = {"detail": message}
    if details:
        payload.update(details)
    return Response(
        build_error_envelope(
            request=request,
            status_code=http_status,
            details=payload,
        ),
        status=http_status,
    )


class DashboardCatalogView(APIView):
    permission_classes = [rbac_permission("dashboard.workspace.read")]

    def get(self, request):
        try:
            rows = list_dashboard_catalog(request=request, actor=request.user)
        except ReportDomainError as exc:
            return _error_response(
                request,
                message=exc.message,
                http_status=int(exc.http_status),
                code=exc.code,
                details=dict(exc.details or {}),
            )

        body = build_envelope(
            request=request,
            report_code="DASHBOARD_V3_CATALOG",
            summary={"workspace_count": len(rows)},
            results=rows,
            pagination={"count": len(rows)},
            meta_extra={"cache_hit": False, "cache_ttl_seconds": 0},
        )
        return Response(body, status=status.HTTP_200_OK)


class DashboardWorkspaceDetailView(APIView):
    permission_classes = [rbac_permission("dashboard.workspace.read")]

    def get(self, request, workspace_code: str):
        try:
            payload = get_dashboard_workspace(request=request, actor=request.user, workspace_code=workspace_code)
        except ReportDomainError as exc:
            return _error_response(
                request,
                message=exc.message,
                http_status=int(exc.http_status),
                code=exc.code,
                details=dict(exc.details or {}),
            )
        widgets_raw = payload.get("widgets")
        widget_rows = widgets_raw if isinstance(widgets_raw, list) else []

        body = build_envelope(
            request=request,
            report_code="DASHBOARD_V3_WORKSPACE",
            summary={
                "workspace_code": workspace_code,
                "title": payload.get("title"),
                "widget_count": len(widget_rows),
            },
            results=payload,
            pagination={},
            meta_extra={"workspace_code": workspace_code, "cache_hit": False, "cache_ttl_seconds": 0},
        )
        return Response(body, status=status.HTTP_200_OK)


class DashboardWorkspaceQueryView(APIView):
    permission_classes = [rbac_permission("dashboard.widget.read")]

    def post(self, request, workspace_code: str):
        s = WorkspaceQueryIn(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            payload = query_dashboard_workspace(
                request=request,
                actor=request.user,
                workspace_code=workspace_code,
                validated=s.validated_data,
            )
        except ReportDomainError as exc:
            return _error_response(
                request,
                message=exc.message,
                http_status=int(exc.http_status),
                code=exc.code,
                details=dict(exc.details or {}),
            )

        body = build_envelope(
            request=request,
            report_code="DASHBOARD_V3_QUERY",
            summary=dict(payload.get("summary") or {}),
            results=dict(payload.get("results") or {}),
            pagination={},
            warnings=list(payload.get("warnings") or []),
            meta_extra={
                "workspace_code": workspace_code,
                "cache_hit": bool(payload.get("cache_hit", False)),
                "cache_ttl_seconds": int(payload.get("cache_ttl_seconds") or 0),
            },
        )
        return Response(body, status=status.HTTP_200_OK)


class DashboardDrilldownView(APIView):
    permission_classes = [rbac_permission("dashboard.drilldown.read")]

    def post(self, request):
        s = DashboardDrilldownIn(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            payload = drilldown_dashboard(
                request=request,
                actor=request.user,
                validated=s.validated_data,
            )
        except ReportDomainError as exc:
            return _error_response(
                request,
                message=exc.message,
                http_status=int(exc.http_status),
                code=exc.code,
                details=dict(exc.details or {}),
            )

        body = build_envelope(
            request=request,
            report_code="DASHBOARD_V3_DRILLDOWN",
            summary=dict(payload.get("summary") or {}),
            results=dict(payload.get("results") or {}),
            pagination={},
            warnings=list(payload.get("warnings") or []),
            meta_extra={
                "workspace_code": str(s.validated_data.get("workspace_code") or ""),
                "widget_code": str(s.validated_data.get("widget_code") or ""),
                "cache_hit": False,
                "cache_ttl_seconds": 0,
            },
        )
        return Response(body, status=status.HTTP_200_OK)
