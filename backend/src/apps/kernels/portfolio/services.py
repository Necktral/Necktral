"""
Financial Portfolio Kernel Services

Servicios de negocio para CxC, CxP y Créditos.
Diseñado con lógica híbrida: auto/manual según configuración.
"""
from decimal import Decimal
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.modulos.integration.services import publish_outbox_event
from apps.kernels.accounting.models import EconomicEvent

from .models import (
    Obligation,
    Receivable,
    Payable,
    Credit,
    PaymentAllocation,
    InterestAccrual,
    PortfolioSettings,
    ObligationStatus,
    AllocationStatus,
    CreditStatus,
    AccountingStatus,
)


class PortfolioDomainError(Exception):
    """Errores de negocio del Portfolio"""
    def __init__(self, code: str, message: str, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code}] {message}")


# ============================================================================
# RECEIVABLE SERVICES
# ============================================================================

def create_receivable(
    company,
    party,
    reference_type: str,
    reference_id: int,
    principal_amount: Decimal,
    currency: str,
    issue_date: date,
    due_date: date,
    branch=None,
    invoice_number: str = "",
    invoice_date: Optional[date] = None,
    credit_limit: Optional[Decimal] = None,
    credit_days: Optional[int] = None,
    created_by=None,
    metadata: Optional[Dict] = None,
) -> Receivable:
    """
    Crea una CxC (Cuenta por Cobrar)

    Diseñado para ser llamado desde Billing kernel cuando se emite factura a crédito.
    """
    if principal_amount <= 0:
        raise PortfolioDomainError(
            "INVALID_AMOUNT",
            f"Principal amount must be positive: {principal_amount}"
        )

    receivable = Receivable(
        company=company,
        branch=branch,
        party=party,
        reference_type=reference_type,
        reference_id=reference_id,
        currency=currency,
        principal_amount=principal_amount,
        issue_date=issue_date,
        due_date=due_date,
        invoice_number=invoice_number,
        invoice_date=invoice_date or issue_date,
        credit_limit=credit_limit,
        credit_days=credit_days,
        created_by=created_by,
        metadata_json=metadata or {},
        accounting_status=AccountingStatus.PENDING_RULESET,
    )

    receivable.full_clean()
    receivable.save()

    # Publicar evento para Shadow Ledger
    _publish_receivable_created_event(receivable)

    return receivable


def _publish_receivable_created_event(receivable: Receivable):
    """Publica evento PORTFOLIO.ReceivableCreated"""
    publish_outbox_event(
        source_module="PORTFOLIO",
        event_type="ReceivableCreated",
        company=receivable.company,
        branch=receivable.branch,
        payload={
            "receivable_id": str(receivable.obligation_id),
            "party_id": receivable.party_id,
            "principal_amount": str(receivable.principal_amount),
            "currency": receivable.currency,
            "issue_date": receivable.issue_date.isoformat(),
            "due_date": receivable.due_date.isoformat(),
            "reference_type": receivable.reference_type,
            "reference_id": receivable.reference_id,
            "invoice_number": receivable.invoice_number,
        }
    )


def adjust_receivable(
    receivable: Receivable,
    adjustment_amount: Decimal,
    reason: str,
    adjusted_by,
) -> Receivable:
    """
    Ajusta el monto de una CxC

    Puede ser por descuento, recargo, corrección, etc.
    """
    old_amount = receivable.principal_amount
    new_amount = old_amount + adjustment_amount

    if new_amount < 0:
        raise PortfolioDomainError(
            "INVALID_ADJUSTMENT",
            f"Adjustment would result in negative amount: {new_amount}"
        )

    receivable.principal_amount = new_amount
    receivable.metadata_json.setdefault("adjustments", []).append({
        "date": timezone.now().isoformat(),
        "old_amount": str(old_amount),
        "adjustment": str(adjustment_amount),
        "new_amount": str(new_amount),
        "reason": reason,
        "adjusted_by_id": adjusted_by.id if adjusted_by else None,
    })
    receivable.save()

    # Publicar evento
    publish_outbox_event(
        source_module="PORTFOLIO",
        event_type="ReceivableAdjusted",
        company=receivable.company,
        branch=receivable.branch,
        payload={
            "receivable_id": str(receivable.obligation_id),
            "old_amount": str(old_amount),
            "adjustment_amount": str(adjustment_amount),
            "new_amount": str(new_amount),
            "reason": reason,
        }
    )

    return receivable


