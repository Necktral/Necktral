from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset
from apps.modulos.common.permissions import rbac_permission
from config.error_envelope import build_error_envelope

from ..reports import contracts
from ..reports.services import (
    build_balance_sheet,
    build_general_ledger,
    build_operational_reconciliation,
    build_pnl,
    build_trial_balance,
)
from .serializers_reports import GeneralLedgerRangeIn, OperationalReconciliationIn, ReportRangeIn


def _is_validation_error(exc: Exception) -> bool:
    return exc.__class__.__name__ in {"Phase7ValidationError", "ValidationError"}


def _error_response(
    request,
    *,
    message: str,
    http_status: int,
    error_code: str = "REPORT_INVALID_PARAMS",
    details: dict[str, Any] | None = None,
) -> Response:
    if contracts.is_legacy_route(request):
        payload: dict[str, Any] = {"detail": message}
        if details:
            payload["details"] = details
        return Response(payload, status=http_status)

    setattr(request, "error_code_override", error_code)
    raw = getattr(request, "_request", None)
    if raw is not None:
        setattr(raw, "error_code_override", error_code)
    detail_payload: dict[str, Any] = {"detail": message}
    if details:
        detail_payload.update(details)
    return Response(
        build_error_envelope(
            request=request,
            status_code=http_status,
            details=detail_payload,
        ),
        status=http_status,
    )


def _success_response(request, *, report_code: str, payload) -> Response:
    if contracts.is_legacy_route(request):
        return Response(payload.legacy_payload, status=status.HTTP_200_OK)

    body = contracts.build_envelope(
        request=request,
        report_code=report_code,
        summary=payload.summary,
        results=payload.results,
        pagination=payload.pagination,
        meta_extra=payload.meta_extra,
    )
    return Response(body, status=status.HTTP_200_OK)


class TrialBalanceReportView(APIView):
    permission_classes = [rbac_permission("accounting.report.read")]

    def get(self, request):
        s = ReportRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        try:
            limit, offset = get_limit_offset(request)
            payload = build_trial_balance(
                company=request.company,
                branch=getattr(request, "branch", None),
                validated=s.validated_data,
                limit=limit,
                offset=offset,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise
        return _success_response(request, report_code="TRIAL_BALANCE", payload=payload)


class GeneralLedgerReportView(APIView):
    permission_classes = [rbac_permission("accounting.report.read")]

    def get(self, request):
        s = GeneralLedgerRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        try:
            limit, offset = get_limit_offset(request)
            payload = build_general_ledger(
                company=request.company,
                branch=getattr(request, "branch", None),
                validated=s.validated_data,
                limit=limit,
                offset=offset,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise
        return _success_response(request, report_code="GENERAL_LEDGER", payload=payload)


class PnLReportView(APIView):
    permission_classes = [rbac_permission("accounting.report.read")]

    def get(self, request):
        s = ReportRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        try:
            payload = build_pnl(
                company=request.company,
                branch=getattr(request, "branch", None),
                validated=s.validated_data,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise
        return _success_response(request, report_code="PNL", payload=payload)


class BalanceSheetReportView(APIView):
    permission_classes = [rbac_permission("accounting.report.read")]

    def get(self, request):
        s = ReportRangeIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        try:
            payload = build_balance_sheet(
                company=request.company,
                branch=getattr(request, "branch", None),
                validated=s.validated_data,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise
        return _success_response(request, report_code="BALANCE_SHEET", payload=payload)


class OperationalReconciliationReportView(APIView):
    permission_classes = [rbac_permission("accounting.report.read")]

    def get(self, request):
        s = OperationalReconciliationIn(data=request.query_params)
        s.is_valid(raise_exception=True)
        try:
            payload = build_operational_reconciliation(
                company=request.company,
                branch=getattr(request, "branch", None),
                validated=s.validated_data,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_validation_error(exc):
                return _error_response(request, message=str(exc), http_status=status.HTTP_400_BAD_REQUEST)
            raise
        return _success_response(request, report_code="OPERATIONAL_RECONCILIATION", payload=payload)
