"""
Financial Portfolio Kernel Models

Modelos para gestión de CxC, CxP y Créditos con máxima flexibilidad.
Diseñado para permitir múltiples opciones configurables.
"""
import uuid
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ObligationType(models.TextChoices):
    """Tipos de obligaciones financieras"""
    RECEIVABLE = "RECEIVABLE", _("Receivable")
    PAYABLE = "PAYABLE", _("Payable")
    CREDIT = "CREDIT", _("Credit")
    LOAN = "LOAN", _("Loan")


class ObligationStatus(models.TextChoices):
    """Estados de obligaciones"""
    PENDING = "PENDING", _("Pending")
    PARTIAL = "PARTIAL", _("Partially Paid")
    PAID = "PAID", _("Paid")
    OVERDUE = "OVERDUE", _("Overdue")
    WRITTEN_OFF = "WRITTEN_OFF", _("Written Off")
    DISPUTED = "DISPUTED", _("Disputed")
    RESTRUCTURED = "RESTRUCTURED", _("Restructured")
    CANCELLED = "CANCELLED", _("Cancelled")


class AccountingStatus(models.TextChoices):
    """Estados contables para Shadow Ledger"""
    PENDING_RULESET = "PENDING_RULESET", _("Pending RuleSet")
    PENDING_RULE = "PENDING_RULE", _("Pending Rule")
    DRAFT_GENERATED = "DRAFT_GENERATED", _("Draft Generated")
    DRAFT_EXCEPTION = "DRAFT_EXCEPTION", _("Draft Exception")
    POSTED = "POSTED", _("Posted")