def write_off_receivable(
    receivable: Receivable,
    reason: str,
    approved_by,
) -> Receivable:
    """
    Castiga una CxC (write-off)

    Marca como incobrable.
    """
    if receivable.status == ObligationStatus.WRITTEN_OFF:
        raise PortfolioDomainError(
            "ALREADY_WRITTEN_OFF",
            f"Receivable {receivable.obligation_id} already written off"
        )

    if receivable.status == ObligationStatus.PAID:
        raise PortfolioDomainError(
            "CANNOT_WRITEOFF_PAID",
            f"Cannot write off paid receivable {receivable.obligation_id}"
        )

    receivable.status = ObligationStatus.WRITTEN_OFF
    receivable.written_off_date = timezone.localdate()
    receivable.metadata_json["writeoff"] = {
        "date": timezone.now().isoformat(),
        "reason": reason,
        "approved_by_id": approved_by.id if approved_by else None,
        "outstanding_amount": str(receivable.outstanding_amount),
    }
    receivable.save()

    # Publicar evento
    publish_outbox_event(
        source_module="PORTFOLIO",
        event_type="ReceivableWrittenOff",
        company=receivable.company,
        branch=receivable.branch,
        payload={
            "receivable_id": str(receivable.obligation_id),
            "written_off_amount": str(receivable.outstanding_amount),
            "reason": reason,
        }
    )

    return receivable


# ============================================================================
# PAYABLE SERVICES
# ============================================================================

def create_payable(
    company,
    party,
    reference_type: str,
    reference_id: int,
    principal_amount: Decimal,
    currency: str,
    issue_date: date,
    due_date: date,
    branch=None,
    supplier_invoice_number: str = "",
    supplier_invoice_date: Optional[date] = None,
    early_payment_discount_rate: Decimal = Decimal("0.00"),
    early_payment_discount_days: int = 0,
    withholding_tax_rate: Decimal = Decimal("0.00"),
    created_by=None,
    metadata: Optional[Dict] = None,
) -> Payable:
    """
    Crea una CxP (Cuenta por Pagar)

    Diseñado para ser llamado desde Compras cuando se recibe factura de proveedor.
    """
    if principal_amount <= 0:
        raise PortfolioDomainError(
            "INVALID_AMOUNT",
            f"Principal amount must be positive: {principal_amount}"
        )

    # Calcular withholding si aplica
    withholding_amount = Decimal("0.00")
    if withholding_tax_rate > 0:
        withholding_amount = (principal_amount * withholding_tax_rate / Decimal("100.00")).quantize(Decimal("0.01"))

    # Calcular fecha límite para descuento
    early_payment_date = None
    if early_payment_discount_days > 0:
        early_payment_date = issue_date + timedelta(days=early_payment_discount_days)

    payable = Payable(
        company=company,
        branch=branch,
        party=party,
        reference_type=reference_type,
        reference_id=reference_id,
        currency=currency,
        principal_amount=principal_amount,
        issue_date=issue_date,
        due_date=due_date,
        supplier_invoice_number=supplier_invoice_number,
        supplier_invoice_date=supplier_invoice_date or issue_date,
        early_payment_discount_rate=early_payment_discount_rate,
        early_payment_discount_days=early_payment_discount_days,
        early_payment_discount_date=early_payment_date,
        withholding_tax_rate=withholding_tax_rate,
        withholding_tax_amount=withholding_amount,
        created_by=created_by,
        metadata_json=metadata or {},
        accounting_status=AccountingStatus.PENDING_RULESET,
    )

    payable.full_clean()
    payable.save()

    # Publicar evento
    _publish_payable_created_event(payable)

    return payable


