from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.modulos.estacion_servicios.models import (
    FuelPaymentMethod,
    FuelPriceUOM,
    FuelProduct,
    FuelSaleType,
    FuelVolumeUOM,
)


class PosSessionStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"


class PosTicketStatus(models.TextChoices):
    CART_OPEN = "CART_OPEN", "Cart open"
    CHECKOUT_PENDING = "CHECKOUT_PENDING", "Checkout pending"
    PAID = "PAID", "Paid"
    CLOSED = "CLOSED", "Closed"
    VOIDED = "VOIDED", "Voided"


class PosLineType(models.TextChoices):
    FUEL = "FUEL", "Fuel"


class PeripheralCapability(models.TextChoices):
    SUPPORTED = "supported", "Supported"
    EXPERIMENTAL = "experimental", "Experimental"
    UNSUPPORTED = "unsupported", "Unsupported"


class PeripheralStatus(models.TextChoices):
    ONLINE = "ONLINE", "Online"
    OFFLINE = "OFFLINE", "Offline"
    DEGRADED = "DEGRADED", "Degraded"


class PeripheralKind(models.TextChoices):
    THERMAL_PRINTER = "THERMAL_PRINTER", "Thermal printer"
    SCANNER = "SCANNER", "Scanner"
    DRAWER = "DRAWER", "Cash drawer"
    SCALE = "SCALE", "Scale"
    PAYMENT_TERMINAL = "PAYMENT_TERMINAL", "Payment terminal"


class PosEdgeChallengeStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONSUMED = "CONSUMED", "Consumed"
    EXPIRED = "EXPIRED", "Expired"


class PosEdgeSessionStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    CLOSED = "CLOSED", "Closed"
    EXPIRED = "EXPIRED", "Expired"


