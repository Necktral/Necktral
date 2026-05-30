"""
Portfolio Kernel Views
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.modulos.iam.context import require_company_context

from .models import (
    Receivable,
    Payable,
    Credit,
    PaymentAllocation,
    InterestAccrual,
    PortfolioSettings,
)
from .serializers import (
    ReceivableSerializer,
    PayableSerializer,
    CreditSerializer,
    PaymentAllocationSerializer,
    InterestAccrualSerializer,
    PortfolioSettingsSerializer,
)
from . import services


class ReceivableViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Receivables (CxC)
    """
    serializer_class = ReceivableSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "party", "aging_bucket", "currency"]
    search_fields = ["invoice_number", "party__name"]
    ordering_fields = ["issue_date", "due_date", "outstanding_amount"]
    ordering = ["-issue_date"]

    @require_company_context
    def get_queryset(self, company=None, **ctx):
        return Receivable.objects.filter(company=company).select_related("party", "company", "branch")

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        """Adjust receivable amount"""
        receivable = self.get_object()
        adjustment_amount = request.data.get("adjustment_amount")
        reason = request.data.get("reason", "")

        try:
            adjusted = services.adjust_receivable(
                receivable=receivable,
                adjustment_amount=adjustment_amount,
                reason=reason,
                adjusted_by=request.user,
            )
            return Response(self.get_serializer(adjusted).data)
        except services.PortfolioDomainError as e:
            return Response(
                {"error": e.code, "message": e.message, "details": e.details},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["post"])
    def writeoff(self, request, pk=None):
        """Write off receivable"""
        receivable = self.get_object()
        reason = request.data.get("reason", "")

        try:
            written_off = services.write_off_receivable(
                receivable=receivable,
                reason=reason,
                approved_by=request.user,
            )
            return Response(self.get_serializer(written_off).data)
        except services.PortfolioDomainError as e:
            return Response(
                {"error": e.code, "message": e.message},
                status=status.HTTP_400_BAD_REQUEST
            )


class PayableViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Payables (CxP)
    """
    serializer_class = PayableSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "party", "payment_priority", "currency"]
    search_fields = ["supplier_invoice_number", "party__name"]
    ordering_fields = ["issue_date", "due_date", "outstanding_amount"]
    ordering = ["-issue_date"]

    @require_company_context
    def get_queryset(self, company=None, **ctx):
        return Payable.objects.filter(company=company).select_related("party", "company", "branch")


class CreditViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Credits
    """
    serializer_class = CreditSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["credit_status", "credit_type", "borrower_party", "lender_party"]
    search_fields = ["contract_number", "borrower_party__name", "lender_party__name"]
    ordering_fields = ["approval_date", "disbursement_date", "maturity_date"]
    ordering = ["-created_at"]

    @require_company_context
    def get_queryset(self, company=None, **ctx):
        return Credit.objects.filter(company=company).select_related(
            "lender_party", "borrower_party", "guarantor_party", "company", "branch"
        )

    @action(detail=True, methods=["post"])
    def disburse(self, request, pk=None):
        """Disburse credit"""
        credit = self.get_object()
        disbursed_amount = request.data.get("disbursed_amount")
        disbursement_date = request.data.get("disbursement_date")

        try:
            disbursed = services.disburse_credit(
                credit=credit,
                disbursed_amount=disbursed_amount,
                disbursement_date=disbursement_date,
                disbursed_by=request.user,
            )
            return Response(self.get_serializer(disbursed).data)
        except services.PortfolioDomainError as e:
            return Response(
                {"error": e.code, "message": e.message},
                status=status.HTTP_400_BAD_REQUEST
            )


class PaymentAllocationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Payment Allocations
    """
    serializer_class = PaymentAllocationSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "payment_intent", "allocation_date"]
    ordering = ["-allocation_date", "-created_at"]

    @require_company_context
    def get_queryset(self, company=None, **ctx):
        return PaymentAllocation.objects.filter(company=company).select_related("payment_intent", "company")


class InterestAccrualViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Interest Accruals (read-only)
    """
    serializer_class = InterestAccrualSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["credit", "accrual_date", "is_capitalized"]
    ordering = ["-accrual_date"]

    def get_queryset(self):
        # Filter by credit's company
        return InterestAccrual.objects.filter(
            credit__company=self.request.user.active_company
        ).select_related("credit")


class PortfolioSettingsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Portfolio Settings (per company)
    """
    serializer_class = PortfolioSettingsSerializer
    permission_classes = [IsAuthenticated]

    @require_company_context
    def get_queryset(self, company=None, **ctx):
        return PortfolioSettings.objects.filter(company=company)