def _publish_payable_created_event(payable: Payable):
    """Publica evento PORTFOLIO.PayableCreated"""
    publish_outbox_event(
        source_module="PORTFOLIO",
        event_type="PayableCreated",
        company=payable.company,
        branch=payable.branch,
        payload={
            "payable_id": str(payable.obligation_id),
            "party_id": payable.party_id,
            "principal_amount": str(payable.principal_amount),
            "currency": payable.currency,
            "issue_date": payable.issue_date.isoformat(),
            "due_date": payable.due_date.isoformat(),
            "reference_type": payable.reference_type,
            "reference_id": payable.reference_id,
            "supplier_invoice_number": payable.supplier_invoice_number,
            "withholding_tax_amount": str(payable.withholding_tax_amount),
        }
    )


# ============================================================================
# CREDIT SERVICES
# ============================================================================

def create_credit(
    company,
    credit_type: str,
    lender_party,
    borrower_party,
    approved_amount: Decimal,
    currency: str,
    interest_rate: Decimal,
    term_months: int,
    maturity_date: date,
    branch=None,
    guarantor_party=None,
    interest_calculation_method: str = "SIMPLE",
    payment_frequency: str = "MONTHLY",
    grace_period_months: int = 0,
    collateral_type: str = "",
    collateral_value: Optional[Decimal] = None,
    contract_number: str = "",
    created_by=None,
    metadata: Optional[Dict] = None,
) -> Credit:
    """
    Crea un Crédito

    Puede ser crédito otorgado o recibido.
    """
    if approved_amount <= 0:
        raise PortfolioDomainError(
            "INVALID_AMOUNT",
            f"Approved amount must be positive: {approved_amount}"
        )

    if interest_rate < 0:
        raise PortfolioDomainError(
            "INVALID_RATE",
            f"Interest rate cannot be negative: {interest_rate}"
        )

    if lender_party.id == borrower_party.id:
        raise PortfolioDomainError(
            "INVALID_PARTIES",
            "Lender and borrower cannot be the same party"
        )

    # Fecha de aprobación es hoy
    approval_date = timezone.localdate()

    credit = Credit(
        company=company,
        branch=branch,
        party=borrower_party,  # Para queries, party es el borrower
        reference_type="CREDIT_CONTRACT",
        reference_id=0,  # Se actualizará cuando haya contrato
        currency=currency,
        principal_amount=approved_amount,  # Principal es el approved_amount
        issue_date=approval_date,
        due_date=maturity_date,
        # Credit-specific
        credit_type=credit_type,
        credit_status=CreditStatus.APPROVED,
        lender_party=lender_party,
        borrower_party=borrower_party,
        guarantor_party=guarantor_party,
        approved_amount=approved_amount,
        disbursed_amount=Decimal("0.00"),
        interest_rate=interest_rate,
        interest_calculation_method=interest_calculation_method,
        payment_frequency=payment_frequency,
        term_months=term_months,
        grace_period_months=grace_period_months,
        approval_date=approval_date,
        maturity_date=maturity_date,
        collateral_type=collateral_type,
        collateral_value=collateral_value,
        contract_number=contract_number,
        created_by=created_by,
        metadata_json=metadata or {},
        accounting_status=AccountingStatus.PENDING_RULESET,
    )

    credit.full_clean()
    credit.save()

    # Publicar evento
    publish_outbox_event(
        source_module="PORTFOLIO",
        event_type="CreditApproved",
        company=credit.company,
        branch=credit.branch,
        payload={
            "credit_id": str(credit.obligation_id),
            "credit_type": credit_type,
            "lender_party_id": lender_party.id,
            "borrower_party_id": borrower_party.id,
            "approved_amount": str(approved_amount),
            "currency": currency,
            "interest_rate": str(interest_rate),
            "term_months": term_months,
        }
    )

    return credit


