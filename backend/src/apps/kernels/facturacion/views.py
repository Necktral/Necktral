from __future__ import annotations

from typing import Any

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit

from .models import BillingDocument
from .serializers import (
    BranchFiscalConfigOut,
    BranchFiscalConfigUpdateIn,
    DocContingencyResolveSerializer,
    DocContingencySerializer,
    DocCreateSerializer,
    DocIssueSerializer,
    DocListQuerySerializer,
    DocPrintSerializer,
    DocVoidSerializer,
    InvoiceCreateIn,
    InvoiceOut,
)
from .services import (
    BillingError,
    BillingNotFoundError,
    create_draft,
    create_invoice,
    get_or_update_branch_fiscal_config,
    issue_doc,
    mark_doc_contingency,
    queue_fiscal_print,
    resolve_doc_contingency,
    void_doc,
)


def _customer_party_payload(doc: BillingDocument) -> dict[str, Any]:
    customer_party = doc.customer_party
    return {
        "customer_party_id": doc.customer_party_id,
        "customer_party_display_name": customer_party.display_name if customer_party is not None else "",
    }


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "billing"}, status=status.HTTP_200_OK)


class BranchFiscalConfigView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("billing.fiscal.config.read")()]
        return [rbac_permission("billing.fiscal.config.update")()]

    def get(self, request):
        company = request.company
        branch = request.branch
        cfg = get_or_update_branch_fiscal_config(company=company, branch=branch)
        return Response(BranchFiscalConfigOut(cfg).data, status=status.HTTP_200_OK)

    def put(self, request):
        company = request.company
        branch = request.branch
        s = BranchFiscalConfigUpdateIn(data=request.data)
        s.is_valid(raise_exception=True)
        cfg = get_or_update_branch_fiscal_config(
            company=company,
            branch=branch,
            actor=request.user,
            data=s.validated_data,
        )
        return Response(BranchFiscalConfigOut(cfg).data, status=status.HTTP_200_OK)


class DocListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("billing.doc.read")()]
        return [rbac_permission("billing.doc.create")()]

    def get(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        s = DocListQuerySerializer(data=request.query_params)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        v = s.validated_data

        company: OrgUnit = request.company
        branch: OrgUnit = request.branch
        qs = BillingDocument.objects.select_related("customer_party").filter(company=company, branch=branch)

        if v.get("status"):
            qs = qs.filter(status=v["status"])
        if v.get("doc_type"):
            qs = qs.filter(doc_type=v["doc_type"])

        q = str(v.get("q") or "").strip()
        if q:
            predicate = Q(customer_name__icontains=q) | Q(customer_ref__icontains=q) | Q(series__icontains=q)
            if q.isdigit():
                predicate |= Q(number=int(q))
            qs = qs.filter(predicate)

        if v.get("date_from"):
            qs = qs.filter(created_at__date__gte=v["date_from"])
        if v.get("date_to"):
            qs = qs.filter(created_at__date__lte=v["date_to"])

        ordering = str(v.get("ordering") or "-created_at")
        if ordering in {"id", "-id"}:
            qs = qs.order_by(ordering)
        else:
            qs = qs.order_by(ordering, "-id")

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "id": int(doc.id),
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "number": int(doc.number),
                "currency": doc.currency,
                "customer_name": doc.customer_name,
                "customer_ref": doc.customer_ref,
                **_customer_party_payload(doc),
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "payment_method": doc.payment_method,
                "is_fiscal": bool(doc.is_fiscal),
                "fiscal_status": doc.fiscal_status,
                "created_at": doc.created_at,
                "issued_at": doc.issued_at,
                "voided_at": doc.voided_at,
            }
            for doc in rows
        ]
        return Response({"count": total, "limit": limit, "offset": offset, "results": results}, status=status.HTTP_200_OK)

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = DocCreateSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        v = s.validated_data
        try:
            out = create_draft(
                request=request,
                actor=request.user,
                doc_type=v["doc_type"],
                series=v.get("series") or "A",
                currency=v.get("currency") or "NIO",
                customer_name=v.get("customer_name") or "",
                customer_ref=v.get("customer_ref") or "",
                customer_party_id=v.get("customer_party_id"),
                is_fiscal=bool(v.get("is_fiscal", False)),
                lines=v["lines"],
                idempotency_key=v.get("idempotency_key") or "",
                payment_method=v.get("payment_method") or "",
            )
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": out.doc_id}, status=status.HTTP_201_CREATED)


