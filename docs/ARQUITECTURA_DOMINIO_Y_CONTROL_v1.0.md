# Arquitectura de Dominio y Control v1.0

Version: v1.0  
Fecha: 2026-03-07  
Estado: Propuesta formal para adopcion

## 1) Proposito

Definir una arquitectura modular donde:

- los kernels concentren la verdad operativa y financiera;
- los adaptadores fiscales cambien cumplimiento sin romper el nucleo;
- el CEC actue como control plane (validacion, evidencia, cierre, riesgo);
- y la evolucion contable pase de Shadow Ledger a GL formal sin reescribir historia.

Regla rectora:

> Una sola verdad operativa, una sola verdad financiera final y capas derivadas no competitivas.

## 2) Topologia objetivo

La plataforma se organiza en cuatro ejes.

### Eje A: Kernels de verdad

1. IAM / Tenant / Policy Kernel
2. Billing / Fiscal Document Kernel
3. Inventory / Cost Kernel
4. Accounting Kernel

### Eje B: Modulos core de soporte operativo

5. Payments & Cash Module
6. CEC Control Plane
7. Integration / Event Backbone

### Eje C: Adaptadores fiscales

8. Fiscal Adapter A
9. Fiscal Adapter B

### Eje D: Verticales

10. Fuel
11. Retail / POS
12. Services
13. Procurement
14. Verticales futuros

## 3) Jerarquia de verdad

### Nivel 1: Verdad operativa primaria

- IAM: identidad, contexto, membresias, RBAC, SoD.
- Billing: documentos comerciales/fiscales y lifecycle.
- Inventory: stock, movimientos, costo.
- Payments/Cash: cobros, conciliacion, sesiones de caja.

### Nivel 2: Verdad derivada de control

CEC valida, reconcilia, evidencia y empaqueta cierres.  
CEC no crea verdad primaria.

### Nivel 3: Verdad financiera final

Accounting (GL formal): asientos, periodos, cierres, reversos, revaluaciones.  
El GL formal es la unica verdad financiera posteada.

### Regla Shadow Ledger

Shadow Ledger no es segunda contabilidad; es proyeccion determinista previa al posting formal.

## 4) Invariantes no negociables

1. No delete historico critico; solo reversas.
2. Unicidad fiscal de serie/correlativo/tipo/scope.
3. Cierre condicionado por igualdad economica esperada vs confirmada.
4. Auditoria append-only con actor, tiempo, motivo y causalidad.
5. Idempotencia extremo a extremo (comandos y eventos).
6. Segregacion de funciones en operaciones sensibles.
7. Stock no negativo por defecto.
8. Politica de costo versionada y estable por ciclo.
9. JournalEntry siempre balanceado (debit == credit).
10. No posting en periodo cerrado.
11. Cierres reproducibles (mismos inputs/version -> mismo output).
12. Excel solo como entregable derivado, nunca como verdad canonica.

## 5) Ownership por kernel/modulo

### 5.1 IAM / Tenant / Policy

Posee:

- usuarios, membresias, contexto, RBAC, SoD y aprobaciones.

Prohibido:

- stock, correlativos fiscales, balances contables, logica vertical.

### 5.2 Billing / Fiscal Document

Posee:

- drafts, issue, void, credit notes, numeracion fiscal, impuestos, linkage documental.

Prohibido:

- stock/costo, cash sessions, journal entries finales.

### 5.3 Inventory / Cost

Posee:

- item master, UOM, almacenes, movimientos, ajustes, transferencias, costo.

Prohibido:

- numeracion fiscal y asientos contables finales.

### 5.4 Accounting

Posee:

- EconomicEvent, Shadow Ledger, PostingRuleSet, JournalEntry, period close.

Prohibido:

- hechos operativos primarios (tickets, stock, caja operativa).

### 5.5 Payments & Cash

Posee:

- intents, autorizaciones/capturas/refunds, conciliacion provider, cash sessions y diferencias.

Prohibido:

- correlativos fiscales, costo de inventario, journal final.

### 5.6 CEC Control Plane

Posee:

- validaciones, reconciliaciones, evidencia hashada, excepciones, manifests, gates y close orchestration.

Prohibido:

- editar verdad primaria, renumerar documentos, postear contabilidad por su cuenta.

## 6) Contratos canonicos entre modulos

### 6.1 Principios de integracion

- Consistencia fuerte intra-agregado.
- Consistencia eventual entre bounded contexts.
- Outbox/inbox, versionado de contratos, dedupe y replay seguro.

### 6.2 Envelope minimo de evento

Todo evento inter-modulo debe incluir:

- event_id
- event_type
- occurred_at
- source_module
- tenant/company/branch scope
- actor y/o device
- correlation_id
- causation_id
- schema_version
- payload

### 6.3 Eventos de referencia

- Billing: `DocumentDrafted`, `DocumentIssued`, `DocumentVoided`, `CreditNoteIssued`.
- Inventory: `InventoryMovementPosted`, `InventoryAdjusted`, `TransferCompleted`.
- Payments/Cash: `PaymentCaptured`, `RefundProcessed`, `CashSessionClosed`, `CashDifferenceDetected`.
- Accounting: `EconomicEventRegistered`, `JournalDraftGenerated`, `JournalPosted`, `PeriodClosed`.
- CEC: `CloseRunPackaged`, `ExceptionRaised`, `ExceptionResolved`, `GateStateChanged`.

## 7) Adaptadores fiscales A/B

Ambos deben cumplir la misma interfaz:

1. `attach_or_reserve_reference()`
2. `issue_document()`
3. `void_document()`
4. `issue_credit_note()`
5. `record_contingency()`
6. `produce_fiscal_evidence()`
7. `validate_range_integrity()`

Regla:

- A/B cambian cumplimiento y evidencia.
- A/B no cambian ownership de Billing, Inventory, Payments/Cash ni Accounting.

## 8) Shadow Ledger formal

Objetos minimos:

- EconomicEvent
- JournalDraft
- PostingRuleSet
- CloseRun
- DraftValidationResult
- ExceptionLink

Reglas:

1. Todo EconomicEvent deriva de hechos operativos canonicos.
2. Todo JournalDraft es reproducible y versionado.
3. No se "corrige Excel"; se abre excepcion formal.
4. Cada draft guarda `rule_set_version`, `contract_version`, `input_manifest_hash`.

Flujo recomendado:

`GENERATED -> VALIDATED -> EXCEPTION -> APPROVED_FOR_POSTING -> POSTED -> SUPERSEDED`

## 9) Maquinas de estado base

- Venta: `DRAFT -> OPEN -> PAID -> CLOSED -> VOIDED`
- Documento A: `PENDING_LINK -> LINKED_MANUAL -> VERIFIED -> VOIDED`
- Documento B: `NUMBER_RESERVED -> ISSUED -> PRINTED -> FAILED_PRINT -> CONTINGENCY -> VOIDED`
- Pago: `INTENDED -> AUTHORIZED -> CAPTURED -> REFUNDED|FAILED`
- CashSession: `OPEN -> COUNT_PENDING -> REVIEW_PENDING -> CLOSED -> REOPENED_FOR_INVESTIGATION`
- Movimiento inventario: `PROPOSED -> POSTED -> REVERSED`
- JournalDraft: `GENERATED -> VALIDATED -> EXCEPTION -> APPROVED_FOR_POSTING -> POSTED`
- CloseRun: `CREATED -> GATHERED -> VALIDATED -> PACKAGED -> DELIVERED -> REOPENED_EXCEPTION`

## 10) Fases de madurez

1. Nucleo disciplinado (IAM, Billing, Inventory, Payments/Cash).
2. Contratos canonicos + event backbone.
3. CEC operativo D+0 y cierres reproducibles.
4. Shadow Ledger con RuleSet v1.
5. Posting formal controlado.
6. Readiness fiscal Adapter B.
7. GL pleno e intercompany.

## 11) Anti-patrones prohibidos

1. CEC como mega-modulo ambiguo.
2. Shadow Ledger como segunda contabilidad.
3. Billing posteando contabilidad final.
4. Inventory mutando costo sin versionado.
5. Excel como fuente primaria.
6. Adaptadores fiscales con logica de negocio central.
7. Verticales con mini-stocks o mini-ledgers paralelos.
8. Edicion directa de historico cerrado.
9. Reaperturas sin cadena de auditoria.
10. Bypass de SoD o credenciales compartidas.

## 12) Decisiones a congelar ahora

1. Politica de costo (metodo, scope y versionado).
2. Estados canonicos de documentos/pagos/caja/journals/cierres.
3. Envelope canonico de eventos.
4. PostingRuleSet v1.
5. Modelo de evidencia + manifests hashados.
6. Modelo de excepciones CEC.
7. Interfaz fiscal A/B unica.
8. Payments/Cash como modulo de primer nivel.

## 13) Mapeo al repo actual (alineacion)

Implementacion actual alineada parcialmente:

- IAM/RBAC/contexto: `backend/src/apps/iam`, `backend/src/apps/rbac`
- Auditoria: `backend/src/apps/audit`
- Sync backbone (en transicion): `backend/src/apps/sync_engine`, `backend/src/apps/sync`
- Billing kernel: `modulos/facturacion`
- Inventory kernel: `modulos/inventarios`
- Vertical Fuel: `modulos/estacion_servicios`

Brechas actuales que este blueprint busca cerrar:

- Estandarizar contratos de error y eventos entre kernels.
- Formalizar Payments/Cash como modulo explicito.
- Evitar dualidad de motores sync en produccion.
- Pasar de auditoria operativa a CEC como control plane completo.
- Formalizar Shadow Ledger/PostingRuleSet sin duplicar verdad contable.

