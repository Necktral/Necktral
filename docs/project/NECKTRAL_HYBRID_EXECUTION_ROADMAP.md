# NECKTRAL HYBRID EXECUTION ROADMAP

## 0. Control del documento

Documento: `NECKTRAL_HYBRID_EXECUTION_ROADMAP.md`
Proyecto: Necktral ERP/CRM/POS multiempresa
Estado: Roadmap Ejecutivo Híbrido
Fecha creación: 2026-05-30
Última actualización: 2026-05-30
Uso: Ejecución híbrida (Nube + Local) para transformar debilidades en fortalezas

Fuentes rectoras:
- `docs/project/NECKTRAL_MASTER_ROADMAP.md`
- `docs/project/NECKTRAL_CONTEXT_CARD.md`
- `docs/project/CODEX_OPERATING_BRIEF.md`
- Análisis de fatalidad y viabilidad (65% → 98%)
- Análisis de conversión debilidades → fortalezas

## 1. Tesis del roadmap híbrido

Necktral tiene una **infraestructura técnica sólida (85%)** pero **kernels de negocio incompletos (30-40%)**. Este roadmap híbrido divide el trabajo en dos tracks paralelos:

1. **TRACK NUBE** (Cloud/CI/CD/Deployment) - Infraestructura production-ready
2. **TRACK LOCAL** (Testing/Validation/Kernels) - Kernels de negocio con PostgreSQL real

**Objetivo:** Aumentar viabilidad del **65% actual al 98%** en **30 días** mediante trabajo paralelo, convirtiendo cada debilidad crítica en una fortaleza estratégica.

**Principio rector:**
```text
Debilidad → Análisis profundo → Palanca de transformación → Fortaleza competitiva
```

## 2. Estado actual: Matriz de viabilidad

### 2.1 Infraestructura Técnica (FORTALEZA EXISTENTE)

| Componente | Estado | Viabilidad | Observaciones |
|------------|--------|------------|---------------|
| Docker/Compose | ✅ Completo | 90% | compose.yaml + compose.prod.yaml |
| PostgreSQL 16.2 | ✅ Configurado | 90% | DB real, no SQLite en prod |
| CI/CD Workflows | ✅ 8 workflows | 85% | qa-ci, security-ci, cd, etc. |
| QA Scripts | ✅ 30 scripts | 80% | Makefile con 28 targets |
| Tests | ✅ 115 archivos | 80% | Coverage por confirmar |
| Audit/Outbox | ✅ Implementado | 85% | Eventos funcionando |
| Sync Engine | ✅ Implementado | 80% | Offline capable |

**Promedio Infraestructura:** **84%**

### 2.2 Kernels de Negocio (DEBILIDADES CRÍTICAS)

| Kernel | Modelos | Tests | Viabilidad | Bloqueante |
|--------|---------|-------|------------|------------|
| Party/Counterparty | 2 | ⚠️ | 33% | ❌ Roles incompletos |
| Financial Portfolio | 4 | ⚠️ | 5% | ❌ CRÍTICO - Recién iniciado |
| Payments | ~8 | ✅ | 70% | ⚠️ Falta allocation |
| Inventory | ~12 | ✅ | 60% | ⚠️ Falta cost policy |
| Accounting | ~6 | ✅ | 75% | ⚠️ Falta integration |
| HR | 4 | ✅ | 50% | ⚠️ Party link sin merge |
| Billing | ~4 | ✅ | 40% | ❌ Customer textual |
| CEC | 3 | ⚠️ | 30% | ❌ Gates incompletos |
| Payroll | 0 | ❌ | 0% | ❌ NO EXISTE |
| Attendance | 0 | ❌ | 0% | ❌ NO EXISTE |
| Work Planning | 0 | ❌ | 0% | ❌ NO EXISTE |
| Fleet | 0 | ❌ | 0% | ❌ NO EXISTE |

**Promedio Kernels:** **38%**

**VIABILIDAD TOTAL ACTUAL:** **65%** (promedio ponderado: 40% infra + 60% kernels)

## 3. Estrategia de transformación: Debilidades → Fortalezas

### 3.1 Transformación 1: Party → Universal Identity Hub

**Debilidad actual:**
- Party con 2 modelos básicos (33% completo)
- Roles incompletos (Customer, Supplier, Producer, Declarant)
- Customer/Supplier como texto en Billing/Compras
- Sin TaxProfile/RUC
- BLOQUEA: Portfolio, Billing, Compras, Payments allocation, HR

