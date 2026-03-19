from __future__ import annotations

import json
from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission

from .models import ReportDefinition, ReportExport, ReportReadAudit, ReportRun
from .serializers import ReportDefinitionCreateIn, ReportExportCreateIn, ReportRunCreateIn
from .services import (
    _assert_reproducibility_integrity,
    ReportDomainError,
    cancel_run,
    create_definition,
    create_export,
    list_visible_sources,
    masked_result_for_actor,
    register_read_access,
    reports_metrics_snapshot,
    retry_run,
    run_report,
)


def _error_response(request, *, code: str, message: str, http_status: int, details: dict | None = None) -> Response:
    setattr(request, "error_code_override", code)
    raw = getattr(request, "_request", None)
    if raw is not None:
        setattr(raw, "error_code_override", code)
    if code == "REPORT_FORBIDDEN":
        setattr(request, "audit_reason_code_override", "RBAC_FORBIDDEN")
        if raw is not None:
            setattr(raw, "audit_reason_code_override", "RBAC_FORBIDDEN")
    payload: dict[str, Any] = {"detail": message}
    if details:
        payload["details"] = details
    return Response(payload, status=http_status)


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "reports", "metrics": reports_metrics_snapshot()}, status=status.HTTP_200_OK)


class ReportDefinitionListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("reports.definition.read")()]
        return [rbac_permission("reports.definition.create")()]

    def get(self, request):
        company = request.company
        qs = ReportDefinition.objects.filter(company=company).order_by("code", "id")

        family = str(request.query_params.get("family") or "").strip().upper()
        truth_level = str(request.query_params.get("truth_level") or "").strip()
        source_type = str(request.query_params.get("source_type") or "").strip()
        sensitivity = str(request.query_params.get("sensitivity_level") or "").strip()
        status_code = str(request.query_params.get("status") or "").strip().upper()

        if family:
            qs = qs.filter(report_family=family)
        if truth_level:
            qs = qs.filter(truth_level=truth_level)
        if source_type:
            qs = qs.filter(source_types__contains=[source_type])
        if sensitivity:
            qs = qs.filter(sensitivity_level=sensitivity)
        if status_code:
            qs = qs.filter(status=status_code)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "report_id": str(r.report_id),
                "report_code": r.code,
                "report_family": r.report_family,
                "name": r.name,
                "description": r.description,
                "truth_level": r.truth_level,
                "source_types": r.source_types,
                "reproducibility_mode": r.reproducibility_mode,
                "sensitivity_level": r.sensitivity_level,
                "classification": r.classification,
                "schema_version": r.schema_version,
                "contract_version": r.contract_version,
                "version": r.version,
                "status": r.status,
                "is_active": bool(r.is_active),
            }
            for r in rows
        ]
        return Response({"count": total, "limit": limit, "offset": offset, "results": results}, status=status.HTTP_200_OK)

    def post(self, request):
        s = ReportDefinitionCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            row = create_definition(
                request=request,
                actor=request.user,
                company=request.company,
                code=v["code"],
                name=v["name"],
                description=v.get("description", "") or "",
                schema_version=v.get("schema_version") or 1,
                contract_version=v.get("contract_version") or 1,
                is_active=bool(v.get("is_active", True)),
            )
        except ReportDomainError as exc:
            return _error_response(
                request,
                code=exc.code,
                message=exc.message,
                http_status=int(exc.http_status),
                details=dict(exc.details or {}),
            )

        return Response(
            {
                "report_id": str(row.report_id),
                "report_code": row.code,
                "report_family": row.report_family,
                "truth_level": row.truth_level,
                "reproducibility_mode": row.reproducibility_mode,
                "version": row.version,
                "schema_version": row.schema_version,
                "contract_version": row.contract_version,
                "sensitivity_level": row.sensitivity_level,
            },
            status=status.HTTP_201_CREATED,
        )


class ReportRunListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("reports.run.read")()]
        return [rbac_permission("reports.run.create")()]

    def get(self, request):
        company = request.company
        branch = getattr(request, "branch", None)
        qs = ReportRun.objects.filter(company=company).select_related("definition").order_by("-started_at", "-id")
        if branch is not None:
            qs = qs.filter(branch_id=branch.id)
        if request.query_params.get("status"):
            qs = qs.filter(status=str(request.query_params.get("status")).strip().upper())
        if request.query_params.get("report_code"):
            qs = qs.filter(definition__code=str(request.query_params.get("report_code")).strip())
        if request.query_params.get("request_id"):
            qs = qs.filter(request_id=str(request.query_params.get("request_id")).strip())

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "execution_id": str(r.run_id),
                "report_code": r.definition.code,
                "report_version": r.report_version,
                "status": r.status,
                "truth_level": r.truth_level,
                "effective_scope": r.effective_scope,
                "freshness": r.freshness,
                "warnings": r.warnings,
                "duration_ms": r.duration_ms,
                "row_count": r.row_count,
                "request_id": r.request_id,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            }
            for r in rows
        ]
        return Response({"count": total, "limit": limit, "offset": offset, "results": results}, status=status.HTTP_200_OK)

    def post(self, request):
        s = ReportRunCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        params = v.get("params") or v.get("parameters") or {}
        try:
            run = run_report(
                request=request,
                actor=request.user,
                company=request.company,
                branch=getattr(request, "branch", None),
                code=v["code"],
                params=params,
                as_of=v.get("as_of"),
                time_window=v.get("time_window") or {},
                run_async=bool(v.get("run_async", False)),
                priority=int(v.get("priority") or 5),
                use_cache=bool(v.get("use_cache", True)),
            )
        except ReportDomainError as exc:
            return _error_response(
                request,
                code=exc.code,
                message=exc.message,
                http_status=int(exc.http_status),
                details=dict(exc.details or {}),
            )

        return Response(
            {
                "execution_id": str(run.run_id),
                "report_code": run.definition.code,
                "report_version": run.report_version,
                "status": run.status,
                "truth_level": run.truth_level,
                "effective_scope": run.effective_scope,
                "freshness": run.freshness,
                "source_manifest": run.source_manifest,
                "warnings": list(run.warnings or []) + (["DEDUPE_REUSED"] if getattr(run, "_dedupe_reused", False) else []),
                "row_count": run.row_count,
                "duration_ms": run.duration_ms,
            },
            status=status.HTTP_202_ACCEPTED if run.status == ReportRun.Status.QUEUED else status.HTTP_201_CREATED,
        )


class ReportRunDetailView(APIView):
    permission_classes = [rbac_permission("reports.run.read")]

    def get(self, request, run_id: str):
        company = request.company
        row = ReportRun.objects.filter(company=company, run_id=run_id).select_related("definition").first()
        if not row:
            return _error_response(request, code="REPORT_NOT_FOUND", message="execution not found", http_status=404)
        request_branch = getattr(request, "branch", None)
        if row.branch_id is not None and request_branch is not None and int(request_branch.id) != int(row.branch_id):
            return _error_response(
                request,
                code="REPORT_INVALID_SCOPE",
                message="branch scope mismatch",
                http_status=403,
                details={"required_scope": {"company_id": int(company.id), "branch_id": int(row.branch_id)}},
            )
        try:
            _assert_reproducibility_integrity(run=row)
        except ReportDomainError as exc:
            return _error_response(
                request,
                code=exc.code,
                message=exc.message,
                http_status=int(exc.http_status),
                details=dict(exc.details or {}),
            )
        try:
            register_read_access(request=request, actor=request.user, run=row, reason=str(request.query_params.get("reason") or ""))
        except ReportDomainError as exc:
            return _error_response(request, code=exc.code, message=exc.message, http_status=exc.http_status)

        result = masked_result_for_actor(request=request, actor=request.user, run=row)
        return Response(
            {
                "execution_id": str(row.run_id),
                "report_code": row.definition.code,
                "report_version": row.report_version,
                "status": row.status,
                "truth_level": row.truth_level,
                "effective_scope": row.effective_scope,
                "params_hash": row.params_hash,
                "as_of": row.as_of,
                "time_window": row.time_window,
                "source_manifest": row.source_manifest,
                "output_manifest_hash": row.output_manifest_hash,
                "freshness": row.freshness,
                "warnings": row.warnings,
                "row_count": row.row_count,
                "duration_ms": row.duration_ms,
                "result": result,
                "error": row.error,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
            },
            status=status.HTTP_200_OK,
        )


