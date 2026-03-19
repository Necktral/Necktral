from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.api_exceptions import ConflictError
from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.services import publish_outbox_event

from .models import CECException, CloseRun, EvidenceArtifact
from .serializers import (
    CECExceptionCreateIn,
    CECExceptionResolveIn,
    CloseRunAdvanceIn,
    CloseRunCreateIn,
    CloseRunExecuteIn,
    EvidenceCreateIn,
)
from .services import advance_close_run_state, execute_close_run


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "cec"}, status=status.HTTP_200_OK)


class CloseRunListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("cec.close_run.read")()]
        return [rbac_permission("cec.close_run.create")()]

    def get(self, request):
        company = request.company
        branch = getattr(request, "branch", None)
        qs = CloseRun.objects.filter(company=company).order_by("-started_at", "-id")
        if branch is not None:
            qs = qs.filter(branch=branch)
        run_type = request.query_params.get("run_type")
        st = request.query_params.get("status")
        if run_type:
            qs = qs.filter(run_type=run_type)
        if st:
            qs = qs.filter(status=st)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "run_id": str(r.run_id),
                "run_type": r.run_type,
                "status": r.status,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "window_start": r.window_start,
                "window_end": r.window_end,
                "consistency_score": r.consistency_score,
                "blocking_exceptions_count": r.blocking_exceptions_count,
            }
            for r in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        s = CloseRunCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        company = request.company
        branch = getattr(request, "branch", None)
        branch_id = v.get("branch_id")
        if branch_id is not None:
            branch = get_object_or_404(
                OrgUnit,
                id=branch_id,
                unit_type=OrgUnit.UnitType.BRANCH,
                parent=company,
                is_active=True,
            )

        run = CloseRun.objects.create(
            company=company,
            branch=branch,
            run_type=v.get("run_type") or CloseRun.RunType.DAILY,
            status=CloseRun.Status.CREATED,
            input_manifest_hash=v.get("input_manifest_hash", "") or "",
            created_by=request.user,
        )
        publish_outbox_event(
            request=request,
            source_module="CEC",
            event_type="CloseRunCreated",
            payload={"run_id": str(run.run_id), "run_type": run.run_type, "status": run.status},
            actor_user=request.user,
            company=company,
            branch=branch,
        )
        return Response({"run_id": str(run.run_id), "status": run.status}, status=status.HTTP_201_CREATED)


class CloseRunAdvanceView(APIView):
    permission_classes = [rbac_permission("cec.close_run.update")]

    def post(self, request, run_id):
        company = request.company
        run = get_object_or_404(CloseRun, run_id=run_id, company=company)
        s = CloseRunAdvanceIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        target_status = v["status"]
        output_manifest_hash = v.get("output_manifest_hash")
        summary_json = v.get("summary_json")
        if not run.can_transition_to(target_status):
            raise ConflictError(
                f"Transition not allowed: {run.status} -> {target_status}",
                code="CONFLICT",
            )
        advance_close_run_state(
            run=run,
            target_status=target_status,
            output_manifest_hash=output_manifest_hash,
            summary_json=summary_json,
        )

        publish_outbox_event(
            request=request,
            source_module="CEC",
            event_type="CloseRunAdvanced",
            payload={"run_id": str(run.run_id), "status": run.status},
            actor_user=request.user,
            company=run.company,
            branch=run.branch,
        )
        return Response({"ok": True, "run_id": str(run.run_id), "status": run.status}, status=status.HTTP_200_OK)


class CloseRunExecuteView(APIView):
    permission_classes = [rbac_permission("cec.close_run.update")]

    def post(self, request, run_id):
        company = request.company
        run = get_object_or_404(CloseRun, run_id=run_id, company=company)
        s = CloseRunExecuteIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        result = execute_close_run(
            run=run,
            request=request,
            actor=request.user,
            window_start=v["window_start"],
            window_end=v["window_end"],
            strict=bool(v.get("strict", True)),
        )
        return Response(
            {
                "run_id": result.run_id,
                "status": result.status,
                "consistency_score": result.consistency_score,
                "blocking_exceptions_count": result.blocking_exceptions_count,
                "exceptions_opened_count": result.exceptions_opened_count,
                "gates": result.gates,
                "output_manifest_hash": result.output_manifest_hash,
            },
            status=status.HTTP_200_OK,
        )