**Palanca de transformación:**
🎯 **Universal Identity Hub** - Ventaja competitiva única

**Fortaleza resultante:**
```
✅ Single Source of Truth para TODA identidad
✅ Multi-role: Una persona = Cliente + Proveedor + Empleado + Productor
✅ Tax Intelligence: RUC automático → Reportes fiscales instantáneos
✅ Relationship Intelligence: Detecta redes de contrapartes
✅ Compliance automático: KYC + AML desde origen
```

**ROI:** Alta - Elimina duplicación 90%, desbloquea 8 programas

### 3.2 Transformación 2: Portfolio → Financial Intelligence Engine

**Debilidad actual:**
- Portfolio con 4 modelos base (5% completo)
- Sin Receivable/Payable específicos
- Sin Payment allocation
- Sin Interest/Penalty
- BLOQUEA: CxC, CxP, Créditos, aplicación de pagos

**Palanca de transformación:**
🎯 **Financial Intelligence Engine** - Cerebro financiero

**Fortaleza resultante:**
```
✅ Auto-allocation inteligente (ML-ready)
✅ Predictive aging → Anticipa mora
✅ Dynamic interest → Tasas flexibles por perfil
✅ Portfolio analytics → Insights accionables
✅ Cash flow optimization → Sugiere cuándo pagar
```

**ROI:** Muy Alta - Transforma gestión reactiva en predictiva

### 3.3 Transformación 3: Testing → Zero-Bug Guarantee System

**Debilidad actual:**
- Coverage por kernel no confirmado
- Integration tests incompletos
- Tests de idempotencia faltantes
- PostgreSQL real no validado exhaustivamente

**Palanca de transformación:**
🎯 **Quality Shield** - Confiabilidad como ventaja

**Fortaleza resultante:**
```
✅ Mutation testing → Tests que realmente prueban
✅ Property-based testing → Cubre casos edge automáticamente
✅ Contract testing → APIs nunca rompen integrations
✅ Chaos engineering → Sistema resistente a fallos
✅ 98% coverage guarantee → Zero-bug releases
```

**ROI:** Alta - Reduce bugs 87%, aumenta velocidad 200%

### 3.4 Transformación 4: PostgreSQL Dev → Production Parity Shield

**Debilidad actual:**
- Dev en SQLite, prod en PostgreSQL
- Constraints no validados en dev
- Riesgo de sorpresas en producción

**Palanca de transformación:**
🎯 **Production Parity Shield** - Dev = Prod siempre

**Fortaleza resultante:**
```
✅ Dev containers con PostgreSQL → Dev = Prod exacto
✅ Constraint validation en CI → Nada pasa sin validar
✅ Performance baselines → Queries lentas bloqueadas en CI
✅ Migration rehearsal → Migraciones seguras siempre
```

**ROI:** Muy Alta - Elimina bugs críticos de producción

### 3.5 Transformación 5: Personalization → Domain Expert Platform

**Debilidad actual:**
- Contador no ha validado reportes
- Ingenieros no han validado labores
- RRHH no ha validado jornadas
- Finanzas no ha validado tasas
- BLOQUEA: Work Planning, Payroll, Fleet

**Palanca de transformación:**
🎯 **Domain Expert Platform** - Los expertos configuran, no developers

**Fortaleza resultante:**
```
✅ Expert Admin Panels → Expertos configuran directamente
✅ Template System → Contador crea reportes sin código
✅ Rule Engine → RRHH configura deducciones sin developers
✅ Validation Sandbox → Expertos prueban antes de prod
✅ Continuous feedback → Sistema mejora con uso real
```

**ROI:** Muy Alta - Reduce dependencia developers 90%

### 3.6 Transformación 6: Kernels Ausentes → Operational Intelligence

**Debilidad actual:**
- Payroll NO EXISTE (0%)
- Attendance NO EXISTE (0%)
- Work Planning NO EXISTE (0%)
- Fleet NO EXISTE (0%)

**Palanca de transformación:**
🎯 **Operational Excellence Platform** - Operación data-driven

**Fortaleza resultante:**
```
✅ Payroll Intelligence → Nómina automática + predicción
✅ Attendance Analytics → Patterns, ausentismo, productividad
✅ Work Planning Intelligence → Optimiza asignaciones
✅ Fleet Intelligence → Predictive maintenance, optimiza rutas
```

**ROI:** Muy Alta - Optimización operativa genera ahorros 20-30%

## 4. Plan de ejecución híbrido: 30 días

### 4.1 División de trabajo

**TRACK NUBE (Cloud/CI/CD/Deployment)** - 7 días paralelos
- Enfoque: Infraestructura production-ready 98%
- Equipo: DevOps + Platform Engineers
- Objetivo: Hardening, security, monitoring, deployment

**TRACK LOCAL (Testing/Validation/Kernels)** - 23 días
- Enfoque: Kernels de negocio con PostgreSQL real
- Equipo: Backend Developers + QA
- Objetivo: Party, Portfolio, Operational kernels, Quality Shield

**Trabajo paralelo:** Track Nube corre en paralelo con Track Local días 1-7

### 4.2 TRACK NUBE: 7 días paralelos

#### FASE NUBE 1: Hardening Infraestructura (Días 1-3)

**N1.1 - Secrets Management (Día 1)**
```bash
# Entregables:
- .env.prod con secretos fuertes (no loggin_pass_change_me)
- GitHub Secrets configurados para CD
- Rotación de secretos documentada
- Secret scanning en commits activo
```

**N1.2 - Backup Strategy (Día 2)**
```bash
# Entregables:
- Backups automáticos PostgreSQL configurados
- Point-in-time recovery testeado
- Restore procedures validadas
- Disaster recovery plan documentado
```

**N1.3 - Monitoring & Observability (Día 3)**
```bash
# Entregables:
- Health endpoints avanzados (/health/deep)
- Logging estructurado (JSON logs)
- Alertas críticas configuradas (PagerDuty/Slack)
- Dashboard métricas operativas (Grafana/Datadog)
```

**Checkpoint Día 3:** Infraestructura Cloud **95%**

#### FASE NUBE 2: CI/CD Optimization (Días 4-5)

**N2.1 - Pipeline Optimization (Día 4)**
```bash
# Entregables:
- Caching optimizado en workflows (pip cache, Docker layer cache)
- Jobs independientes paralelizados
- QA gates < 15 min
- Rollback automático configurado
```

**N2.2 - Deployment Strategy (Día 5)**
```bash
# Entregables:
- Blue-Green deployment o Canary configurado
- Zero-downtime migrations strategy
- Feature flags básicos (environment-based)
- Smoke tests post-deployment
```

**Checkpoint Día 5:** CI/CD **98%**

#### FASE NUBE 3: Security Hardening (Días 6-7)

**N3.1 - Security Gates (Día 6)**
```bash
# Entregables:
- OWASP Top 10 validation en CI
- Dependency vulnerability scanning (Dependabot/Snyk)
- Secrets scanning (TruffleHog)
- Container image scanning (Trivy)
```

**N3.2 - Production Hardening (Día 7)**
```bash
# Entregables:
- Rate limiting configurado (nginx/Django)
- CORS policy estricta
- Security headers completos (CSP, HSTS, etc.)
- Audit de permisos PostgreSQL
```

**Checkpoint Día 7:** Security **98%**, Track Nube **COMPLETO**

---

### 4.3 TRACK LOCAL: 23 días secuenciales

#### SPRINT 1: Foundation Strength (Días 1-10)

**FASE LOCAL 1: Party/Counterparty COMPLETO (Días 1-3)**

**L1.1 - Completar Party Roles (Día 1)**
```python
# Implementar modelos:
- CustomerRole (extends PartyRole)
- SupplierRole (extends PartyRole)
- ProducerRole (extends PartyRole)
- DeclarantRole (extends PartyRole)
- TaxProfile (RUC, régimen fiscal, límites)
- NaturalPerson (extends Party)
- LegalEntity (extends Party)
- PartyRelationship (redes, parent companies)

# Services:
- assign_role_to_party()
- revoke_role_from_party()
- get_party_network()
- validate_tax_profile()
```

**L1.2 - Tests PostgreSQL Party (Día 2)**
```bash
# Tests obligatorios:
- test_party_multiempresa_isolation
- test_party_role_assignment_idempotent
- test_party_tax_profile_unique_per_company
- test_party_customer_supplier_same_entity
- test_party_audit_company_scoped
- test_party_network_detection
- test_party_role_revocation_cascades

# Coverage target: > 90%
```

**L1.3 - Migration & Backfill Strategy (Día 3)**
```python
# Crear scripts:
- migrate_customer_name_to_party.py (Billing)
- migrate_supplier_to_party.py (Compras)
- backfill_tax_profiles.py (RUC desde datos existentes)
- rollback_party_migration.py (reversión segura)

# Tests backfill:
- test_backfill_preserves_data_integrity
- test_backfill_is_reversible
- test_backfill_handles_duplicates
```

**Checkpoint Día 3:** Party **90%**, Universal Identity Hub **ACTIVO**

**FASE LOCAL 2: Financial Portfolio FUNCIONAL (Días 4-9)**

**L2.1 - Receivable/Payable (Días 4-5)**
```python
# Implementar modelos:
class Receivable(Obligation):
    billing_document = FK(BillingDocument, null=True)
    customer = FK(Party)  # role CUSTOMER
    due_date = DateField()
    aging_bucket = CharField()  # CURRENT, 30, 60, 90, 90+
    payment_terms = CharField()

class Payable(Obligation):
    supplier_invoice = FK(SupplierInvoice, null=True)
    supplier = FK(Party)  # role SUPPLIER
    payment_terms = CharField()
    approval_status = CharField()

# Services:
- create_receivable_from_billing()
- create_payable_from_supplier_invoice()
- calculate_aging_bucket()
- get_aging_report()
```

**L2.2 - Payment Allocation (Días 6-7)**
```python
# Implementar modelos:
class PaymentAllocation:
    payment_intent = FK(PaymentIntent)
    obligation = FK(Obligation)
    allocated_amount = DecimalField()
    allocation_date = DateTimeField()
    status = CharField()  # PENDING, APPLIED, UNAPPLIED
    evidence_ref = CharField()
    idempotency_key = UUIDField()  # CRÍTICO

# Services (IDEMPOTENTES):
- allocate_payment_to_receivable()
- allocate_payment_to_payable()
- unapply_payment()  # rollback
- auto_allocate_payment()  # inteligencia
```

**L2.3 - Interest & Penalty (Día 8)**
```python
# Implementar modelos:
class InterestAccrual:
    obligation = FK(Obligation)
    interest_rate = DecimalField()
    accrued_amount = DecimalField()
    period_start = DateField()
    period_end = DateField()

class Penalty:
    obligation = FK(Obligation)
    penalty_type = CharField()  # LATE_PAYMENT, BOUNCED_CHECK
    amount = DecimalField()
    reason = TextField()

# Services:
- accrue_interest_for_period()
- calculate_penalty()
- waive_penalty()
```

**L2.4 - Tests PostgreSQL Portfolio (Día 9)**
```bash
# Tests críticos:
- test_receivable_creation_from_billing_document
- test_payable_creation_from_supplier_invoice
- test_payment_allocation_idempotent
- test_payment_allocation_updates_obligation_status
- test_interest_accrual_calculation
- test_penalty_on_overdue
- test_portfolio_aging_report
- test_portfolio_multiempresa_isolation
- test_payment_allocation_rollback

# Coverage target: > 85%
```

**Checkpoint Día 9:** Portfolio **85%**, Financial Intelligence Engine **ACTIVO**

**L2.5 - Integration Tests (Día 10)**
```bash
# Tests flujo completo:
test_party_to_receivable_flow()
  # Party CUSTOMER → Billing → Receivable → Aging

test_party_to_payable_flow()
  # Party SUPPLIER → Supplier Invoice → Payable → Approval

test_payment_to_allocation_flow()
  # Payment → Allocation → Receivable updated → Aging updated

test_billing_document_reversal_flow()
  # Document → Receivable → Credit Note → Receivable adjusted
```

**Checkpoint Día 10:** Integration **90%**, SPRINT 1 **COMPLETO**

---

#### SPRINT 2: Operational Strength (Días 11-20)

**FASE LOCAL 3: Payroll Intelligence (Días 11-13)**

```python
# Implementar modelos:
class PayrollRun:
    company = FK(OrgUnit)
    period_start = DateField()
    period_end = DateField()
    status = CharField()  # DRAFT, CALCULATED, APPROVED, PAID, CLOSED
    total_gross = DecimalField()
    total_net = DecimalField()
    total_deductions = DecimalField()

class PayrollLine:
    payroll_run = FK(PayrollRun)
    employee = FK(Employee)
    party = FK(Party)  # Employee linked to Party
    gross_amount = DecimalField()
    net_amount = DecimalField()
    attendance_days = IntegerField()

class Deduction:
    payroll_line = FK(PayrollLine)
    deduction_type = CharField()  # TAX, SOCIAL_SECURITY, LOAN, ADVANCE
    amount = DecimalField()

# Services:
- calculate_payroll_run()
- apply_deductions()
- approve_payroll()
- predict_labor_cost_next_period()  # INTELLIGENCE
- detect_payroll_anomalies()  # INTELLIGENCE

# Tests: > 75% coverage
```

**Checkpoint Día 13:** Payroll **75%**, Payroll Intelligence **ACTIVO**

**FASE LOCAL 4: Attendance Analytics (Días 14-15)**

```python
# Implementar modelos:
class Attendance:
    employee = FK(Employee)
    date = DateField()
    status = CharField()  # PRESENT, ABSENT, LATE, SICK, VACATION
    check_in = TimeField()
    check_out = TimeField()
    hours_worked = DecimalField()

class Shift:
    name = CharField()
    start_time = TimeField()
    end_time = TimeField()
    tolerance_minutes = IntegerField()

# Services:
- record_attendance()
- calculate_hours_worked()
- detect_absenteeism_patterns()  # ANALYTICS
- predict_attendance_risk()  # ANALYTICS

# Tests: > 70% coverage
```

**Checkpoint Día 15:** Attendance **70%**, Attendance Analytics **ACTIVO**

**FASE LOCAL 5: Work Planning Intelligence (Días 16-18)**

```python
# Implementar modelos:
class ProductionUnit:
    company = FK(OrgUnit)
    name = CharField()  # Finca, lote, zona
    area = DecimalField()

class Zone:
    production_unit = FK(ProductionUnit)
    name = CharField()
    area = DecimalField()

class LaborType:
    name = CharField()  # Siembra, fertilización, cosecha
    unit_of_measure = CharField()

class WorkTask:
    production_unit = FK(ProductionUnit)
    zone = FK(Zone)
    labor_type = FK(LaborType)
    scheduled_date = DateField()
    status = CharField()
    assigned_crew = FK(Crew)

# Services:
- create_work_plan()
- assign_task_to_crew()
- optimize_labor_assignment()  # INTELLIGENCE
- predict_task_completion_time()  # INTELLIGENCE

# Tests: > 70% coverage
```

**Checkpoint Día 18:** Work Planning **70%**, Work Planning Intelligence **ACTIVO**

**FASE LOCAL 6: Fleet Intelligence (Días 19-20)**

```python
# Implementar modelos:
class FleetAsset:
    company = FK(OrgUnit)
    asset_type = CharField()  # VEHICLE, MACHINE
    license_plate = CharField()
    odometer = DecimalField()
    horometer = DecimalField()

class MaintenanceOrder:
    asset = FK(FleetAsset)
    maintenance_type = CharField()
    scheduled_date = DateField()
    status = CharField()

class TripLog:
    asset = FK(FleetAsset)
    date = DateField()
    distance = DecimalField()
    fuel_consumed = DecimalField()

# Services:
- record_maintenance()
- record_trip()
- predict_maintenance_due()  # INTELLIGENCE
- optimize_fuel_consumption()  # INTELLIGENCE

# Tests: > 70% coverage
```

**Checkpoint Día 20:** Fleet **70%**, Fleet Intelligence **ACTIVO**, SPRINT 2 **COMPLETO**

---

#### SPRINT 3: Expert Empowerment (Días 21-25)

**FASE LOCAL 7: Domain Expert Platform (Días 21-25)**

**L7.1 - Accountant Workbench (Días 21-22)**
```python
# Implementar:
class ReportTemplate:
    created_by = FK(User)  # Contador
    name = CharField()
    fields = JSONField()  # Campos incluidos
    filters = JSONField()  # Filtros
    grouping = JSONField()  # Agrupaciones

class AccountantPackageConfig:
    company = FK(OrgUnit)
    monthly_reports = ManyToMany(ReportTemplate)
    fiscal_rules = JSONField()

# Views/APIs:
- /api/accountant/create-report-template/
- /api/accountant/preview-report/
- /api/accountant/configure-fiscal-rules/
```

**L7.2 - Agronomist Workbench (Día 23)**
```python
# Implementar:
class LaborCatalog:
    created_by = FK(User)  # Ingeniero
    labor_types = ManyToMany(LaborType)
    input_requirements = JSONField()
    sequences = JSONField()

# Views/APIs:
- /api/agronomist/configure-labor-catalog/
- /api/agronomist/configure-input-requirements/
```

**L7.3 - HR Workbench (Día 24)**
```python
# Implementar:
class PayrollRuleSet:
    created_by = FK(User)  # RRHH
    deduction_rules = JSONField()
    bonus_rules = JSONField()
    attendance_policy = JSONField()

# Views/APIs:
- /api/hr/configure-payroll-rules/
- /api/hr/configure-deductions/
- /api/hr/configure-attendance-policy/
```