class Obligation(models.Model):
    """
    Base abstracta para todas las obligaciones financieras.

    Diseñado con máxima flexibilidad para permitir ajustes posteriores.
    Cada tipo (Receivable, Payable, Credit) hereda y añade campos específicos.
    """

    # Identificador único
    obligation_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="UUID único de la obligación"
    )

    # Scope organizacional
    company = models.ForeignKey(
        "iam.OrgUnit",
        on_delete=models.PROTECT,
        related_name="%(class)s_company",
        help_text="Empresa propietaria"
    )
    branch = models.ForeignKey(
        "iam.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="%(class)s_branch",
        help_text="Sucursal (opcional)"
    )

    # Tipo y estado
    obligation_type = models.CharField(
        max_length=16,
        choices=ObligationType.choices,
        db_index=True,
        help_text="Tipo de obligación"
    )
    status = models.CharField(
        max_length=16,
        choices=ObligationStatus.choices,
        default=ObligationStatus.PENDING,
        db_index=True,
        help_text="Estado actual"
    )

    # Contraparte (Party)
    party = models.ForeignKey(
        "parties.Party",
        on_delete=models.PROTECT,
        related_name="%(class)s_obligations",
        help_text="Contraparte (cliente, proveedor, prestatario)"
    )

    # Referencia al documento origen
    reference_type = models.CharField(
        max_length=32,
        db_index=True,
        help_text="Tipo de documento origen (BILLING_DOCUMENT, PURCHASE_DOCUMENT, etc.)"
    )
    reference_id = models.PositiveIntegerField(
        db_index=True,
        help_text="ID del documento origen"
    )

    # Montos en moneda original
    currency = models.CharField(
        max_length=8,
        default="NIO",
        db_index=True,
        help_text="Moneda de la obligación"
    )
    principal_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        help_text="Monto principal"
    )
    interest_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Monto de intereses acumulados"
    )
    fee_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Monto de comisiones"
    )
    penalty_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Monto de penalidades/mora"
    )
    allocated_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Monto aplicado/pagado"
    )

    # Fechas
    issue_date = models.DateField(
        db_index=True,
        help_text="Fecha de emisión"
    )
    due_date = models.DateField(
        db_index=True,
        help_text="Fecha de vencimiento"
    )
    last_payment_date = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha del último pago"
    )
    paid_date = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha de pago completo"
    )
    written_off_date = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha de castigo"
    )

    # Aging (calculado)
    days_overdue = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Días vencidos (calculado)"
    )
    aging_bucket = models.CharField(
        max_length=16,
        blank=True,
        default="",
        db_index=True,
        help_text="Bucket de antigüedad (CURRENT, 0-30, 31-60, etc.)"
    )

    # Accounting projection
    accounting_status = models.CharField(
        max_length=24,
        choices=AccountingStatus.choices,
        default=AccountingStatus.PENDING_RULESET,
        db_index=True,
        help_text="Estado contable para Shadow Ledger"
    )

    # Metadata flexible
    metadata_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Metadata adicional en JSON (máxima flexibilidad)"
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Notas adicionales"
    )

    # Auditoría
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_created",
        help_text="Usuario que creó"
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        db_index=True
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_index=True
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "party", "status", "due_date"]),
            models.Index(fields=["company", "status", "due_date"]),
            models.Index(fields=["reference_type", "reference_id"]),
            models.Index(fields=["obligation_type", "status", "due_date"]),
            models.Index(fields=["currency", "status"]),
            models.Index(fields=["aging_bucket", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(principal_amount__gt=0),
                name="%(class)s_principal_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(allocated_amount__gte=0),
                name="%(class)s_allocated_non_negative"
            ),
        ]

    def __str__(self):
        return f"{self.obligation_type} {self.obligation_id} - {self.party}"

    @property
    def total_amount(self) -> Decimal:
        """Monto total de la obligación"""
        return (
            self.principal_amount +
            self.interest_amount +
            self.fee_amount +
            self.penalty_amount
        )

    @property
    def outstanding_amount(self) -> Decimal:
        """Monto pendiente de pago"""
        return self.total_amount - self.allocated_amount

    @property
    def is_overdue(self) -> bool:
        """¿Está vencida?"""
        if self.status in (ObligationStatus.PAID, ObligationStatus.WRITTEN_OFF, ObligationStatus.CANCELLED):
            return False
        return self.due_date < timezone.localdate()

    def calculate_days_overdue(self) -> int:
        """Calcula días vencidos"""
        if not self.is_overdue:
            return 0
        return (timezone.localdate() - self.due_date).days

    def calculate_aging_bucket(self) -> str:
        """Calcula bucket de antigüedad (configurable)"""
        days = self.calculate_days_overdue()

        # Buckets por defecto (configurable vía PortfolioSettings)
        if days == 0:
            return "CURRENT"
        elif days <= 30:
            return "0-30"
        elif days <= 60:
            return "31-60"
        elif days <= 90:
            return "61-90"
        elif days <= 120:
            return "91-120"
        else:
            return "120+"

    def update_aging(self):
        """Actualiza campos de aging"""
        self.days_overdue = self.calculate_days_overdue()
        self.aging_bucket = self.calculate_aging_bucket()

        # Auto-actualiza status si está vencida
        if self.is_overdue and self.status == ObligationStatus.PENDING:
            self.status = ObligationStatus.OVERDUE

    def clean(self):
        """Validaciones del modelo"""
        super().clean()

        # Validar que allocated no exceda total
        if self.allocated_amount > self.total_amount:
            raise ValidationError({
                "allocated_amount": _("Allocated amount cannot exceed total amount")
            })

        # Validar fechas
        if self.due_date and self.issue_date and self.due_date < self.issue_date:
            raise ValidationError({
                "due_date": _("Due date cannot be before issue date")
            })

    def save(self, *args, **kwargs):
        """Override save para actualizar aging"""
        self.update_aging()
        super().save(*args, **kwargs)


