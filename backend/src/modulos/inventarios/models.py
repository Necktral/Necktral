from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class UoM(models.TextChoices):
    UNIT = "UNIT", "Unit"
    LITER = "LITER", "Liter"


class Warehouse(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_warehouses_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_warehouses_branch")

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=24, blank=True, default="")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "is_active", "name"], name="ix_invwh_c_b_an"),
            models.Index(fields=["company", "branch", "code"], name="ix_invwh_c_b_code"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["company", "branch", "code"], name="uniq_inv_wh_code_pb"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class InventoryItem(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_items_company")
    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=160)
    uom = models.CharField(max_length=16, choices=UoM.choices, default=UoM.UNIT)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["company", "is_active", "sku"], name="ix_invitm_c_as"),
            models.Index(fields=["company", "is_active", "name"], name="ix_invitm_c_an"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["company", "sku"], name="uniq_inv_sku_pc"),
        ]

    def __str__(self) -> str:
        return f"{self.sku} - {self.name}"


class StockBalance(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_bal_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_bal_branch")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="balances")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="balances")

    qty_on_hand = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    avg_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))

    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "branch", "warehouse", "item"],
                name="uniq_inv_bal_scope",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "warehouse", "item"], name="ix_invbal_scope"),
        ]


class MovementType(models.TextChoices):
    RECEIVE = "RECEIVE", "Receive"
    ISSUE = "ISSUE", "Issue"
    ADJUST = "ADJUST", "Adjust"
    TRANSFER_OUT = "TRANSFER_OUT", "Transfer Out"
    TRANSFER_IN = "TRANSFER_IN", "Transfer In"


class StockMovement(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_mov_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_mov_branch")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="movements")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="movements")

    movement_type = models.CharField(max_length=16, choices=MovementType.choices)
    qty_delta = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    total_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))

    # Referencia a origen (kernel/entidad) para trazabilidad
    source_module = models.CharField(max_length=32, blank=True, default="")
    source_type = models.CharField(max_length=64, blank=True, default="")
    source_id = models.CharField(max_length=64, blank=True, default="")

    note = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=96, blank=True, default="")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "created_at"], name="ix_invmov_c_b_ca"),
            models.Index(fields=["company", "branch", "item", "created_at"], name="ix_invmov_item_ca"),
            models.Index(fields=["company", "branch", "warehouse", "created_at"], name="ix_invmov_wh_ca"),
            models.Index(fields=["company", "idempotency_key"], name="ix_invmov_idem"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_invmov_idem",
            )
        ]