def disburse_credit(
    credit: Credit,
    disbursed_amount: Decimal,
    disbursement_date: date,
    disbursed_by,
) -> Credit:
    """
    Desembolsa un crédito

    Registra el desembolso y actualiza estado.
    """
    if credit.credit_status not in (CreditStatus.APPROVED, CreditStatus.DISBURSED):
        raise PortfolioDomainError(
            "INVALID_STATUS",
            f"Cannot disburse credit in status {credit.credit_status}"
        )

    if disbursed_amount <= 0:
        raise PortfolioDomainError(
            "INVALID_AMOUNT",
            f"Disbursement amount must be positive: {disbursed_amount}"
        )

    new_total = credit.disbursed_amount + disbursed_amount
    if new_total > credit.approved_amount:
        raise PortfolioDomainError(
            "EXCEEDS_APPROVED",
            f"Total disbursed ({new_total}) would exceed approved ({credit.approved_amount})"
        )

    credit.disbursed_amount = new_total
    credit.credit_status = CreditStatus.DISBURSED if new_total == credit.approved_amount else CreditStatus.ACTIVE

    if not credit.disbursement_date:
        credit.disbursement_date = disbursement_date

    credit.metadata_json.setdefault("disbursements", []).append({
        "date": disbursement_date.isoformat(),
        "amount": str(disbursed_amount),
        "disbursed_by_id": disbursed_by.id if disbursed_by else None,
    })

    credit.save()

    # Publicar evento
    publish_outbox_event(
        source_module="PORTFOLIO",
        event_type="CreditDisbursed",
        company=credit.company,
        branch=credit.branch,
        payload={
            "credit_id": str(credit.obligation_id),
            "disbursed_amount": str(disbursed_amount),
            "total_disbursed": str(credit.disbursed_amount),
            "disbursement_date": disbursement_date.isoformat(),
            "borrower_party_id": credit.borrower_party_id,
            "lender_party_id": credit.lender_party_id,
        }
    )

    return credit


# ============================================================================
# PAYMENT ALLOCATION SERVICES
# ============================================================================

def allocate_payment_to_obligation(
    payment_intent,
    obligation: Obligation,
    allocated_amount: Decimal,
    allocation_date: date,
    created_by,
    allocation_breakdown: Optional[Dict[str, Decimal]] = None,
    exchange_rate: Optional[Decimal] = None,
) -> PaymentAllocation:
    """
    Aplica un pago a una obligación

    Lógica híbrida: puede ser llamada manualmente o por proceso automático.

    Args:
        payment_intent: PaymentIntent capturado
        obligation: Receivable, Payable o Credit
        allocated_amount: Monto a aplicar
        allocation_date: Fecha de aplicación
        created_by: Usuario que aplica (o sistema)
        allocation_breakdown: Opcional, dict con 'principal', 'interest', 'fee', 'penalty'
        exchange_rate: Opcional, tasa de cambio si monedas difieren
    """
    # Validar payment_intent
    if payment_intent.status != "CAPTURED":
        raise PortfolioDomainError(
            "PAYMENT_NOT_CAPTURED",
            f"Payment {payment_intent.payment_id} must be CAPTURED to allocate"
        )

    # Validar monto
    if allocated_amount <= 0:
        raise PortfolioDomainError(
            "INVALID_AMOUNT",
            f"Allocated amount must be positive: {allocated_amount}"
        )

    if allocated_amount > payment_intent.amount:
        raise PortfolioDomainError(
            "EXCEEDS_PAYMENT",
            f"Allocated amount ({allocated_amount}) exceeds payment amount ({payment_intent.amount})"
        )

    if allocated_amount > obligation.outstanding_amount:
        raise PortfolioDomainError(
            "EXCEEDS_OUTSTANDING",
            f"Allocated amount ({allocated_amount}) exceeds outstanding ({obligation.outstanding_amount})"
        )

    # Validar moneda
    if payment_intent.currency != obligation.currency and not exchange_rate:
        raise PortfolioDomainError(
            "CURRENCY_MISMATCH",
            f"Payment currency ({payment_intent.currency}) differs from obligation ({obligation.currency}), exchange_rate required"
        )

    # Desglose del allocation
    if allocation_breakdown:
        principal_applied = allocation_breakdown.get("principal", Decimal("0.00"))
        interest_applied = allocation_breakdown.get("interest", Decimal("0.00"))
        fee_applied = allocation_breakdown.get("fee", Decimal("0.00"))
        penalty_applied = allocation_breakdown.get("penalty", Decimal("0.00"))
    else:
        # Default: aplicar a principal primero, luego interés, luego fees, luego penalties
        remaining = allocated_amount
        penalty_applied = min(remaining, obligation.penalty_amount - Decimal("0.00"))  # TODO: track applied per component
        remaining -= penalty_applied
        interest_applied = min(remaining, obligation.interest_amount)
        remaining -= interest_applied
        fee_applied = min(remaining, obligation.fee_amount)
        remaining -= fee_applied
        principal_applied = remaining

    # Crear allocation
    content_type = ContentType.objects.get_for_model(obligation)

    allocation = PaymentAllocation(
        company=payment_intent.company,
        payment_intent=payment_intent,
        obligation_content_type=content_type,
        obligation_object_id=obligation.id,
        status=AllocationStatus.APPLIED,
        allocated_amount=allocated_amount,
        currency=payment_intent.currency,
        principal_applied=principal_applied,
        interest_applied=interest_applied,
        fee_applied=fee_applied,
        penalty_applied=penalty_applied,
        exchange_rate=exchange_rate,
        allocation_date=allocation_date,
        applied_at=timezone.now(),
        created_by=created_by,
    )

    allocation.full_clean()

    with transaction.atomic():
        allocation.save()

        # Actualizar obligation
        obligation.allocated_amount += allocated_amount
        obligation.last_payment_date = allocation_date

        # Actualizar status
        if obligation.allocated_amount >= obligation.total_amount:
            obligation.status = ObligationStatus.PAID
            obligation.paid_date = allocation_date
        elif obligation.allocated_amount > 0:
            obligation.status = ObligationStatus.PARTIAL

        obligation.save()

    # Publicar evento según tipo
    event_type = _get_allocation_event_type(obligation)
    publish_outbox_event(
        source_module="PORTFOLIO",
        event_type=event_type,
        company=payment_intent.company,
        branch=payment_intent.branch,
        payload={
            "allocation_id": str(allocation.allocation_id),
            "payment_id": str(payment_intent.payment_id),
            "obligation_id": str(obligation.obligation_id),
            "obligation_type": obligation.obligation_type,
            "allocated_amount": str(allocated_amount),
            "principal_applied": str(principal_applied),
            "interest_applied": str(interest_applied),
            "party_id": obligation.party_id,
        }
    )

    return allocation