class Receivable(Obligation):
    """
    Cuentas por Cobrar (CxC)

    Representa dinero que nos deben los clientes.
    """

    obligation_type = models.CharField(
        max_length=16,
        default=ObligationType.RECEIVABLE,
        editable=False
    )

    # Campos específicos de CxC
    invoice_number = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Número de factura"
    )
    invoice_date = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha de factura"
    )

    # Términos de crédito
    credit_limit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Límite de crédito del cliente"
    )
    credit_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Días de crédito aprobados"
    )

    # Gestión de cobro
    risk_rating = models.CharField(
        max_length=8,
        blank=True,
        default="",
        db_index=True,
        help_text="Calificación de riesgo (A, B, C, D)"
    )
    collection_priority = models.CharField(
        max_length=16,
        blank=True,
        default="NORMAL",
        db_index=True,
        help_text="Prioridad de cobro (HIGH, NORMAL, LOW)"
    )
    collector_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="receivables_assigned",
        help_text="Usuario asignado para cobro"
    )

    class Meta:
        db_table = "portfolio_receivable"
        verbose_name = _("Receivable")
        verbose_name_plural = _("Receivables")
        indexes = Obligation.Meta.indexes + [
            models.Index(fields=["company", "party", "status", "aging_bucket"]),
            models.Index(fields=["company", "invoice_number"]),
            models.Index(fields=["collection_priority", "status"]),
        ]
        constraints = Obligation.Meta.constraints

    def __str__(self):
        inv = f" - {self.invoice_number}" if self.invoice_number else ""
        return f"CxC{inv}: {self.party} - {self.outstanding_amount} {self.currency}"


class Payable(Obligation):
    """
    Cuentas por Pagar (CxP)

    Representa dinero que debemos a proveedores.
    """

    obligation_type = models.CharField(
        max_length=16,
        default=ObligationType.PAYABLE,
        editable=False
    )

    # Campos específicos de CxP
    supplier_invoice_number = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Número de factura del proveedor"
    )
    supplier_invoice_date = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha de factura del proveedor"
    )

    # Descuentos por pronto pago
    early_payment_discount_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="% de descuento por pronto pago (ej. 2.00 = 2%)"
    )
    early_payment_discount_days = models.PositiveIntegerField(
        default=0,
        help_text="Días para aplicar descuento (ej. pagar en 10 días)"
    )
    early_payment_discount_date = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha límite para descuento"
    )

    # Retenciones
    withholding_tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="% de retención"
    )
    withholding_tax_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Monto retenido"
    )

    # Gestión de pago
    payment_priority = models.CharField(
        max_length=16,
        blank=True,
        default="NORMAL",
        db_index=True,
        help_text="Prioridad de pago (URGENT, NORMAL, LOW)"
    )
    approver_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payables_approved",
        help_text="Usuario que aprueba el pago"
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha de aprobación"
    )

    class Meta:
        db_table = "portfolio_payable"
        verbose_name = _("Payable")
        verbose_name_plural = _("Payables")
        indexes = Obligation.Meta.indexes + [
            models.Index(fields=["company", "party", "status", "payment_priority"]),
            models.Index(fields=["company", "supplier_invoice_number"]),
            models.Index(fields=["payment_priority", "status", "due_date"]),
        ]
        constraints = Obligation.Meta.constraints

    @property
    def net_payable_amount(self) -> Decimal:
        """Monto neto a pagar (descontando retenciones)"""
        return self.outstanding_amount - self.withholding_tax_amount

    @property
    def discount_available(self) -> Decimal:
        """Descuento disponible si se paga ahora"""
        if not self.early_payment_discount_date:
            return Decimal("0.00")
        if timezone.localdate() <= self.early_payment_discount_date:
            return (self.outstanding_amount * self.early_payment_discount_rate / Decimal("100.00"))
        return Decimal("0.00")

    def __str__(self):
        inv = f" - {self.supplier_invoice_number}" if self.supplier_invoice_number else ""
        return f"CxP{inv}: {self.party} - {self.outstanding_amount} {self.currency}"


