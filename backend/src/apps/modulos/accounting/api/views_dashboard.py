from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission
from config.error_envelope import build_error_envelope

from ..reports import contracts
from ..reports.services import (
    dashboard_branch_performance,
    dashboard_cash_position,
    dashboard_executive_summary,
    dashboard_monthly_trends,
    dashboard_reconciliation_health,
    dashboard_revenue_vs_expense,
)
from .serializers_dashboard import DashboardRangeIn

DASHBOARD_CACHE_TTL_SECONDS = 90


def _is_validation_error(exc: Exception) -> bool:
    return exc.__class__.__name__ in {"Phase7ValidationError", "ValidationError"}


def _error_response(request, *, message: str, http_status: int, error_code: str = "REPORT_INVALID_PARAMS") -> Response:
    if contracts.is_legacy_route(request):
        return Response({"detail": message}, status=http_status)
    setattr(request, "error_code_override", error_code)
    raw = getattr(request, "_request", None)
    if raw is not None:
        setattr(raw, "error_code_override", error_code)
    return Response(
        build_error_envelope(
            request=request,
            status_code=http_status,
            details={"detail": message},
        ),
        status=http_status,
    )


def _cache_key(*, request, metric: str, validated: dict[str, Any]) -> str:
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    payload = {
        "metric": metric,
        "company_id": int(company.id) if company is not None else None,
        "branch_id": int(branch.id) if branch is not None else None,
        "filters": {k: str(v) for k, v in sorted(validated.items()) if k != "refresh"},
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"acc.dashboard:{metric}:{digest}"


def _build_payload(
    *,
    request,
    report_code: str,
    summary: dict[str, Any],
    results: Any,
    cache_hit: bool,
) -> dict[str, Any]:
    return contracts.build_envelope(
        request=request,
        report_code=report_code,
        summary=summary,
        results=results,
        pagination={},
        meta_extra={
            "cache_hit": bool(cache_hit),
            "cache_ttl_seconds": DASHBOARD_CACHE_TTL_SECONDS,
        },
    )


def _dashboard_response(
    *,
    request,
    report_code: str,
    validated: dict[str, Any],
    builder: Callable[[], tuple[dict[str, Any], Any]],
) -> Response:
    cache_key = _cache_key(request=request, metric=report_code, validated=validated)
    force_refresh = bool(validated.get("refresh"))
    cached_payload = None if force_refresh else cache.get(cache_key)
    if isinstance(cached_payload, dict):
        body = dict(cached_payload)
        body.setdefault("meta", {})
        body["meta"]["cache_hit"] = True
        return Response(body, status=status.HTTP_200_OK)

    summary, results = builder()
    body = _build_payload(
        request=request,
        report_code=report_code,
        summary=summary,
        results=results,
        cache_hit=False,
    )
    cache.set(cache_key, body, timeout=DASHBOARD_CACHE_TTL_SECONDS)
    return Response(body, status=status.HTTP_200_OK)


class ExecutiveSummaryDashboardView(APIView):
    permission_classes = [rbac_permission("accounting.dashboard.read")]

    def get(self, request):
        s = DashboardRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        validated = s.validated_data
        try:
            return _dashboard_response(
                request=request,
                report_code="DASHBOARD_EXECUTIVE_SUMMARY",
                validated=validated,
                builder=lambda: dashboard_executive_summary(
                    company=request.company,
                    branch=getattr(request, "branch", None),
                    validated=validated,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise


class RevenueVsExpenseDashboardView(APIView):
    permission_classes = [rbac_permission("accounting.dashboard.read")]

    def get(self, request):
        s = DashboardRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        validated = s.validated_data
        try:
            return _dashboard_response(
                request=request,
                report_code="DASHBOARD_REVENUE_VS_EXPENSE",
                validated=validated,
                builder=lambda: dashboard_revenue_vs_expense(
                    company=request.company,
                    branch=getattr(request, "branch", None),
                    validated=validated,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise


class CashPositionDashboardView(APIView):
    permission_classes = [rbac_permission("accounting.dashboard.read")]

    def get(self, request):
        s = DashboardRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        validated = s.validated_data
        try:
            return _dashboard_response(
                request=request,
                report_code="DASHBOARD_CASH_POSITION",
                validated=validated,
                builder=lambda: dashboard_cash_position(
                    company=request.company,
                    branch=getattr(request, "branch", None),
                    validated=validated,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise


class ReconciliationHealthDashboardView(APIView):
    permission_classes = [rbac_permission("accounting.dashboard.read")]

    def get(self, request):
        s = DashboardRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        validated = s.validated_data
        try:
            return _dashboard_response(
                request=request,
                report_code="DASHBOARD_RECONCILIATION_HEALTH",
                validated=validated,
                builder=lambda: dashboard_reconciliation_health(
                    company=request.company,
                    branch=getattr(request, "branch", None),
                    validated=validated,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise


class BranchPerformanceDashboardView(APIView):
    permission_classes = [rbac_permission("accounting.dashboard.read")]

    def get(self, request):
        s = DashboardRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        validated = s.validated_data
        try:
            return _dashboard_response(
                request=request,
                report_code="DASHBOARD_BRANCH_PERFORMANCE",
                validated=validated,
                builder=lambda: dashboard_branch_performance(
                    company=request.company,
                    branch=getattr(request, "branch", None),
                    validated=validated,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise


class MonthlyTrendsDashboardView(APIView):
    permission_classes = [rbac_permission("accounting.dashboard.read")]

    def get(self, request):
        s = DashboardRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        validated = s.validated_data
        try:
            return _dashboard_response(
                request=request,
                report_code="DASHBOARD_MONTHLY_TRENDS",
                validated=validated,
                builder=lambda: dashboard_monthly_trends(
                    company=request.company,
                    branch=getattr(request, "branch", None),
                    validated=validated,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise
