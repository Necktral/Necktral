# Financial Portfolio Kernel

Kernel para gestión de Cuentas por Cobrar (CxC), Cuentas por Pagar (CxP) y Créditos.

## Características

### Diseño Flexible

El Portfolio Kernel está diseñado con **máxima flexibilidad** para permitir ajustes posteriores sin cambiar código:

- **Múltiples estrategias de allocation**: Auto (FIFO) o Manual
- **Múltiples frecuencias de interés**: Diario, Mensual, o Configurable
- **Múltiples modos de integración**: Síncrono o Asíncrono
- **Aging buckets configurables**: Por company
- **Gates configurables**: Bloqueante, Warning, o Disabled

### Modelos

#### Obligation (Base Abstracta)
- Base para todas las obligaciones financieras
- Campos comunes: montos, fechas, aging, accounting status
- Propiedades calculadas: `total_amount`, `outstanding_amount`, `is_overdue`

#### Receivable (CxC - Cuentas por Cobrar)
- Hereda de Obligation
- Campos específicos: `invoice_number`, `credit_limit`, `credit_days`
- Gestión de cobro: `risk_rating`, `collection_priority`, `collector_user`

#### Payable (CxP - Cuentas por Pagar)
- Hereda de Obligation
- Campos específicos: `supplier_invoice_number`, descuentos por pronto pago
- Retenciones: `withholding_tax_rate`, `withholding_tax_amount`
- Gestión de pago: `payment_priority`, `approver_user`

#### Credit (Créditos Financieros)
- Hereda de Obligation
- Partes: `lender_party`, `borrower_party`, `guarantor_party`
- Términos: tasa de interés, plazo, frecuencia de pago, período de gracia
- Garantías: `collateral_type`, `collateral_value`
- Reestructuraciones: `restructured_from`, `restructure_count`

#### PaymentAllocation
- Vincula pagos (`PaymentIntent`) con obligaciones
- Desglose: `principal_applied`, `interest_applied`, `fee_applied`, `penalty_applied`
- Conversión de moneda: `exchange_rate`

#### InterestAccrual
- Devengo de intereses en créditos
- Cálculo por período: diario o mensual
- Capitalización opcional: `is_capitalized`

#### PortfolioSettings
- Configuración por Company
- Controla todo el comportamiento del kernel sin cambiar código

## API Endpoints

### Receivables (CxC)
```
GET    /api/portfolio/receivables/          # Listar
POST   /api/portfolio/receivables/          # Crear
GET    /api/portfolio/receivables/{id}/     # Detalle
PATCH  /api/portfolio/receivables/{id}/     # Actualizar
DELETE /api/portfolio/receivables/{id}/     # Eliminar
POST   /api/portfolio/receivables/{id}/adjust/   # Ajustar monto
POST   /api/portfolio/receivables/{id}/writeoff/ # Castigar
```

### Payables (CxP)
```
GET    /api/portfolio/payables/             # Listar
POST   /api/portfolio/payables/             # Crear
GET    /api/portfolio/payables/{id}/        # Detalle
PATCH  /api/portfolio/payables/{id}/        # Actualizar
DELETE /api/portfolio/payables/{id}/        # Eliminar
```

### Credits
```
GET    /api/portfolio/credits/              # Listar
POST   /api/portfolio/credits/              # Crear
GET    /api/portfolio/credits/{id}/         # Detalle
PATCH  /api/portfolio/credits/{id}/         # Actualizar
DELETE /api/portfolio/credits/{id}/         # Eliminar
POST   /api/portfolio/credits/{id}/disburse/ # Desembolsar
```

### Payment Allocations
```
GET    /api/portfolio/allocations/          # Listar
POST   /api/portfolio/allocations/          # Crear (aplicar pago)
GET    /api/portfolio/allocations/{id}/     # Detalle
```

### Interest Accruals
```
GET    /api/portfolio/interest-accruals/    # Listar (read-only)
GET    /api/portfolio/interest-accruals/{id}/ # Detalle
```

### Settings
```
GET    /api/portfolio/settings/             # Listar
PATCH  /api/portfolio/settings/{company_id}/ # Actualizar
```

## Servicios

### Receivables
```python
from apps.kernels.portfolio import services

# Crear CxC
receivable = services.create_receivable(
    company=company,
    party=customer_party,
    reference_type="BILLING_DOCUMENT",
    reference_id=invoice.id,
    principal_amount=Decimal("1000.00"),
    currency="NIO",
    issue_date=date.today(),
    due_date=date.today() + timedelta(days=30),
    invoice_number="F001-123",
)

# Ajustar CxC
adjusted = services.adjust_receivable(
    receivable=receivable,
    adjustment_amount=Decimal("-50.00"),  # descuento
    reason="Descuento por pronto pago",
    adjusted_by=user,
)

# Castigar CxC
written_off = services.write_off_receivable(
    receivable=receivable,
    reason="Cliente declarado en quiebra",
    approved_by=manager,
)
```