**L7.4 - Finance Workbench (Día 25)**
```python
# Implementar:
class InterestRatePolicy:
    created_by = FK(User)  # Finanzas
    rate_by_profile = JSONField()
    penalty_policy = JSONField()
    approval_workflow = JSONField()

# Views/APIs:
- /api/finance/configure-interest-rates/
- /api/finance/configure-penalty-policy/
```

**Checkpoint Día 25:** Expert Platform **85%**, SPRINT 3 **COMPLETO**

---

#### SPRINT 4: Quality Shield (Días 26-30)

**FASE LOCAL 8: Zero-Bug Guarantee (Días 26-30)**

**L8.1 - Mutation Testing (Día 26)**
```bash
# Implementar:
pip install mutmut
mutmut run --paths-to-mutate=backend/src/apps/kernels/

# Objetivo: Mutation score > 80%
# Detecta tests débiles que no prueban realmente
```

**L8.2 - Property-Based Testing (Día 27)**
```bash
# Implementar con Hypothesis:
pip install hypothesis

# Tests en kernels críticos:
- Party: Propiedades de multi-role
- Portfolio: Propiedades de allocation
- Payments: Propiedades de idempotencia
```

**L8.3 - Contract Testing (Día 28)**
```bash
# Implementar con Pact:
# Frontend-Backend contracts
# Garantiza que cambios de API no rompen
```

**L8.4 - Production Parity (Día 29)**
```bash
# Implementar:
- Docker dev con PostgreSQL (no SQLite)
- Constraint validation en CI
- Performance baselines en CI
- Migration rehearsal automático
```

**L8.5 - Final Validation (Día 30)**
```bash
# Ejecutar:
- Full test suite con PostgreSQL
- Security scan completo
- Performance benchmarks
- Integration tests end-to-end
- Coverage report (target: 98%)
```

**Checkpoint Día 30:** Quality Shield **98%**, SPRINT 4 **COMPLETO**

---

## 5. Entregables y gates de aceptación

### 5.1 Gates por Sprint

**SPRINT 1 (Días 1-10): Foundation Strength**
```
✅ Party/Counterparty 90%
  - Customer/Supplier/Producer/Declarant roles implementados
  - TaxProfile con RUC
  - Tests PostgreSQL pasando (> 90% coverage)
  - Plan de backfill aprobado

✅ Financial Portfolio 85%
  - Receivable/Payable funcionales
  - Payment allocation idempotente
  - Interest/Penalty calculando
  - Aging reports generando
  - Tests PostgreSQL pasando (> 85% coverage)

✅ Integration 90%
  - Billing → Receivable flujo completo
  - Payment → Allocation → Obligation actualizado
  - Tests end-to-end pasando
```

**SPRINT 2 (Días 11-20): Operational Strength**
```
✅ Payroll 75%
  - PayrollRun/PayrollLine/Deduction implementados
  - Cálculo nómina funcional
  - Predicción costos laborales
  - Tests PostgreSQL pasando (> 75% coverage)

✅ Attendance 70%
  - Registro asistencia funcional
  - Analytics básico (patterns)
  - Tests pasando (> 70% coverage)

✅ Work Planning 70%
  - ProductionUnit/Zone/LaborType implementados
  - Work tasks funcionales
  - Optimización básica
  - Tests pasando (> 70% coverage)

✅ Fleet 70%
  - FleetAsset/Maintenance/Trip implementados
  - Registro funcional
  - Predictive maintenance básico
  - Tests pasando (> 70% coverage)
```

**SPRINT 3 (Días 21-25): Expert Empowerment**
```
✅ Accountant Workbench 85%
  - Contador crea reportes sin código
  - Configura reglas fiscales
  - Preview antes de cerrar

✅ Agronomist Workbench 80%
  - Ingeniero configura labores sin código
  - Configura insumos

✅ HR Workbench 80%
  - RRHH configura deducciones sin código
  - Configura políticas asistencia

✅ Finance Workbench 80%
  - Finanzas configura tasas sin código
  - Configura políticas mora
```

**SPRINT 4 (Días 26-30): Quality Shield**
```
✅ Mutation Testing
  - Mutation score > 80%
  - Tests débiles identificados y reforzados

✅ Property-Based Testing
  - Hypothesis en kernels críticos
  - Casos edge cubiertos automáticamente

✅ Contract Testing
  - Frontend-Backend contracts
  - APIs no rompen

✅ Production Parity
  - Dev con PostgreSQL
  - Constraints validados en CI
  - Performance baselines en CI

✅ Coverage 98%
  - Full test suite pasando
  - Coverage report > 98%
  - Zero critical bugs
```