class CreditType(models.TextChoices):
    """Tipos de crédito"""
    WORKING_CAPITAL = "WORKING_CAPITAL", _("Working Capital")
    TERM_LOAN = "TERM_LOAN", _("Term Loan")
    LINE_OF_CREDIT = "LINE_OF_CREDIT", _("Line of Credit")
    MORTGAGE = "MORTGAGE", _("Mortgage")
    EQUIPMENT_FINANCING = "EQUIPMENT_FINANCING", _("Equipment Financing")
    FACTORING = "FACTORING", _("Factoring")
    SUPPLIER_CREDIT = "SUPPLIER_CREDIT", _("Supplier Credit")
    INTERCOMPANY_LOAN = "INTERCOMPANY_LOAN", _("Intercompany Loan")


class CreditStatus(models.TextChoices):
    """Estados de crédito"""
    DRAFT = "DRAFT", _("Draft")
    APPROVED = "APPROVED", _("Approved")
    DISBURSED = "DISBURSED", _("Disbursed")
    ACTIVE = "ACTIVE", _("Active")
    RESTRUCTURED = "RESTRUCTURED", _("Restructured")
    PAID_OFF = "PAID_OFF", _("Paid Off")
    DEFAULTED = "DEFAULTED", _("Defaulted")
    WRITTEN_OFF = "WRITTEN_OFF", _("Written Off")


class InterestCalculationMethod(models.TextChoices):
    """Métodos de cálculo de interés"""
    SIMPLE = "SIMPLE", _("Simple Interest")
    COMPOUND = "COMPOUND", _("Compound Interest")
    FLAT = "FLAT", _("Flat Rate")


class PaymentFrequency(models.TextChoices):
    """Frecuencia de pago"""
    DAILY = "DAILY", _("Daily")
    WEEKLY = "WEEKLY", _("Weekly")
    BIWEEKLY = "BIWEEKLY", _("Biweekly")
    MONTHLY = "MONTHLY", _("Monthly")
    QUARTERLY = "QUARTERLY", _("Quarterly")
    SEMIANNUALLY = "SEMIANNUALLY", _("Semiannually")
    ANNUALLY = "ANNUALLY", _("Annually")


class Credit(Obligation):
    """
    Créditos Financieros

    Representa préstamos otorgados o recibidos.
    Máxima flexibilidad para diferentes tipos de crédito.
    """

    obligation_type = models.CharField(
        max_length=16,
        default=ObligationType.CREDIT,
        editable=False
    )

    # Tipo de crédito
    credit_type = models.CharField(
        max_length=32,
        choices=CreditType.choices,
        db_index=True,
        help_text="Tipo de crédito"
    )
    credit_status = models.CharField(
        max_length=16,
        choices=CreditStatus.choices,
        default=CreditStatus.DRAFT,
        db_index=True,
        help_text="Estado del crédito"
    )

    # Partes involucradas
    lender_party = models.ForeignKey(
        "parties.Party",
        on_delete=models.PROTECT,
        related_name="credits_as_lender",
        help_text="Prestamista"
    )
    borrower_party = models.ForeignKey(
        "parties.Party",
        on_delete=models.PROTECT,
        related_name="credits_as_borrower",
        help_text="Prestatario"
    )
    guarantor_party = models.ForeignKey(
        "parties.Party",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="credits_as_guarantor",
        help_text="Garante (opcional)"
    )

    # Montos del crédito
    approved_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        help_text="Monto aprobado"
    )
    disbursed_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Monto desembolsado"
    )

    # Términos del crédito
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Tasa de interés anual (%)"
    )
    interest_calculation_method = models.CharField(
        max_length=16,
        choices=InterestCalculationMethod.choices,
        default=InterestCalculationMethod.SIMPLE,
        help_text="Método de cálculo de interés"
    )
    payment_frequency = models.CharField(
        max_length=16,
        choices=PaymentFrequency.choices,
        default=PaymentFrequency.MONTHLY,
        help_text="Frecuencia de pago"
    )
    term_months = models.PositiveIntegerField(
        help_text="Plazo en meses"
    )
    grace_period_months = models.PositiveIntegerField(
        default=0,
        help_text="Período de gracia en meses"
    )

    # Fechas importantes
    approval_date = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha de aprobación"
    )
    disbursement_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Fecha de desembolso"
    )
    first_payment_date = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha del primer pago"
    )
    maturity_date = models.DateField(
        db_index=True,
        help_text="Fecha de vencimiento final"
    )

    # Mora y penalidades
    late_payment_penalty_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Tasa de penalidad por mora (%)"
    )
    days_past_due = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Días de mora"
    )

    # Garantías y colateral
    collateral_type = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Tipo de garantía (REAL_ESTATE, VEHICLE, INVENTORY, etc.)"
    )
    collateral_value = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor del colateral"
    )
    collateral_description = models.TextField(
        blank=True,
        default="",
        help_text="Descripción del colateral"
    )

    # Reestructuraciones
    restructured_from = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="restructurings",
        help_text="Crédito original si es reestructuración"
    )
    restructure_count = models.PositiveIntegerField(
        default=0,
        help_text="Número de reestructuraciones"
    )

    # Contrato
    contract_number = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Número de contrato"
    )
    contract_document_ref = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Referencia al documento de contrato"
    )

    class Meta:
        db_table = "portfolio_credit"
        verbose_name = _("Credit")
        verbose_name_plural = _("Credits")
        indexes = Obligation.Meta.indexes + [
            models.Index(fields=["company", "borrower_party", "credit_status"]),
            models.Index(fields=["company", "lender_party", "credit_status"]),
            models.Index(fields=["credit_type", "credit_status", "maturity_date"]),
            models.Index(fields=["contract_number"]),
            models.Index(fields=["disbursement_date", "credit_status"]),
        ]
        constraints = Obligation.Meta.constraints + [
            models.CheckConstraint(
                condition=models.Q(approved_amount__gt=0),
                name="credit_approved_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(disbursed_amount__lte=models.F("approved_amount")),
                name="credit_disbursed_lte_approved"
            ),
            models.CheckConstraint(
                condition=models.Q(interest_rate__gte=0),
                name="credit_interest_non_negative"
            ),
        ]

    def clean(self):
        """Validaciones adicionales para crédito"""
        super().clean()

        # Borrower y Lender deben ser diferentes
        if self.lender_party_id and self.borrower_party_id:
            if self.lender_party_id == self.borrower_party_id:
                raise ValidationError({
                    "borrower_party": _("Borrower and Lender must be different parties")
                })

    @property
    def loan_to_value_ratio(self) -> Optional[Decimal]:
        """LTV ratio si hay colateral"""
        if self.collateral_value and self.collateral_value > 0:
            return (self.approved_amount / self.collateral_value) * Decimal("100.00")
        return None

    def __str__(self):
        return f"Credit {self.contract_number or self.obligation_id}: {self.borrower_party} - {self.outstanding_amount} {self.currency}"


class AllocationStatus(models.TextChoices):
    """Estados de aplicación de pago"""
    PENDING = "PENDING", _("Pending")
    APPLIED = "APPLIED", _("Applied")
    REVERSED = "REVERSED", _("Reversed")


