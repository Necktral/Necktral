from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit
from apps.modulos.payments.models import CashSession, CashMovement, PaymentIntent

from kernels.facturacion.models import BillingDocument
from kernels.inventarios.models import InventoryItem, Warehouse


class RetailBranchConfig(models.Model):
    branch = models.OneToOneField(OrgUnit, on_delete=models.CASCADE, related_name="retail_branch_config")
    series = models.CharField(max_length=16, default="RTL")
    default_warehouse = models.ForeignKey(
        Warehouse,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_branch_configs",
    )
    price_includes_tax = models.BooleanField(default=False)
    hold_expiry_minutes = models.PositiveIntegerField(default=120)
    print_after_issue = models.BooleanField(default=False)
    require_customer_for_fiscal = models.BooleanField(default=False)
    allow_manual_reprice = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ventas_retail"


class RetailTerminal(models.Model):
    branch = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="retail_terminals")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    device_ref = models.CharField(max_length=96, blank=True, default="")
    receipt_printer_ref = models.CharField(max_length=96, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ventas_retail"
        constraints = [
            models.UniqueConstraint(fields=["branch", "code"], name="uq_retail_terminal_branch_code"),
        ]
        indexes = [
            models.Index(fields=["branch", "is_active", "code"]),
        ]


class RetailTicket(models.Model):
    class TicketKind(models.TextChoices):
        SALE = "SALE", "Sale"
        RETURN = "RETURN", "Return"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        OPEN = "OPEN", "Open"
        PAID = "PAID", "Paid"
        CLOSED = "CLOSED", "Closed"
        VOIDED = "VOIDED", "Voided"

    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        INTENDED = "INTENDED", "Intended"
        CAPTURED = "CAPTURED", "Captured"
        PARTIAL = "PARTIAL", "Partial"
        REFUNDED = "REFUNDED", "Refunded"
        FAILED = "FAILED", "Failed"

    class FulfillmentStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        STOCK_APPLIED = "STOCK_APPLIED", "Stock applied"
        REVERSED = "REVERSED", "Reversed"

    class CompensationStatus(models.TextChoices):
        NONE = "NONE", "None"
        COMPENSATING = "COMPENSATING", "Compensating"
        FAILED = "FAILED", "Failed"

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="retail_tickets_company")
    branch = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="retail_tickets_branch")
    terminal = models.ForeignKey(
        RetailTerminal,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tickets",
    )
    cash_session = models.ForeignKey(
        CashSession,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_tickets",
    )
    ticket_kind = models.CharField(max_length=16, choices=TicketKind.choices, default=TicketKind.SALE)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    payment_status = models.CharField(max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    fulfillment_status = models.CharField(
        max_length=24,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.PENDING,
    )
    compensation_status = models.CharField(
        max_length=24,
        choices=CompensationStatus.choices,
        default=CompensationStatus.NONE,
    )
    version = models.PositiveIntegerField(default=1)
    flow_correlation_id = models.CharField(max_length=96, blank=True, default="", db_index=True)
    checkout_lock_token = models.CharField(max_length=96, blank=True, default="")
    customer_name = models.CharField(max_length=200, blank=True, default="")
    customer_ref = models.CharField(max_length=96, blank=True, default="")
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    discount_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    billing_doc = models.ForeignKey(
        BillingDocument,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_tickets",
    )
    payment_intent = models.ForeignKey(
        PaymentIntent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_tickets",
    )
    last_error = models.CharField(max_length=255, blank=True, default="")
    compensation_attempts = models.PositiveIntegerField(default=0)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retail_tickets_created",
    )

    class Meta:
        app_label = "ventas_retail"
        indexes = [
            models.Index(fields=["company", "branch", "status", "created_at"]),
            models.Index(fields=["branch", "ticket_kind", "status", "created_at"]),
        ]


class RetailTicketLine(models.Model):
    ticket = models.ForeignKey(RetailTicket, on_delete=models.CASCADE, related_name="lines")
    inventory_item = models.ForeignKey(
        InventoryItem,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_ticket_lines",
    )
    source_line_id = models.PositiveIntegerField(null=True, blank=True)
    position = models.PositiveIntegerField(default=1)
    sku_snapshot = models.CharField(max_length=64)
    name_snapshot = models.CharField(max_length=160)
    invoice_name_snapshot = models.CharField(max_length=160, blank=True, default="")
    uom_snapshot = models.CharField(max_length=16, default="UNIT")
    tax_profile_snapshot = models.CharField(max_length=64, blank=True, default="")
    tax_rate_snapshot = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0.0000"))
    qty = models.DecimalField(max_digits=18, decimal_places=4)
    unit_price = models.DecimalField(max_digits=18, decimal_places=6)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_tax = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ventas_retail"
        constraints = [
            models.UniqueConstraint(fields=["ticket", "position"], name="uq_retail_ticket_line_position"),
        ]
        indexes = [
            models.Index(fields=["ticket", "position"]),
        ]