class PosSession(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="pos_sessions_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="pos_sessions_branch")

    status = models.CharField(max_length=16, choices=PosSessionStatus.choices, default=PosSessionStatus.OPEN)

    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pos_sessions_opened",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pos_sessions_closed",
    )

    cash_session = models.ForeignKey(
        "payments.CashSession",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_pos_sessions",
    )

    opening_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    counted_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    difference_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    note = models.CharField(max_length=255, blank=True, default="")

    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "retail_pos"
        indexes = [
            models.Index(fields=["company", "branch", "status", "opened_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["branch"],
                condition=models.Q(status=PosSessionStatus.OPEN),
                name="uq_open_pos_session_per_branch",
            )
        ]


class PosTicket(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="pos_tickets_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="pos_tickets_branch")
    session = models.ForeignKey(PosSession, on_delete=models.PROTECT, related_name="tickets")

    shift = models.ForeignKey(
        "estacion_servicios.FuelShift",
        on_delete=models.PROTECT,
        related_name="pos_tickets",
    )

    status = models.CharField(max_length=24, choices=PosTicketStatus.choices, default=PosTicketStatus.CART_OPEN)
    idempotency_key = models.CharField(max_length=96, blank=True, default="")

    correlation_id = models.CharField(max_length=96, blank=True, default="", db_index=True)
    causation_id = models.CharField(max_length=96, blank=True, default="")

    external_ref = models.CharField(max_length=96, blank=True, default="")

    customer_name = models.CharField(max_length=200, blank=True, default="")
    customer_ref = models.CharField(max_length=96, blank=True, default="")
    customer_party = models.ForeignKey(
        "parties.Party",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pos_tickets",
    )

    sale_type = models.CharField(max_length=16, choices=FuelSaleType.choices, default=FuelSaleType.PUBLIC)
    payment_method = models.CharField(max_length=16, choices=FuelPaymentMethod.choices, default=FuelPaymentMethod.CASH)

    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    sale = models.ForeignKey(
        "estacion_servicios.FuelSale",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pos_tickets",
    )
    payment_intent = models.ForeignKey(
        "payments.PaymentIntent",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pos_tickets",
    )
    cash_movement = models.ForeignKey(
        "payments.CashMovement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pos_tickets",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pos_tickets_created",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    checkout_started_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)

    void_reason = models.CharField(max_length=255, blank=True, default="")
    last_error = models.CharField(max_length=255, blank=True, default="")

    compensation_pending = models.BooleanField(default=False)
    compensation_attempts = models.PositiveIntegerField(default=0)
    compensation_last_error = models.CharField(max_length=255, blank=True, default="")
    compensation_next_retry_at = models.DateTimeField(null=True, blank=True)
    last_compensation_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "retail_pos"
        indexes = [
            models.Index(fields=["company", "branch", "status", "created_at"]),
            models.Index(fields=["status", "updated_at"]),
            models.Index(fields=["status", "compensation_pending", "compensation_next_retry_at", "updated_at"]),
            models.Index(fields=["company", "customer_party"], name="ix_pos_ticket_co_cust_party"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uq_pos_ticket_company_idempotency",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(compensation_pending=False)
                    | (
                        models.Q(status=PosTicketStatus.CHECKOUT_PENDING)
                        & models.Q(compensation_attempts__gt=0)
                        & models.Q(compensation_next_retry_at__isnull=False)
                    )
                ),
                name="ck_pos_ticket_comp_pending_state",
            ),
            models.CheckConstraint(
                condition=~models.Q(status=PosTicketStatus.CLOSED, compensation_pending=True),
                name="ck_pos_ticket_closed_no_comp_pending",
            ),
            models.CheckConstraint(
                condition=~models.Q(status=PosTicketStatus.CLOSED) | models.Q(compensation_next_retry_at__isnull=True),
                name="ck_pos_ticket_closed_no_next_retry",
            ),
        ]

    def clean(self):
        super().clean()
        if self.customer_party_id and self.company_id and self.customer_party.company_id != self.company_id:
            raise ValidationError({"customer_party": "customer_party debe pertenecer a PosTicket.company."})


class PosTicketLine(models.Model):
    ticket = models.ForeignKey(PosTicket, on_delete=models.CASCADE, related_name="lines")
    line_no = models.PositiveIntegerField(default=1)
    line_type = models.CharField(max_length=16, choices=PosLineType.choices, default=PosLineType.FUEL)

    product = models.CharField(max_length=16, choices=FuelProduct.choices)
    volume = models.DecimalField(max_digits=12, decimal_places=4)
    volume_uom = models.CharField(max_length=16, choices=FuelVolumeUOM.choices, default=FuelVolumeUOM.LITER)

    unit_price_entered = models.DecimalField(max_digits=12, decimal_places=4)
    unit_price_uom = models.CharField(max_length=16, choices=FuelPriceUOM.choices, default=FuelPriceUOM.PER_LITER)

    amount_estimated = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    metadata = models.JSONField(default=dict)

    class Meta:
        app_label = "retail_pos"
        indexes = [
            models.Index(fields=["ticket", "line_no"]),
            models.Index(fields=["product"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["ticket", "line_no"], name="uq_pos_ticket_line_no"),
        ]


class PosEdgeChallenge(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="pos_edge_challenges_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="pos_edge_challenges_branch")

    challenge_id = models.UUIDField(default=uuid4, unique=True, editable=False, db_index=True)
    nonce = models.CharField(max_length=96, default="")
    status = models.CharField(
        max_length=16,
        choices=PosEdgeChallengeStatus.choices,
        default=PosEdgeChallengeStatus.PENDING,
    )

    connector_id = models.CharField(max_length=96, blank=True, default="")
    connector_version = models.CharField(max_length=32, blank=True, default="")
    metadata = models.JSONField(default=dict)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pos_edge_challenges_created",
    )
    consumed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pos_edge_challenges_consumed",
    )

    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "retail_pos"
        indexes = [
            models.Index(fields=["company", "branch", "status", "expires_at"]),
            models.Index(fields=["issued_at"]),
        ]


class PosEdgeSession(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="pos_edge_sessions_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="pos_edge_sessions_branch")

    session_token = models.UUIDField(default=uuid4, unique=True, editable=False, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=PosEdgeSessionStatus.choices,
        default=PosEdgeSessionStatus.ACTIVE,
    )

    connector_id = models.CharField(max_length=96)
    connector_version = models.CharField(max_length=32, blank=True, default="")

    challenge = models.ForeignKey(
        PosEdgeChallenge,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="edge_sessions",
    )
    capability_registry = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pos_edge_sessions_created",
    )

    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "retail_pos"
        indexes = [
            models.Index(fields=["company", "branch", "status", "expires_at"]),
            models.Index(fields=["connector_id", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "branch", "connector_id"],
                condition=models.Q(status=PosEdgeSessionStatus.ACTIVE),
                name="uq_active_pos_edge_session_connector",
            )
        ]


class PosPeripheralStatus(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="pos_peripherals_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="pos_peripherals_branch")

    connector_id = models.CharField(max_length=96)
    connector_version = models.CharField(max_length=32, blank=True, default="")

    device_key = models.CharField(max_length=96)
    device_kind = models.CharField(max_length=32, choices=PeripheralKind.choices)

    capability_level = models.CharField(
        max_length=16,
        choices=PeripheralCapability.choices,
        default=PeripheralCapability.EXPERIMENTAL,
    )
    status = models.CharField(max_length=16, choices=PeripheralStatus.choices, default=PeripheralStatus.ONLINE)

    metadata = models.JSONField(default=dict)
    last_seen_at = models.DateTimeField(default=timezone.now)
    edge_session = models.ForeignKey(
        PosEdgeSession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="peripherals",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pos_peripherals_updated",
    )

    class Meta:
        app_label = "retail_pos"
        indexes = [
            models.Index(fields=["company", "branch", "status", "last_seen_at"]),
            models.Index(fields=["device_kind", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "branch", "device_key"],
                name="uq_pos_peripheral_company_branch_device",
            )
        ]