### Payables
```python
# Crear CxP
payable = services.create_payable(
    company=company,
    party=supplier_party,
    reference_type="PURCHASE_DOCUMENT",
    reference_id=purchase_doc.id,
    principal_amount=Decimal("5000.00"),
    currency="USD",
    issue_date=date.today(),
    due_date=date.today() + timedelta(days=45),
    supplier_invoice_number="PROV-456",
    withholding_tax_rate=Decimal("2.00"),  # 2%
)
```

### Credits
```python
# Crear crédito
credit = services.create_credit(
    company=company,
    credit_type="TERM_LOAN",
    lender_party=bank_party,
    borrower_party=company_party,
    approved_amount=Decimal("100000.00"),
    currency="NIO",
    interest_rate=Decimal("12.50"),  # 12.5% anual
    term_months=24,
    maturity_date=date.today() + timedelta(days=730),
    contract_number="LOAN-2026-001",
)

# Desembolsar
disbursed = services.disburse_credit(
    credit=credit,
    disbursed_amount=Decimal("50000.00"),
    disbursement_date=date.today(),
    disbursed_by=user,
)
```

### Payment Allocation
```python
# Aplicar pago a obligación (manual)
allocation = services.allocate_payment_to_obligation(
    payment_intent=payment,  # PaymentIntent en estado CAPTURED
    obligation=receivable,
    allocated_amount=Decimal("500.00"),
    allocation_date=date.today(),
    created_by=user,
)

# Aplicar pago automáticamente (FIFO)
allocations = services.auto_allocate_payment(
    payment_intent=payment,
    party=customer_party,
    created_by=None,  # sistema
)
```

### Interest Accrual
```python
# Devengar interés
accrual = services.accrue_interest_for_credit(
    credit=credit,
    accrual_date=date.today(),
    period_start=date(2026, 5, 1),
    period_end=date(2026, 5, 31),
)
```

## Management Commands

### Devengo de Intereses
```bash
# Company específica
python manage.py accrue_credit_interest --company-id=1

# Todas las companies
python manage.py accrue_credit_interest --all-companies

# Dry run
python manage.py accrue_credit_interest --company-id=1 --dry-run

# Fecha específica
python manage.py accrue_credit_interest --company-id=1 --accrual-date=2026-05-31
```

### Actualización de Aging
```bash
# Company específica
python manage.py update_portfolio_aging --company-id=1

# Todas las companies
python manage.py update_portfolio_aging --all-companies

# As-of date específica
python manage.py update_portfolio_aging --company-id=1 --as-of-date=2026-05-30
```

## Integración con Otros Kernels

### Billing → Receivables (Automática)
Cuando se emite una factura a crédito, automáticamente se crea una CxC:

```python
# En apps/kernels/facturacion/services.py
from apps.kernels.portfolio import services as portfolio_services

def post_billing_document(doc, user):
    # ... código actual ...

    if doc.payment_method == "CREDIT" and settings.sync_with_billing:
        receivable = portfolio_services.create_receivable(
            company=doc.company,
            party=doc.customer_party,
            reference_type="BILLING_DOCUMENT",
            reference_id=doc.id,
            principal_amount=doc.total,
            currency=doc.currency,
            issue_date=doc.issued_at.date(),
            due_date=doc.issued_at.date() + timedelta(days=30),
            invoice_number=f"{doc.series}-{doc.number}",
            created_by=user,
        )
```

### Procurement → Payables (Automática)
Cuando se recibe factura de proveedor, automáticamente se crea una CxP:

```python
# En apps/modulos/compras/services.py
from apps.kernels.portfolio import services as portfolio_services

def post_purchase_document(doc, user):
    # ... código actual ...

    if doc.doc_type == "SUPPLIER_INVOICE" and settings.sync_with_procurement:
        payable = portfolio_services.create_payable(
            company=doc.company,
            party=doc.supplier_party,
            reference_type="PURCHASE_DOCUMENT",
            reference_id=doc.id,
            principal_amount=doc.total,
            currency=doc.currency,
            issue_date=doc.posted_at.date(),
            due_date=doc.posted_at.date() + timedelta(days=45),
            supplier_invoice_number=doc.external_ref,
            created_by=user,
        )
```

