from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit


class PaymentIntent(models.Model):
    class Status(models.TextChoices):
        INTENDED = "INTENDED", "Intended"
        AUTHORIZED = "AUTHORIZED", "Authorized"
        CAPTURED = "CAPTURED", "Captured"
        REFUNDED = "REFUNDED", "Refunded"
        FAILED = "FAILED", "Failed"

    payment_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="pay_intents_company")
    branch = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pay_intents_branch",
    )

    external_ref = models.CharField(max_length=96, blank=True, default="")
    idempotency_key = models.CharField(max_length=96, blank=True, default="")

    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=8, default="NIO")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.INTENDED)

    provider = models.CharField(max_length=32, blank=True, default="")
    provider_txn_id = models.CharField(max_length=96, blank=True, default="")

    authorized_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True, default="")

    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "payments"
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="ck_pay_intent_amount_positive"),
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uq_pay_intent_company_idempotency",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "status", "created_at"]),
            models.Index(fields=["provider", "provider_txn_id"]),
        ]


class CashSession(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        COUNT_PENDING = "COUNT_PENDING", "Count pending"
        REVIEW_PENDING = "REVIEW_PENDING", "Review pending"
        CLOSED = "CLOSED", "Closed"
        REOPENED_FOR_INVESTIGATION = "REOPENED_FOR_INVESTIGATION", "Reopened for investigation"

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="cash_sessions_company")
    branch = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cash_sessions_branch",
    )

    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cash_sessions_opened",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cash_sessions_closed",
    )

    status = models.CharField(max_length=32, choices=Status.choices, default=Status.OPEN)

    opened_at = models.DateTimeField(default=timezone.now, editable=False)
    closed_at = models.DateTimeField(null=True, blank=True)

    opening_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    expected_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    counted_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    difference_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict)

    class Meta:
        app_label = "payments"
        indexes = [
            models.Index(fields=["company", "branch", "status", "opened_at"]),
        ]

    def clean(self):
        if self.status == self.Status.CLOSED and self.closed_at is None:
            raise ValidationError("CashSession cerrada requiere closed_at.")
        expected_difference = self.counted_amount - self.expected_amount
        if self.difference_amount != expected_difference:
            raise ValidationError("difference_amount debe ser counted_amount - expected_amount.")


class CashMovement(models.Model):
    class MovementType(models.TextChoices):
        INCOME = "INCOME", "Income"
        EXPENSE = "EXPENSE", "Expense"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        REFUND = "REFUND", "Refund"

    session = models.ForeignKey(CashSession, on_delete=models.CASCADE, related_name="movements")
    movement_type = models.CharField(max_length=16, choices=MovementType.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    reference = models.CharField(max_length=96, blank=True, default="")
    reason = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cash_movements_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "payments"
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="ck_cash_movement_amount_positive"),
        ]
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]