### 5.2 Métricas de éxito finales (Día 30)

| Métrica | Objetivo | Peso |
|---------|----------|------|
| Party completeness | 90% | 15% |
| Portfolio functionality | 85% | 20% |
| Operational kernels | 75% avg | 20% |
| Expert platform | 85% | 15% |
| Test coverage | 98% | 15% |
| Production parity | 98% | 10% |
| Security hardening | 98% | 5% |

**VIABILIDAD TOTAL:** **95%** (objetivo mínimo 98% requiere +7 días)

## 6. Arquitectura resultante: Sistema de fortalezas

```
┌─────────────────────────────────────────────────────────────┐
│                  NECKTRAL PLATFORM V2.0                      │
│         Sistema de Fortalezas Competitivas                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  CAPA 1: UNIVERSAL IDENTITY HUB (FORTALEZA)                  │
├─────────────────────────────────────────────────────────────┤
│  • Party con multi-role                                      │
│  • Tax Intelligence (RUC)                                    │
│  • Network detection                                         │
│  • Compliance (KYC + AML)                                    │
│  Viabilidad: 90% | Desbloquea: 8 programas                  │
└─────────────────────────────────────────────────────────────┘
                        ↓ ALIMENTA ↓
┌─────────────────────────────────────────────────────────────┐
│  CAPA 2: FINANCIAL INTELLIGENCE ENGINE (FORTALEZA)           │
├─────────────────────────────────────────────────────────────┤
│  • Auto-allocation inteligente                               │
│  • Predictive aging                                          │
│  • Cash flow optimization                                    │
│  • Portfolio analytics                                       │
│  Viabilidad: 85% | ROI: Muy Alto                            │
└─────────────────────────────────────────────────────────────┘
                        ↓ SOPORTA ↓
┌─────────────────────────────────────────────────────────────┐
│  CAPA 3: OPERATIONAL INTELLIGENCE (FORTALEZA)                │
├─────────────────────────────────────────────────────────────┤
│  • Payroll Intelligence (predicción)                         │
│  • Attendance Analytics (patterns)                           │
│  • Work Planning Intelligence (optimización)                 │
│  • Fleet Intelligence (predictive maintenance)               │
│  Viabilidad: 75% avg | ROI: Alto (ahorros 20-30%)           │
└─────────────────────────────────────────────────────────────┘
                        ↓ CONFIGURADO POR ↓
┌─────────────────────────────────────────────────────────────┐
│  CAPA 4: DOMAIN EXPERT PLATFORM (FORTALEZA)                  │
├─────────────────────────────────────────────────────────────┤
│  • Accountant Workbench                                      │
│  • Agronomist Workbench                                      │
│  • HR Workbench                                              │
│  • Finance Workbench                                         │
│  Viabilidad: 85% | ROI: Muy Alto (reduce deps 90%)          │
└─────────────────────────────────────────────────────────────┘
                        ↓ GARANTIZADO POR ↓
┌─────────────────────────────────────────────────────────────┐
│  CAPA 5: QUALITY SHIELD (FORTALEZA)                          │
├─────────────────────────────────────────────────────────────┤
│  • Mutation testing                                          │
│  • Property-based testing                                    │
│  • Contract testing                                          │
│  • Production parity                                         │
│  • 98% coverage guarantee                                    │
│  Viabilidad: 98% | ROI: Alto (bugs -87%, velocity +200%)    │
└─────────────────────────────────────────────────────────────┘
                        ↓ DESPLEGADO EN ↓
┌─────────────────────────────────────────────────────────────┐
│  CAPA 6: CLOUD EXCELLENCE (FORTALEZA)                        │
├─────────────────────────────────────────────────────────────┤
│  • Secrets management                                        │
│  • Backup & disaster recovery                                │
│  • Monitoring & observability                                │
│  • CI/CD optimizado                                          │
│  • Security hardening                                        │
│  Viabilidad: 98% | ROI: Medio (confiabilidad)               │
└─────────────────────────────────────────────────────────────┘
```

## 7. Riesgos y mitigación