class RetailPaymentRecord(models.Model):
    class Kind(models.TextChoices):
        SALE_CAPTURE = "SALE_CAPTURE", "Sale capture"
        SALE_REFUND = "SALE_REFUND", "Sale refund"

    class Status(models.TextChoices):
        INTENDED = "INTENDED", "Intended"
        CAPTURED = "CAPTURED", "Captured"
        REFUNDED = "REFUNDED", "Refunded"
        FAILED = "FAILED", "Failed"

    ticket = models.ForeignKey(RetailTicket, on_delete=models.CASCADE, related_name="payment_records")
    payment_intent = models.ForeignKey(
        PaymentIntent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_payment_records",
    )
    cash_movement = models.ForeignKey(
        CashMovement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_payment_records",
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.INTENDED)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    cash_received = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    change_due = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    reason = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=96, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "ventas_retail"
        constraints = [
            models.UniqueConstraint(
                fields=["ticket", "kind", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uq_retail_payment_record_ticket_kind_idem",
            ),
        ]
        indexes = [
            models.Index(fields=["ticket", "kind", "created_at"]),
        ]


class RetailSale(models.Model):
    class Status(models.TextChoices):
        CHECKOUT_PENDING = "CHECKOUT_PENDING", "Checkout pending"
        COMPLETED = "COMPLETED", "Completed"
        VOIDED = "VOIDED", "Voided"
        COMPENSATING = "COMPENSATING", "Compensating"
        COMPENSATION_FAILED = "COMPENSATION_FAILED", "Compensation failed"

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="retail_sales_company")
    branch = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="retail_sales_branch")
    ticket = models.OneToOneField(RetailTicket, on_delete=models.PROTECT, related_name="sale")
    terminal = models.ForeignKey(
        RetailTerminal,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sales",
    )
    cash_session = models.ForeignKey(
        CashSession,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_sales",
    )
    billing_doc = models.ForeignKey(
        BillingDocument,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_sales",
    )
    payment_intent = models.ForeignKey(
        PaymentIntent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_sales",
    )
    cash_movement = models.ForeignKey(
        CashMovement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_sales",
    )
    inventory_movement_ids = models.JSONField(default=list, blank=True)
    reversal_movement_ids = models.JSONField(default=list, blank=True)
    flow_correlation_id = models.CharField(max_length=96, blank=True, default="", db_index=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.CHECKOUT_PENDING)
    accounting_status = models.CharField(max_length=24, blank=True, default="")
    compensation_attempts = models.PositiveIntegerField(default=0)
    compensation_last_error = models.CharField(max_length=255, blank=True, default="")
    compensation_next_retry_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retail_sales_created",
    )

    class Meta:
        app_label = "ventas_retail"
        indexes = [
            models.Index(fields=["company", "branch", "status", "created_at"]),
            models.Index(fields=["status", "compensation_next_retry_at", "created_at"]),
        ]


class RetailHold(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        RESUMED = "RESUMED", "Resumed"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"

    ticket = models.ForeignKey(RetailTicket, on_delete=models.CASCADE, related_name="holds")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    reason = models.CharField(max_length=255, blank=True, default="")
    held_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retail_holds_created",
    )
    held_at = models.DateTimeField(default=timezone.now, editable=False)
    resumed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "ventas_retail"
        indexes = [
            models.Index(fields=["status", "expires_at", "held_at"]),
        ]


class RetailReturn(models.Model):
    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="retail_returns_company")
    branch = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="retail_returns_branch")
    original_sale = models.ForeignKey(RetailSale, on_delete=models.PROTECT, related_name="returns")
    return_ticket = models.OneToOneField(RetailTicket, on_delete=models.PROTECT, related_name="return_record")
    credit_note_doc = models.ForeignKey(
        BillingDocument,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_returns",
    )
    refund_payment_intent = models.ForeignKey(
        PaymentIntent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_returns",
    )
    refund_cash_movement = models.ForeignKey(
        CashMovement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_returns",
    )
    inventory_movement_ids = models.JSONField(default=list, blank=True)
    flow_correlation_id = models.CharField(max_length=96, blank=True, default="", db_index=True)
    idempotency_key = models.CharField(max_length=96, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)
    reason = models.CharField(max_length=255, blank=True, default="")
    refund_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retail_returns_created",
    )

    class Meta:
        app_label = "ventas_retail"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uq_retail_return_company_idempotency",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "status", "created_at"]),
        ]


class RetailCommandExecution(models.Model):
    class Action(models.TextChoices):
        CHECKOUT_COMMIT = "CHECKOUT_COMMIT", "Checkout commit"
        SALE_VOID = "SALE_VOID", "Sale void"
        RETURN_CREATE = "RETURN_CREATE", "Return create"
        COMPENSATION_RETRY = "COMPENSATION_RETRY", "Compensation retry"

    class Status(models.TextChoices):
        STARTED = "STARTED", "Started"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="retail_command_exec_company")
    branch = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="retail_command_exec_branch")
    action = models.CharField(max_length=32, choices=Action.choices)
    idempotency_key = models.CharField(max_length=96)
    request_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.STARTED)
    response_json = models.JSONField(default=dict, blank=True)
    error_json = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=96, blank=True, default="")
    causation_id = models.CharField(max_length=96, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ventas_retail"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "action", "idempotency_key"],
                name="uq_retail_cmd_exec_company_action_idem",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "action", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]