class ReportExportCreateView(APIView):
    permission_classes = [rbac_permission("reports.export")]

    def post(self, request):
        s = ReportExportCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            row = create_export(
                request=request,
                actor=request.user,
                company=request.company,
                execution_id=v["execution_id"],
                fmt=v.get("format") or "json",
                template_version=v.get("template_version") or "v1",
                reason=v.get("reason", "") or "",
                require_dual_approval=bool(v.get("require_dual_approval", False)),
                approved_by_user_id=v.get("approved_by_user_id"),
            )
        except ReportDomainError as exc:
            return _error_response(
                request,
                code=exc.code,
                message=exc.message,
                http_status=int(exc.http_status),
                details=dict(exc.details or {}),
            )

        return Response(
            {
                "export_id": str(row.export_id),
                "execution_id": str(row.execution.run_id),
                "status": row.status,
                "format": row.format,
                "retention_until": row.retention_until,
            },
            status=status.HTTP_201_CREATED,
        )


class ReportExportDetailView(APIView):
    permission_classes = [rbac_permission("reports.export")]

    def get(self, request, export_id: str):
        row = ReportExport.objects.filter(company=request.company, export_id=export_id).select_related("execution").first()
        if not row:
            return _error_response(request, code="REPORT_NOT_FOUND", message="export not found", http_status=404)
        request_branch = getattr(request, "branch", None)
        if row.execution.branch_id is not None and request_branch is not None and int(request_branch.id) != int(row.execution.branch_id):
            return _error_response(
                request,
                code="REPORT_INVALID_SCOPE",
                message="branch scope mismatch",
                http_status=403,
                details={"required_scope": {"company_id": int(request.company.id), "branch_id": int(row.execution.branch_id)}},
            )
        payload = {
            "export_id": str(row.export_id),
            "execution_id": str(row.execution.run_id),
            "status": row.status,
            "format": row.format,
            "template_version": row.template_version,
            "watermark_text": row.watermark_text,
            "storage_ref": row.storage_ref,
            "retention_until": row.retention_until,
            "requested_at": row.requested_at,
            "exported_at": row.exported_at,
        }
        if row.status == ReportExport.ExportStatus.READY:
            payload["content"] = row.content
        if row.error:
            payload["error"] = row.error
        return Response(payload, status=status.HTTP_200_OK)


class ReportReadAuditListView(APIView):
    permission_classes = [rbac_permission("reports.audit.read")]

    def get(self, request):
        qs = ReportReadAudit.objects.filter(company=request.company).select_related("execution", "actor_user").order_by("-occurred_at", "-id")
        if request.query_params.get("action"):
            qs = qs.filter(action=str(request.query_params.get("action")).strip().upper())
        if request.query_params.get("report_code"):
            qs = qs.filter(report_code=str(request.query_params.get("report_code")).strip())
        if request.query_params.get("request_id"):
            qs = qs.filter(request_id=str(request.query_params.get("request_id")).strip())
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "read_audit_id": str(r.read_audit_id),
                "action": r.action,
                "report_code": r.report_code,
                "execution_id": str(r.execution.run_id) if r.execution_id else "",
                "actor_user_id": r.actor_user_id,
                "scope": r.scope,
                "sensitivity_level": r.sensitivity_level,
                "reason": r.reason,
                "request_id": r.request_id,
                "occurred_at": r.occurred_at,
            }
            for r in rows
        ]
        return Response({"count": total, "limit": limit, "offset": offset, "results": results}, status=status.HTTP_200_OK)


