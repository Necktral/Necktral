from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission

from .models import InboxEvent, OutboxEvent
from .serializers import InboxAckIn, OutboxMarkSentIn
from .services import mark_outbox_event_sent


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "integration"}, status=status.HTTP_200_OK)


class OutboxListView(APIView):
    permission_classes = [rbac_permission("integration.outbox.read")]

    def get(self, request):
        company = getattr(request, "company", None)
        branch = getattr(request, "branch", None)
        qs = OutboxEvent.objects.all().order_by("-occurred_at", "-id")
        if company is not None:
            qs = qs.filter(company=company)
        if branch is not None:
            qs = qs.filter(branch=branch)

        status_filter = request.query_params.get("status")
        module_filter = request.query_params.get("source_module")
        event_type_filter = request.query_params.get("event_type")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if module_filter:
            qs = qs.filter(source_module=module_filter)
        if event_type_filter:
            qs = qs.filter(event_type=event_type_filter)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)

        results = [
            {
                "event_id": str(r.event_id),
                "source_module": r.source_module,
                "event_type": r.event_type,
                "schema_version": r.schema_version,
                "status": r.status,
                "attempt_count": r.attempt_count,
                "occurred_at": r.occurred_at,
                "published_at": r.published_at,
                "next_attempt_at": r.next_attempt_at,
                "correlation_id": r.correlation_id,
                "causation_id": r.causation_id,
                "last_error": r.last_error,
            }
            for r in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class OutboxMarkSentView(APIView):
    permission_classes = [rbac_permission("integration.outbox.publish")]

    def post(self, request, event_id):
        company = getattr(request, "company", None)
        qs = OutboxEvent.objects.all()
        if company is not None:
            qs = qs.filter(company=company)
        ev = get_object_or_404(qs, event_id=event_id)

        s = OutboxMarkSentIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        mark_outbox_event_sent(event=ev, published_at=v.get("published_at") or timezone.now())

        return Response(
            {"ok": True, "event_id": str(ev.event_id), "status": ev.status},
            status=status.HTTP_200_OK,
        )


class InboxListView(APIView):
    permission_classes = [rbac_permission("integration.inbox.read")]

    def get(self, request):
        qs = InboxEvent.objects.all().order_by("-received_at", "-id")
        consumer = request.query_params.get("consumer")
        st = request.query_params.get("status")
        if consumer:
            qs = qs.filter(consumer=consumer)
        if st:
            qs = qs.filter(status=st)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "id": r.id,
                "event_id": str(r.event_id),
                "consumer": r.consumer,
                "source_module": r.source_module,
                "event_type": r.event_type,
                "status": r.status,
                "received_at": r.received_at,
                "processed_at": r.processed_at,
                "last_error": r.last_error,
            }
            for r in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class InboxAckView(APIView):
    permission_classes = [rbac_permission("integration.inbox.process")]

    def post(self, request, inbox_id: int):
        ev = get_object_or_404(InboxEvent, id=inbox_id)
        s = InboxAckIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        new_status = v.get("status") or InboxEvent.Status.PROCESSED
        ev.status = new_status
        ev.last_error = v.get("error", "") if new_status == InboxEvent.Status.FAILED else ""
        ev.processed_at = timezone.now() if new_status == InboxEvent.Status.PROCESSED else None
        ev.save(update_fields=["status", "last_error", "processed_at"])

        return Response({"ok": True, "id": ev.id, "status": ev.status}, status=status.HTTP_200_OK)