def _get_allocation_event_type(obligation: Obligation) -> str:
    """Retorna evento según tipo de obligación"""
    if isinstance(obligation, Receivable):
        return "ReceivableAllocated"
    elif isinstance(obligation, Payable):
        return "PayableAllocated"
    elif isinstance(obligation, Credit):
        return "CreditRepaymentReceived"
    return "ObligationAllocated"


def auto_allocate_payment(
    payment_intent,
    party,
    created_by=None,
) -> List[PaymentAllocation]:
    """
    Aplica un pago automáticamente a obligaciones pendientes

    Usa estrategia FIFO por defecto (configurable vía PortfolioSettings).
    """
    settings = PortfolioSettings.get_or_create_for_company(payment_intent.company)

    if not settings.auto_allocate_payments:
        raise PortfolioDomainError(
            "AUTO_ALLOCATION_DISABLED",
            f"Auto allocation is disabled for company {payment_intent.company}"
        )

    # Buscar obligaciones pendientes del party
    # TODO: Determinar si es Receivable o Payable según dirección del pago
    # Por ahora asumimos que son Receivables (cobros)
    pending_obligations = Receivable.objects.filter(
        company=payment_intent.company,
        party=party,
        status__in=[ObligationStatus.PENDING, ObligationStatus.PARTIAL, ObligationStatus.OVERDUE],
        currency=payment_intent.currency,
    ).order_by("due_date", "issue_date")  # FIFO

    allocations = []
    remaining_amount = payment_intent.amount
    allocation_date = timezone.localdate()

    for obligation in pending_obligations:
        if remaining_amount <= 0:
            break

        outstanding = obligation.outstanding_amount
        to_allocate = min(remaining_amount, outstanding)

        allocation = allocate_payment_to_obligation(
            payment_intent=payment_intent,
            obligation=obligation,
            allocated_amount=to_allocate,
            allocation_date=allocation_date,
            created_by=created_by,
        )

        allocations.append(allocation)
        remaining_amount -= to_allocate

    return allocations