class ReportSourceListView(APIView):
    permission_classes = [rbac_permission("reports.definition.read")]

    def get(self, request):
        qs = list_visible_sources(company=request.company)
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "source_code": s.source_code,
                "source_type": s.source_type,
                "producer_module": s.producer_module,
                "contract_version": s.contract_version,
                "truth_level": s.truth_level,
                "supports_scope": bool(s.supports_scope),
                "supports_request_id": bool(s.supports_request_id),
                "supports_correlation": bool(s.supports_correlation),
                "supports_replay": bool(s.supports_replay),
                "retention_policy": s.retention_policy,
                "pii_policy": s.pii_policy,
                "status": s.status,
            }
            for s in rows
        ]
        return Response({"count": total, "limit": limit, "offset": offset, "results": results}, status=status.HTTP_200_OK)


class ReportRunExportCompatView(APIView):
    permission_classes = [rbac_permission("reports.export")]

    def get(self, request, run_id: str):
        run = ReportRun.objects.filter(company=request.company, run_id=run_id).first()
        if run is None:
            return _error_response(request, code="REPORT_NOT_FOUND", message="execution not found", http_status=404)
        request_branch = getattr(request, "branch", None)
        if run.branch_id is not None and request_branch is not None and int(request_branch.id) != int(run.branch_id):
            return _error_response(
                request,
                code="REPORT_INVALID_SCOPE",
                message="branch scope mismatch",
                http_status=403,
                details={"required_scope": {"company_id": int(request.company.id), "branch_id": int(run.branch_id)}},
            )
        if run.status != ReportRun.Status.SUCCEEDED:
            return _error_response(request, code="REPORT_INVALID_PARAMS", message="execution not succeeded", http_status=422)
        result = masked_result_for_actor(request=request, actor=request.user, run=run)
        fmt = str(request.query_params.get("format") or "json").strip().lower()
        if fmt == "ndjson":
            rows = list((result or {}).get("rows") or [])
            raw = "\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) for r in rows)
            return Response(raw, status=status.HTTP_200_OK, content_type="application/x-ndjson")
        if fmt != "json":
            return _error_response(request, code="REPORT_EXPORT_FORBIDDEN", message="unsupported format", http_status=403)
        return Response(result, status=status.HTTP_200_OK)


class ReportRunCancelView(APIView):
    permission_classes = [rbac_permission("reports.run.create")]

    def post(self, request, run_id: str):
        try:
            run = cancel_run(request=request, actor=request.user, company=request.company, run_id=run_id)
        except ReportDomainError as exc:
            return _error_response(
                request,
                code=exc.code,
                message=exc.message,
                http_status=int(exc.http_status),
                details=dict(exc.details or {}),
            )
        return Response(
            {
                "execution_id": str(run.run_id),
                "status": run.status,
                "error_code": run.error_code,
            },
            status=status.HTTP_200_OK,
        )


class ReportRunRetryView(APIView):
    permission_classes = [rbac_permission("reports.run.create")]

    def post(self, request, run_id: str):
        priority_raw = request.data.get("priority")
        use_cache = bool(request.data.get("use_cache", True))
        try:
            run = retry_run(
                request=request,
                actor=request.user,
                company=request.company,
                run_id=run_id,
                priority=(int(priority_raw) if priority_raw is not None else None),
                use_cache=use_cache,
            )
        except ReportDomainError as exc:
            return _error_response(
                request,
                code=exc.code,
                message=exc.message,
                http_status=int(exc.http_status),
                details=dict(exc.details or {}),
            )
        return Response(
            {
                "execution_id": str(run.run_id),
                "status": run.status,
                "warnings": list(run.warnings or []) + (["DEDUPE_REUSED"] if getattr(run, "_dedupe_reused", False) else []),
            },
            status=status.HTTP_202_ACCEPTED if run.status == ReportRun.Status.QUEUED else status.HTTP_201_CREATED,
        )
