from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import rbac_permission
from apps.iam.models import OrgUnit

from .models import BillingDocument
from .serializers import (
    BranchFiscalConfigOut,
    BranchFiscalConfigUpdateIn,
    DocContingencyResolveSerializer,
    DocContingencySerializer,
    DocCreateSerializer,
    DocIssueSerializer,
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

LEGACY_SUNSET = "2026-06-30T00:00:00Z"
LEGACY_DEPRECATION_LINK = "</docs/BILLING_KERNEL_v1.0.md>; rel=\"deprecation\""


def _set_legacy_deprecation_headers(response: Response, *, notice: str) -> Response:
    response["Deprecation"] = "true"
    response["Sunset"] = LEGACY_SUNSET
    response["Link"] = LEGACY_DEPRECATION_LINK
    response["X-Deprecated"] = "true"
    response["X-Deprecation-Notice"] = notice
    return response


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


class DocCreateView(APIView):
    permission_classes = [rbac_permission("billing.doc.create")]

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
                is_fiscal=bool(v.get("is_fiscal", False)),
                lines=v["lines"],
                idempotency_key=v.get("idempotency_key") or "",
            )
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": out.doc_id}, status=status.HTTP_201_CREATED)


class DocDetailView(APIView):
    permission_classes = [rbac_permission("billing.doc.read")]

    def get(self, request, doc_id: int):
        company: OrgUnit = request.company
        branch: OrgUnit = request.branch

        doc = get_object_or_404(BillingDocument, id=doc_id, company=company, branch=branch)
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
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
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
        return _set_legacy_deprecation_headers(
            resp,
            notice="Use /api/billing/health/ (legacy sera retirado tras Sunset).",
        )


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
        return _set_legacy_deprecation_headers(
            resp,
            notice="Use /api/billing/docs/ (legacy sera retirado tras Sunset).",
        )