# ============================================================================
# INTEREST ACCRUAL SERVICES
# ============================================================================

def accrue_interest_for_credit(
    credit: Credit,
    accrual_date: date,
    period_start: date,
    period_end: date,
) -> Optional[InterestAccrual]:
    """
    Calcula y registra devengo de interés para un crédito

    Diseñado para ser llamado por comando periódico.
    """
    if credit.credit_status not in (CreditStatus.DISBURSED, CreditStatus.ACTIVE):
        return None

    # Verificar que no exista ya
    existing = InterestAccrual.objects.filter(
        credit=credit,
        accrual_date=accrual_date
    ).first()

    if existing:
        return existing

    # Calcular interés
    principal_balance = credit.disbursed_amount - credit.allocated_amount
    if principal_balance <= 0:
        return None

    days_in_period = (period_end - period_start).days + 1
    annual_rate = credit.interest_rate / Decimal("100.00")

    if credit.interest_calculation_method == "SIMPLE":
        # Interés simple: P * r * t
        daily_rate = annual_rate / Decimal("365.00")
        accrued = (principal_balance * daily_rate * Decimal(str(days_in_period))).quantize(Decimal("0.01"))
    elif credit.interest_calculation_method == "COMPOUND":
        # Interés compuesto: P * ((1 + r)^t - 1)
        # Simplificado para períodos cortos
        daily_rate = annual_rate / Decimal("365.00")
        accrued = (principal_balance * daily_rate * Decimal(str(days_in_period))).quantize(Decimal("0.01"))
    else:
        # Flat rate
        accrued = (principal_balance * annual_rate / Decimal("12.00")).quantize(Decimal("0.01"))

    accrual = InterestAccrual(
        credit=credit,
        accrual_date=accrual_date,
        period_start=period_start,
        period_end=period_end,
        days_in_period=days_in_period,
        principal_balance=principal_balance,
        interest_rate_applied=credit.interest_rate,
        accrued_interest=accrued,
        calculation_method=credit.interest_calculation_method,
        metadata_json={
            "calculation_details": {
                "principal": str(principal_balance),
                "rate": str(credit.interest_rate),
                "days": days_in_period,
                "method": credit.interest_calculation_method,
            }
        }
    )

    accrual.save()

    # Actualizar interest_amount en el crédito
    credit.interest_amount += accrued
    credit.save()

    # Publicar evento
    publish_outbox_event(
        source_module="PORTFOLIO",
        event_type="InterestAccrued",
        company=credit.company,
        branch=credit.branch,
        payload={
            "credit_id": str(credit.obligation_id),
            "accrual_id": str(accrual.accrual_id),
            "accrued_interest": str(accrued),
            "principal_balance": str(principal_balance),
            "accrual_date": accrual_date.isoformat(),
            "borrower_party_id": credit.borrower_party_id,
        }
    )

    return accrual


def update_aging_for_obligations(company, as_of_date: Optional[date] = None):
    """
    Actualiza aging de todas las obligaciones de una company

    Diseñado para ser llamado por comando diario.
    """
    if not as_of_date:
        as_of_date = timezone.localdate()

    # Actualizar Receivables
    for receivable in Receivable.objects.filter(company=company, status__in=[
        ObligationStatus.PENDING,
        ObligationStatus.PARTIAL,
        ObligationStatus.OVERDUE,
    ]):
        receivable.update_aging()
        receivable.save(update_fields=["days_overdue", "aging_bucket", "status", "updated_at"])

    # Actualizar Payables
    for payable in Payable.objects.filter(company=company, status__in=[
        ObligationStatus.PENDING,
        ObligationStatus.PARTIAL,
        ObligationStatus.OVERDUE,
    ]):
        payable.update_aging()
        payable.save(update_fields=["days_overdue", "aging_bucket", "status", "updated_at"])

    # Actualizar Credits
    for credit in Credit.objects.filter(company=company, credit_status__in=[
        CreditStatus.DISBURSED,
        CreditStatus.ACTIVE,
    ]):
        credit.update_aging()
        credit.save(update_fields=["days_overdue", "aging_bucket", "status", "days_past_due", "updated_at"])