class CloseRunSummaryView(APIView):
    permission_classes = [rbac_permission("cec.close_run.read")]

    def get(self, request, run_id):
        company = request.company
        run = get_object_or_404(CloseRun, run_id=run_id, company=company)
        exceptions = list(
            run.exceptions.order_by("-opened_at", "-id").values(
                "exception_id",
                "code",
                "severity",
                "status",
                "is_blocking",
                "related_object_type",
                "related_object_id",
                "fingerprint",
                "opened_at",
                "resolved_at",
            )
        )
        artifacts = list(
            run.artifacts.order_by("-created_at", "-id").values(
                "artifact_id",
                "support_id",
                "sha256",
                "mime_type",
                "storage_ref",
                "created_at",
            )
        )

        return Response(
            {
                "run_id": str(run.run_id),
                "run_type": run.run_type,
                "status": run.status,
                "window_start": run.window_start,
                "window_end": run.window_end,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "consistency_score": run.consistency_score,
                "blocking_exceptions_count": run.blocking_exceptions_count,
                "output_manifest_hash": run.output_manifest_hash,
                "summary": run.summary_json or {},
                "exceptions": exceptions,
                "artifacts": artifacts,
            },
            status=status.HTTP_200_OK,
        )


class ExceptionListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("cec.exception.read")()]
        return [rbac_permission("cec.exception.create")()]

    def get(self, request):
        company = request.company
        branch = getattr(request, "branch", None)
        qs = CECException.objects.filter(company=company).order_by("-opened_at", "-id")
        if branch is not None:
            qs = qs.filter(branch=branch)
        st = request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "exception_id": str(r.exception_id),
                "source_module": r.source_module,
                "code": r.code,
                "severity": r.severity,
                "status": r.status,
                "opened_at": r.opened_at,
                "resolved_at": r.resolved_at,
            }
            for r in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        s = CECExceptionCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        company = request.company
        branch = getattr(request, "branch", None)
        run = None
        if v.get("close_run_id"):
            run = get_object_or_404(CloseRun, run_id=v["close_run_id"], company=company)

        ex = CECException.objects.create(
            source_module=v["source_module"],
            code=v["code"],
            severity=v.get("severity") or CECException.Severity.MEDIUM,
            company=company,
            branch=branch,
            related_object_type=v.get("related_object_type", "") or "",
            related_object_id=v.get("related_object_id", "") or "",
            details_json=v.get("details_json", {}) or {},
            close_run=run,
        )
        publish_outbox_event(
            request=request,
            source_module="CEC",
            event_type="ExceptionRaised",
            payload={"exception_id": str(ex.exception_id), "code": ex.code, "severity": ex.severity},
            actor_user=request.user,
            company=ex.company,
            branch=ex.branch,
        )
        return Response({"exception_id": str(ex.exception_id), "status": ex.status}, status=status.HTTP_201_CREATED)


class ExceptionResolveView(APIView):
    permission_classes = [rbac_permission("cec.exception.resolve")]

    def post(self, request, exception_id):
        company = request.company
        ex = get_object_or_404(CECException, exception_id=exception_id, company=company)
        s = CECExceptionResolveIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        ex.status = CECException.Status.RESOLVED
        ex.resolved_at = timezone.now()
        ex.resolution_note = v.get("resolution_note", "") or ""
        ex.save(update_fields=["status", "resolved_at", "resolution_note"])

        publish_outbox_event(
            request=request,
            source_module="CEC",
            event_type="ExceptionResolved",
            payload={"exception_id": str(ex.exception_id), "status": ex.status},
            actor_user=request.user,
            company=ex.company,
            branch=ex.branch,
        )
        return Response({"ok": True, "exception_id": str(ex.exception_id), "status": ex.status}, status=status.HTTP_200_OK)


class EvidenceCreateView(APIView):
    permission_classes = [rbac_permission("cec.evidence.create")]

    def post(self, request):
        s = EvidenceCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        company = request.company
        run = None
        if v.get("close_run_id"):
            run = get_object_or_404(CloseRun, run_id=v["close_run_id"], company=company)
        art = EvidenceArtifact.objects.create(
            support_id=v["support_id"],
            sha256=v["sha256"],
            mime_type=v["mime_type"],
            storage_ref=v["storage_ref"],
            metadata_json=v.get("metadata_json", {}) or {},
            close_run=run,
        )
        publish_outbox_event(
            request=request,
            source_module="CEC",
            event_type="EvidenceRegistered",
            payload={"artifact_id": str(art.artifact_id), "support_id": art.support_id, "close_run_id": str(run.run_id) if run else ""},
            actor_user=request.user,
            company=company,
            branch=getattr(request, "branch", None),
        )
        return Response({"artifact_id": str(art.artifact_id), "support_id": art.support_id}, status=status.HTTP_201_CREATED)
