from __future__ import annotations

from typing import Any, Callable

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission
from config.error_envelope import build_error_envelope

from ..dashboard.cache_keys import build_dashboard_cache_key
from ..dashboard.services import (
    build_branch_performance,
    build_cash_position,
    build_executive_summary,
    build_monthly_trends,
    build_reconciliation_health,
    build_revenue_vs_expense,
)
from ..reports import contracts
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
    return build_dashboard_cache_key(
        metric=metric,
        company_id=int(company.id) if company is not None else None,
        branch_id=int(branch.id) if branch is not None else None,
        validated=validated,
    )


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
                builder=lambda: build_executive_summary(
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
                builder=lambda: build_revenue_vs_expense(
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
                builder=lambda: build_cash_position(
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
                builder=lambda: build_reconciliation_health(
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
                builder=lambda: build_branch_performance(
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
                builder=lambda: build_monthly_trends(
                    company=request.company,
                    branch=getattr(request, "branch", None),
                    validated=validated,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise
