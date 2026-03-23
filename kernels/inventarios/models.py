from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class UoM(models.TextChoices):
    UNIT = "UNIT", "Unit"
    LITER = "LITER", "Liter"
    KILOGRAM = "KILOGRAM", "Kilogram"
    BOX = "BOX", "Box"
    GALLON = "GALLON", "Gallon"
    METER = "METER", "Meter"


class ItemType(models.TextChoices):
    INVENTARIABLE = "INVENTARIABLE", "Inventariable"
    NO_INVENTARIABLE = "NO_INVENTARIABLE", "No inventariable"
    SERVICIO = "SERVICIO", "Servicio"


class ItemStatus(models.TextChoices):
    ACTIVO = "ACTIVO", "Activo"
    INACTIVO = "INACTIVO", "Inactivo"
    BLOQUEADO = "BLOQUEADO", "Bloqueado"


class BarcodeType(models.TextChoices):
    EAN13 = "EAN13", "EAN-13"
    UPCA = "UPCA", "UPC-A"
    CODE128 = "CODE128", "Code 128"
    INTERNO = "INTERNO", "Interno"


class TaxTreatment(models.TextChoices):
    GRAVADO = "GRAVADO", "Gravado"
    EXENTO = "EXENTO", "Exento"
    EXONERADO = "EXONERADO", "Exonerado"


class CostingMethod(models.TextChoices):
    MOVING_WEIGHTED_AVG = "MOVING_WEIGHTED_AVG", "Moving weighted average"


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


class InventoryBrand(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_brands")
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["company", "is_active", "name"], name="ix_invbrand_c_an"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_inv_brand_name_c"),
        ]


class InventoryCategory(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_categories")
    name = models.CharField(max_length=80)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["company", "parent", "is_active", "name"], name="ix_invcat_c_pan"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["company", "parent", "name"], name="uniq_inv_cat_name_cp"),
        ]


class InventoryTaxProfile(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_tax_profiles")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    tax_treatment = models.CharField(max_length=16, choices=TaxTreatment.choices, default=TaxTreatment.GRAVADO)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["company", "is_active", "code"], name="ix_invtax_c_ac"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_inv_tax_code_c"),
        ]


class InventoryItem(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_items_company")

    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=160)
    uom = models.CharField(max_length=16, choices=UoM.choices, default=UoM.UNIT)

    item_type = models.CharField(max_length=20, choices=ItemType.choices, default=ItemType.INVENTARIABLE)
    status = models.CharField(max_length=16, choices=ItemStatus.choices, default=ItemStatus.ACTIVO)
    short_name = models.CharField(max_length=80, blank=True, default="")
    invoice_name = models.CharField(max_length=160, blank=True, default="")
    description = models.CharField(max_length=500, blank=True, default="")

    brand = models.ForeignKey(
        InventoryBrand,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="items",
    )
    category = models.ForeignKey(
        InventoryCategory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="items",
    )
    subcategory = models.ForeignKey(
        InventoryCategory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sub_items",
    )

    barcode = models.CharField(max_length=64, blank=True, default="")
    barcode_type = models.CharField(max_length=16, choices=BarcodeType.choices, blank=True, default="")
    alternate_code = models.CharField(max_length=64, blank=True, default="")
    search_tags = models.JSONField(default=list, blank=True)

    purchase_enabled = models.BooleanField(default=True)
    sales_enabled = models.BooleanField(default=True)
    controls_stock = models.BooleanField(default=True)
    transfer_enabled = models.BooleanField(default=True)
    allow_returns = models.BooleanField(default=True)

    uom_base = models.CharField(max_length=16, choices=UoM.choices, default=UoM.UNIT)
    uom_purchase = models.CharField(max_length=16, choices=UoM.choices, default=UoM.UNIT)
    uom_sale = models.CharField(max_length=16, choices=UoM.choices, default=UoM.UNIT)
    uom_conversions = models.JSONField(default=list, blank=True)
    allow_fraction = models.BooleanField(default=False)
    min_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    rounding_increment = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))

    default_branch = models.ForeignKey(
        "iam.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inv_items_default_branch",
    )
    default_warehouse = models.ForeignKey(
        Warehouse,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="default_for_items",
    )
    enabled_branch_ids = models.JSONField(default=list, blank=True)

    min_stock = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    max_stock = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    reorder_point = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    reorder_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    allow_negative_stock = models.BooleanField(default=False)
    reserve_enabled = models.BooleanField(default=False)
    internal_location = models.CharField(max_length=64, blank=True, default="")

    costing_method = models.CharField(max_length=32, choices=CostingMethod.choices, default=CostingMethod.MOVING_WEIGHTED_AVG)
    initial_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    standard_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    currency = models.CharField(max_length=3, default="NIO")
    last_known_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))

    preferred_supplier_id = models.IntegerField(null=True, blank=True)
    supplier_item_code = models.CharField(max_length=64, blank=True, default="")
    lead_time_days = models.IntegerField(null=True, blank=True)
    purchase_moq = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    purchase_multiple = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))

    suggested_price = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    min_sale_price = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    allow_discount = models.BooleanField(default=True)
    visible_pos = models.BooleanField(default=True)
    visible_quote = models.BooleanField(default=True)
    visible_invoice = models.BooleanField(default=True)

    tax_profile = models.ForeignKey(
        InventoryTaxProfile,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="items",
    )
    tax_treatment = models.CharField(max_length=16, choices=TaxTreatment.choices, default=TaxTreatment.GRAVADO)
    invoice_description = models.CharField(max_length=160, blank=True, default="")

    use_lot = models.BooleanField(default=False)
    use_serial = models.BooleanField(default=False)
    use_expiry = models.BooleanField(default=False)
    shelf_life_days = models.IntegerField(null=True, blank=True)
    quality_control_required = models.BooleanField(default=False)
    allow_return_to_stock = models.BooleanField(default=True)

    is_active = models.BooleanField(default=True)
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["company", "is_active", "sku"], name="ix_invitm_c_as"),
            models.Index(fields=["company", "is_active", "name"], name="ix_invitm_c_an"),
            models.Index(fields=["company", "barcode"], name="ix_invitm_c_bar"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["company", "sku"], name="uniq_inv_sku_pc"),
            models.UniqueConstraint(
                fields=["company", "barcode"],
                condition=~models.Q(barcode=""),
                name="uniq_inv_barcode_pc",
            ),
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
    class AccountingStatus(models.TextChoices):
        DISABLED = "DISABLED", "Disabled"
        UNSUPPORTED = "UNSUPPORTED", "Unsupported"
        PENDING_RULESET = "PENDING_RULESET", "Pending ruleset"
        PENDING_RULE = "PENDING_RULE", "Pending rule"
        DRAFT_EXCEPTION = "DRAFT_EXCEPTION", "Draft exception"
        DRAFT_VALIDATED = "DRAFT_VALIDATED", "Draft validated"
        POSTED = "POSTED", "Posted"

    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_mov_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_mov_branch")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="movements")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="movements")

    movement_type = models.CharField(max_length=16, choices=MovementType.choices)
    qty_delta = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    total_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))

    source_module = models.CharField(max_length=32, blank=True, default="")
    source_type = models.CharField(max_length=64, blank=True, default="")
    source_id = models.CharField(max_length=64, blank=True, default="")

    note = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=96, blank=True, default="")

    accounting_status = models.CharField(
        max_length=24,
        choices=AccountingStatus.choices,
        blank=True,
        default="",
    )
    accounting_error = models.CharField(max_length=255, blank=True, default="")
    accounting_economic_event = models.ForeignKey(
        "accounting.EconomicEvent",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inventory_movements",
    )
    accounting_journal_draft = models.ForeignKey(
        "accounting.JournalDraft",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inventory_movements",
    )
    accounting_journal_entry = models.ForeignKey(
        "accounting.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inventory_movements",
    )

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "created_at"], name="ix_invmov_c_b_ca"),
            models.Index(fields=["company", "branch", "item", "created_at"], name="ix_invmov_item_ca"),
            models.Index(fields=["company", "branch", "warehouse", "created_at"], name="ix_invmov_wh_ca"),
            models.Index(fields=["company", "idempotency_key"], name="ix_invmov_idem"),
            models.Index(fields=["company", "branch", "accounting_status", "created_at"], name="ix_invmov_acc_st"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_invmov_idem",
            )
        ]