### Payments → Allocation (Manual o Auto)
Cuando se captura un pago, se puede aplicar automáticamente o manualmente:

```python
# En apps/kernels/payments/services.py
from apps.kernels.portfolio import services as portfolio_services
from apps.kernels.portfolio.models import PortfolioSettings

def on_payment_captured(payment_intent):
    settings = PortfolioSettings.get_or_create_for_company(payment_intent.company)

    if settings.auto_allocate_payments:
        # Auto-aplicar (FIFO)
        allocations = portfolio_services.auto_allocate_payment(
            payment_intent=payment_intent,
            party=payment_intent.party,  # determinar party del pago
            created_by=None,
        )
    # else: esperar aplicación manual por API
```

## Eventos Económicos

El Portfolio Kernel emite eventos para integración con Shadow Ledger:

- `PORTFOLIO.ReceivableCreated` - Al crear CxC
- `PORTFOLIO.ReceivableAdjusted` - Al ajustar CxC
- `PORTFOLIO.ReceivableAllocated` - Al aplicar pago a CxC
- `PORTFOLIO.ReceivableWrittenOff` - Al castigar CxC
- `PORTFOLIO.PayableCreated` - Al crear CxP
- `PORTFOLIO.PayableAllocated` - Al aplicar pago a CxP
- `PORTFOLIO.CreditApproved` - Al aprobar crédito
- `PORTFOLIO.CreditDisbursed` - Al desembolsar crédito
- `PORTFOLIO.CreditRepaymentReceived` - Al recibir pago de crédito
- `PORTFOLIO.InterestAccrued` - Al devengar interés
- `PORTFOLIO.InterestCapitalized` - Al capitalizar interés

## Configuración (PortfolioSettings)

Cada Company puede tener su propia configuración:

```python
from apps.kernels.portfolio.models import PortfolioSettings

settings = PortfolioSettings.get_or_create_for_company(company)

# Modificar configuración
settings.auto_allocate_payments = True  # Aplicar pagos automáticamente
settings.allocation_strategy = "FIFO"   # Estrategia FIFO
settings.interest_accrual_frequency = "MONTHLY"  # Devengo mensual
settings.auto_capitalize_interest = False  # No capitalizar automáticamente
settings.auto_writeoff_enabled = False  # No castigo automático
settings.auto_writeoff_days = 365  # Castigo después de 365 días
settings.gate_mode = "BLOCKING"  # Gates bloquean cierre
settings.functional_currency = "NIO"  # Moneda funcional
settings.auto_convert_currency = False  # No conversión automática
settings.sync_with_billing = True  # Crear CxC desde facturas
settings.sync_with_procurement = True  # Crear CxP desde compras
settings.integration_mode = "ASYNC"  # Integración asincrónica
settings.aging_buckets_json = {
    "0": "CURRENT",
    "30": "0-30",
    "60": "31-60",
    "90": "61-90",
    "120": "91-120",
    "999": "120+"
}
settings.save()
```

## Admin Interface

El kernel incluye una interfaz de administración completa:

- `/admin/portfolio/receivable/` - Gestión de CxC
- `/admin/portfolio/payable/` - Gestión de CxP
- `/admin/portfolio/credit/` - Gestión de Créditos
- `/admin/portfolio/paymentallocation/` - Aplicaciones de pago
- `/admin/portfolio/interestaccrual/` - Devengos de interés
- `/admin/portfolio/portfoliosettings/` - Configuración

## Próximos Pasos

1. **Crear migración**: `python manage.py makemigrations portfolio`
2. **Aplicar migración**: `python manage.py migrate portfolio`
3. **Configurar company**: Crear PortfolioSettings para cada company
4. **Integrar con Billing**: Modificar `post_billing_document()` para crear CxC
5. **Integrar con Procurement**: Modificar `post_purchase_document()` para crear CxP
6. **Configurar cron jobs**: Para `accrue_credit_interest` y `update_portfolio_aging`
7. **Definir PostingRuleSets**: Para eventos Portfolio en Shadow Ledger

## Notas Importantes

- ✅ **Prerequisito cumplido**: Party/Counterparty existe y está integrado
- ✅ **Diseño flexible**: Múltiples opciones configurables sin cambiar código
- ✅ **Listo para refinamiento**: Sistema funcional que puede ajustarse con gerencia
- ⚠️ **Requiere PostgreSQL**: No funciona con SQLite (por constraints complejos)
- ⚠️ **Backfill cuidadoso**: Si tienes datos históricos, planificar migración con cuidado

## Soporte

Para dudas o ajustes, revisar el análisis profundo original que documenta todas las decisiones de diseño y opciones disponibles.