class DocDetailView(APIView):
    permission_classes = [rbac_permission("billing.doc.read")]

    def get(self, request, doc_id: int):
        company: OrgUnit = request.company
        branch: OrgUnit = request.branch

        doc = get_object_or_404(
            BillingDocument.objects.select_related("customer_party"),
            id=doc_id,
            company=company,
            branch=branch,
        )
        lines = []
        for ln in doc.lines.all().order_by("id"):
            lines.append(
                {
                    "id": ln.id,
                    "description": ln.description,
                    "quantity": str(ln.quantity),
                    "unit_price": str(ln.unit_price),
                    "tax_rate": str(ln.tax_rate),
                    "line_subtotal": str(ln.line_subtotal),
                    "line_tax": str(ln.line_tax),
                    "line_total": str(ln.line_total),
                    "inventory_item_id": ln.inventory_item_id,
                }
            )
        return Response(
            {
                "id": doc.id,
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "number": doc.number,
                "currency": doc.currency,
                "customer_name": doc.customer_name,
                "customer_ref": doc.customer_ref,
                **_customer_party_payload(doc),
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "payment_method": doc.payment_method,
                "is_fiscal": bool(doc.is_fiscal),
                "issued_at": doc.issued_at,
                "voided_at": doc.voided_at,
                "void_reason": doc.void_reason,
                "fiscal": {
                    "mode": doc.fiscal_mode_resolved,
                    "status": doc.fiscal_status,
                    "reference": doc.fiscal_reference,
                    "evidence_id": doc.fiscal_evidence_id,
                    "printed_at": doc.printed_at,
                    "attempts": doc.print_attempt_count,
                    "last_error": doc.last_print_error,
                    "contingency_reason": doc.contingency_reason,
                    "contingency_at": doc.contingency_at,
                    "metadata": doc.fiscal_metadata_json or {},
                },
                "accounting": {
                    "status": doc.accounting_status,
                    "error": doc.accounting_error,
                    "economic_event_id": doc.accounting_economic_event_id,
                    "journal_draft_id": doc.accounting_journal_draft_id,
                    "journal_entry_id": doc.accounting_journal_entry_id,
                },
                "lines": lines,
            },
            status=status.HTTP_200_OK,
        )


class DocIssueView(APIView):
    permission_classes = [rbac_permission("billing.doc.issue")]

    def post(self, request, doc_id: int):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = DocIssueSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        v = s.validated_data
        try:
            out = issue_doc(
                request=request,
                actor=request.user,
                doc_id=doc_id,
                apply_inventory=bool(v.get("apply_inventory", False)),
                print_after_issue=bool(v.get("print_after_issue", False)),
                idempotency_key=v.get("idempotency_key") or "",
            )
        except BillingNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class DocPrintView(APIView):
    permission_classes = [rbac_permission("billing.doc.print")]

    def post(self, request, doc_id: int):
        s = DocPrintSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            out = queue_fiscal_print(
                request=request,
                actor=request.user,
                doc_id=doc_id,
                idempotency_key=s.validated_data.get("idempotency_key") or "",
            )
        except BillingNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "doc_id": out.doc_id,
                "job_id": out.job_id,
                "status": out.status,
                "created": out.created,
                "fiscal_status": out.fiscal_status,
            },
            status=status.HTTP_200_OK,
        )


class DocContingencyView(APIView):
    permission_classes = [rbac_permission("billing.doc.contingency")]

    def post(self, request, doc_id: int):
        s = DocContingencySerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            out = mark_doc_contingency(
                request=request,
                actor=request.user,
                doc_id=doc_id,
                reason=s.validated_data["reason"],
            )
        except BillingNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class DocContingencyResolveView(APIView):
    permission_classes = [rbac_permission("billing.doc.contingency.resolve")]

    def post(self, request, doc_id: int):
        s = DocContingencyResolveSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            out = resolve_doc_contingency(
                request=request,
                actor=request.user,
                doc_id=doc_id,
                action=s.validated_data["action"],
                idempotency_key=s.validated_data.get("idempotency_key") or "",
                reason=s.validated_data.get("reason") or "",
            )
        except BillingNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class DocVoidView(APIView):
    permission_classes = [rbac_permission("billing.doc.void")]

    def post(self, request, doc_id: int):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = DocVoidSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        v = s.validated_data
        try:
            out = void_doc(
                request=request,
                actor=request.user,
                doc_id=doc_id,
                reason=v.get("reason") or "VOID",
            )
        except BillingNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class BillingHealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        resp = Response({"ok": True, "module": "billing"})
        resp["X-Deprecated"] = "true"
        resp["X-Deprecation-Notice"] = "Use /api/billing/health/ (legacy será retirado en v1.1)"
        return resp


class InvoiceCreateView(APIView):
    permission_classes = [rbac_permission("billing.invoice.create")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        ser = InvoiceCreateIn(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            inv = create_invoice(
                request=request,
                company=request.company,
                branch=request.branch,
                actor_user=request.user,
                customer_name=ser.validated_data["customer_name"],
                total_amount=ser.validated_data["total_amount"],
            )
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        resp = Response(InvoiceOut(inv).data, status=status.HTTP_201_CREATED)
        resp["X-Deprecated"] = "true"
        resp["X-Deprecation-Notice"] = "Use /api/billing/docs/ (legacy será retirado en v1.1)"
        return resp