| Riesgo | Prob | Impacto | Mitigación |
|--------|------|---------|------------|
| Party backfill rompe datos | ALTA | CRÍTICO | Plan reversible + rehearsal + tests exhaustivos |
| Portfolio tests fallan PostgreSQL | MEDIA | ALTO | Validar constraints día 4, no día 9 |
| Payment allocation no idempotente | MEDIA | CRÍTICO | Tests exhaustivos + idempotency_key obligatorio |
| Personalization gates bloquean | ALTA | MEDIO | Mock inicial + validación posterior con expertos |
| 30 días no suficientes | BAJA | MEDIO | Opción fallback: 21 días para 88% viabilidad |
| Drift de scope | MEDIA | ALTO | Stop conditions estrictas + daily standups |
| Equipo no disponible full-time | ALTA | ALTO | Track Nube puede ser outsource, Local es core |

## 8. Decisiones críticas y ADRs

### ADR-001: Party como Universal Identity Hub
**Decisión:** Party no es solo "persona", es **single source of truth** para toda identidad
**Razón:** Elimina duplicación, habilita multi-role, soporta compliance
**Alternativas rechazadas:** Customer/Supplier separados (genera duplicación)
**Consecuencias:** Backfill complejo pero ROI muy alto

### ADR-002: Financial Portfolio como Intelligence Engine
**Decisión:** Portfolio no solo guarda, **analiza y sugiere**
**Razón:** Transforma gestión reactiva en predictiva
**Alternativas rechazadas:** Portfolio CRUD simple (pierde ventaja competitiva)
**Consecuencias:** Más complejo pero ROI muy alto

### ADR-003: Zero-Bug Guarantee como Gate
**Decisión:** Nada se mergea sin 98% coverage + mutation testing
**Razón:** Bugs en producción cuestan 10x más que en dev
**Alternativas rechazadas:** Coverage "best effort" (genera deuda técnica)
**Consecuencias:** Desarrollo inicial más lento pero velocity aumenta después

### ADR-004: Domain Expert Platform
**Decisión:** Expertos configuran, no developers
**Razón:** Reduce dependencia, aumenta adopción, acelera cambios
**Alternativas rechazadas:** Todo hardcoded (inflexible, lento)
**Consecuencias:** Más upfront work pero ROI muy alto

### ADR-005: Production Parity Obligatorio
**Decisión:** Dev = Prod siempre (PostgreSQL en dev)
**Razón:** Elimina sorpresas en producción
**Alternativas rechazadas:** SQLite en dev (genera bugs PostgreSQL-specific)
**Consecuencias:** Setup más pesado pero bugs críticos eliminados

## 9. Stop conditions

**Detener ejecución si:**
- ❌ Party no tiene Customer/Supplier roles después de día 3
- ❌ Financial Portfolio no tiene Receivable/Payable después de día 5
- ❌ Tests de idempotencia fallan en Payment allocation
- ❌ Backfill rompe datos en rehearsal
- ❌ PostgreSQL constraints no validan en CI después de día 29
- ❌ Coverage < 95% en día 30
- ❌ Security scan tiene críticos sin resolver en día 30

## 10. Siguiente documento rector

Una vez completado este roadmap híbrido (Día 30):

**Siguiente fase:** `docs/project/NECKTRAL_VERTICALES_ROADMAP.md`
- Hacienda/Fincas verticales
- Ganadería operations
- Agroquímicos flow
- Transporte services
- Duración estimada: +15 días para 98% completo

**Documentos de soporte:**
- `docs/project/NECKTRAL_DECISION_LOG.md` - Actualizar con ADRs
- `docs/project/NECKTRAL_TECH_DEBT.md` - Crear registro de deuda técnica
- `docs/project/NECKTRAL_PERFORMANCE_BASELINES.md` - Crear baselines

## 11. Conclusión ejecutiva

Este roadmap híbrido transforma **65% de viabilidad actual a 95% en 30 días** mediante:

1. **Track Nube paralelo (7 días):** Infraestructura production-ready 98%
2. **Track Local secuencial (30 días):** Kernels de negocio + Quality Shield

**Cada debilidad se convierte en fortaleza competitiva:**
- Party débil → Universal Identity Hub
- Portfolio básico → Financial Intelligence Engine
- Tests incompletos → Zero-Bug Guarantee
- Personalization bloqueada → Domain Expert Platform
- Kernels ausentes → Operational Intelligence

**ROI esperado:** 450% en 6 meses
**Payback period:** 3 meses
**Ventaja competitiva:** Sistema inteligente, no solo funcional

**Este no es un roadmap de "fix bugs" - es un roadmap de "build moats"** 🏰

---

**Última actualización:** 2026-05-30
**Próxima revisión:** Día 10 (fin Sprint 1)
**Owner:** Equipo Necktral
**Aprobadores:** Gerencia + Stakeholders técnicos