class PaymentAllocation(models.Model):
    """
    Aplicación de pagos a obligaciones

    Vincula pagos (PaymentIntent) con obligaciones (Receivable/Payable/Credit).
    Diseñado con flexibilidad para soportar allocation automática o manual.
    """

    allocation_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True
    )

    # Scope
    company = models.ForeignKey(
        "iam.OrgUnit",
        on_delete=models.PROTECT,
        related_name="payment_allocations_company"
    )

    # Pago origen
    payment_intent = models.ForeignKey(
        "payments.PaymentIntent",
        on_delete=models.PROTECT,
        related_name="allocations",
        help_text="Pago que se está aplicando"
    )

    # Obligación destino (polymorphic via GenericForeignKey)
    obligation_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        help_text="Tipo de obligación (Receivable, Payable, Credit)"
    )
    obligation_object_id = models.PositiveIntegerField(
        help_text="ID de la obligación"
    )
    obligation = GenericForeignKey("obligation_content_type", "obligation_object_id")

    # Estado y monto
    status = models.CharField(
        max_length=16,
        choices=AllocationStatus.choices,
        default=AllocationStatus.PENDING,
        db_index=True
    )
    allocated_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        help_text="Monto total aplicado"
    )
    currency = models.CharField(
        max_length=8,
        default="NIO"
    )

    # Desagregación del monto (flexibilidad para diferentes tipos)
    principal_applied = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Aplicado a principal"
    )
    interest_applied = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Aplicado a intereses"
    )
    fee_applied = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Aplicado a comisiones"
    )
    penalty_applied = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Aplicado a penalidades"
    )

    # Conversion de moneda (si aplica)
    exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Tasa de cambio aplicada (si monedas difieren)"
    )

    # Fechas
    allocation_date = models.DateField(
        db_index=True,
        help_text="Fecha de aplicación"
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp de aplicación"
    )
    reversed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp de reversión"
    )
    reversal_reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Razón de reversión"
    )

    # Auditoría
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_allocations_created"
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False
    )

    class Meta:
        db_table = "portfolio_payment_allocation"
        verbose_name = _("Payment Allocation")
        verbose_name_plural = _("Payment Allocations")
        ordering = ["-allocation_date", "-created_at"]
        indexes = [
            models.Index(fields=["company", "payment_intent", "status"]),
            models.Index(fields=["obligation_content_type", "obligation_object_id"]),
            models.Index(fields=["allocation_date", "status"]),
            models.Index(fields=["status", "applied_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(allocated_amount__gt=0),
                name="allocation_amount_positive"
            ),
        ]

    def clean(self):
        """Validaciones"""
        super().clean()

        # Suma de componentes debe igualar total
        components_sum = (
            self.principal_applied +
            self.interest_applied +
            self.fee_applied +
            self.penalty_applied
        )
        if components_sum > 0 and components_sum != self.allocated_amount:
            raise ValidationError({
                "allocated_amount": _(
                    f"Allocated amount ({self.allocated_amount}) must equal sum of components ({components_sum})"
                )
            })

    def __str__(self):
        return f"Allocation {self.allocation_id}: {self.allocated_amount} {self.currency}"


class InterestAccrual(models.Model):
    """
    Devengo de intereses en créditos

    Registra el cálculo y devengo de intereses periódicamente.
    Diseñado para soportar múltiples frecuencias (diario, mensual, etc.)
    """

    accrual_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True
    )

    # Crédito al que pertenece
    credit = models.ForeignKey(
        Credit,
        on_delete=models.PROTECT,
        related_name="interest_accruals",
        help_text="Crédito sobre el que se calcula interés"
    )

    # Período de devengo
    accrual_date = models.DateField(
        db_index=True,
        help_text="Fecha de devengo"
    )
    period_start = models.DateField(
        help_text="Inicio del período"
    )
    period_end = models.DateField(
        help_text="Fin del período"
    )
    days_in_period = models.PositiveIntegerField(
        help_text="Días en el período"
    )

    # Cálculo
    principal_balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        help_text="Balance de principal al inicio del período"
    )
    interest_rate_applied = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Tasa aplicada (%)"
    )
    accrued_interest = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        help_text="Interés devengado"
    )

    # Capitalización
    is_capitalized = models.BooleanField(
        default=False,
        db_index=True,
        help_text="¿Se capitalizó el interés?"
    )
    capitalized_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp de capitalización"
    )

    # Metadata
    calculation_method = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text="Método usado para calcular"
    )
    metadata_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detalles del cálculo"
    )

    # Auditoría
    calculated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Usuario/sistema que calculó"
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False
    )

    class Meta:
        db_table = "portfolio_interest_accrual"
        verbose_name = _("Interest Accrual")
        verbose_name_plural = _("Interest Accruals")
        ordering = ["-accrual_date"]
        indexes = [
            models.Index(fields=["credit", "accrual_date"]),
            models.Index(fields=["accrual_date", "is_capitalized"]),
            models.Index(fields=["credit", "is_capitalized"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["credit", "accrual_date"],
                name="unique_credit_accrual_date"
            ),
        ]

    def __str__(self):
        return f"Interest {self.accrual_date}: {self.accrued_interest} on {self.credit}"


class PortfolioSettings(models.Model):
    """
    Configuración del Portfolio Kernel por Company

    Máxima flexibilidad para configurar comportamiento sin cambiar código.
    """

    company = models.OneToOneField(
        "iam.OrgUnit",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="portfolio_settings"
    )

    # Aging buckets configurables
    aging_buckets_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuración de buckets de aging (ej. {0: 'CURRENT', 30: '0-30', 60: '31-60'})"
    )

    # Allocation behavior
    auto_allocate_payments = models.BooleanField(
        default=True,
        help_text="¿Aplicar pagos automáticamente a obligaciones?"
    )
    allocation_strategy = models.CharField(
        max_length=16,
        default="FIFO",
        help_text="Estrategia de allocation (FIFO, LIFO, SMALLEST_FIRST, etc.)"
    )

    # Interest accrual
    interest_accrual_frequency = models.CharField(
        max_length=16,
        default="MONTHLY",
        help_text="Frecuencia de devengo de intereses"
    )
    auto_capitalize_interest = models.BooleanField(
        default=False,
        help_text="¿Capitalizar intereses automáticamente?"
    )

    # Write-offs
    auto_writeoff_enabled = models.BooleanField(
        default=False,
        help_text="¿Permitir castigo automático?"
    )
    auto_writeoff_days = models.PositiveIntegerField(
        default=365,
        help_text="Días de mora para castigo automático"
    )

    # CEC Gates
    gate_mode = models.CharField(
        max_length=16,
        default="BLOCKING",
        help_text="Modo de gates (BLOCKING, WARNING, DISABLED)"
    )

    # Multi-currency
    functional_currency = models.CharField(
        max_length=8,
        default="NIO",
        help_text="Moneda funcional para reportes"
    )
    auto_convert_currency = models.BooleanField(
        default=False,
        help_text="¿Convertir automáticamente a moneda funcional?"
    )

    # Integration
    sync_with_billing = models.BooleanField(
        default=True,
        help_text="¿Crear CxC automáticamente desde facturas?"
    )
    sync_with_procurement = models.BooleanField(
        default=True,
        help_text="¿Crear CxP automáticamente desde compras?"
    )
    integration_mode = models.CharField(
        max_length=16,
        default="ASYNC",
        help_text="Modo de integración (SYNC, ASYNC)"
    )

    # Metadata flexible
    settings_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuraciones adicionales en JSON"
    )

    # Auditoría
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    class Meta:
        db_table = "portfolio_settings"
        verbose_name = _("Portfolio Settings")
        verbose_name_plural = _("Portfolio Settings")

    def __str__(self):
        return f"Portfolio Settings: {self.company}"

    @classmethod
    def get_or_create_for_company(cls, company):
        """Obtiene o crea settings con defaults"""
        settings, created = cls.objects.get_or_create(
            company=company,
            defaults={
                "aging_buckets_json": {
                    "0": "CURRENT",
                    "30": "0-30",
                    "60": "31-60",
                    "90": "61-90",
                    "120": "91-120",
                    "999": "120+"
                }
            }
        )
        return settings
