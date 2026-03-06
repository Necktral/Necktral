from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import rbac_permission
from apps.iam.models import OrgUnit

from .models import BillingDocument
from .serializers import (
    DocCreateSerializer,
    DocIssueSerializer,
    DocVoidSerializer,
    InvoiceCreateIn,
    InvoiceOut,
)
from .services import BillingError, create_draft, create_invoice, issue_doc, void_doc


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "billing"}, status=status.HTTP_200_OK)


class DocCreateView(APIView):
    permission_classes = [rbac_permission("billing.doc.create")]

    def post(self, request):
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
                "lines": lines,
            },
            status=status.HTTP_200_OK,
        )


class DocIssueView(APIView):
    permission_classes = [rbac_permission("billing.doc.issue")]

    def post(self, request, doc_id: int):
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
            )
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class DocVoidView(APIView):
    permission_classes = [rbac_permission("billing.doc.void")]

    def post(self, request, doc_id: int):
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
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class BillingHealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        # compat legacy
        resp = Response({"ok": True, "module": "billing"})
        resp["X-Deprecated"] = "true"
        resp["X-Deprecation-Notice"] = "Use /api/billing/health/ (legacy será retirado en v1.1)"
        return resp


class InvoiceCreateView(APIView):
    permission_classes = [rbac_permission("billing.invoice.create")]

    def post(self, request):
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
