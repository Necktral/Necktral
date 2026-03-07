# Blueprint de Arquitectura Modular (High Standard)

## 0) Resumen ejecutivo

Diseñar la plataforma con arquitectura **modular + event-driven transaccional**:

- **Kernels Core**:
  1. Identity & Tenant Context (IAM/RBAC/SoD)
  2. Billing (documentos comerciales y fiscales)
  3. Inventory (existencias y movimientos)
  4. Accounting Ledger (double-entry, periodos, cierres)

- **Módulos verticales** (Fuel, retail, servicios, etc.) integrados por:
  - APIs internas versionadas
  - Eventos de dominio con Outbox/Inbox e idempotencia

- **Principio rector**: **Accounting Ledger** es el sistema de registro financiero final.

---

## 1) Principios de arquitectura (no negociables)

1. **Tenant isolation por diseño**
   - `tenant_id/company_id` obligatorio en tablas operativas.
   - RLS (si aplica) + guardas de aplicación.
   - Sin consultas globales sin scope explícito.

2. **Source of truth por dominio**
   - Billing: verdad de documentos comerciales/fiscales.
   - Inventory: verdad de stock y costo.
   - Accounting: verdad financiera consolidada.

3. **Inmutabilidad operativa**
   - No editar histórico crítico.
   - Usar `void/cancel/reverse` + trazabilidad.

4. **Idempotencia end-to-end**
   - Comandos con `idempotency_key`.
   - Eventos con `event_id` único + deduplicación.

5. **Consistencia explícita**
   - Fuerte dentro del agregado.
   - Eventual entre bounded contexts vía outbox.

6. **Contrato primero**
   - Esquemas API/eventos versionados y backward compatible.

---

## 2) Bounded Contexts y responsabilidades

### 2.1 IAM / Tenant Context (Kernel)
Responsable de usuarios, membresías, org units, RBAC y SoD.

Entidades clave:
- `org_unit`
- `user_membership`
- `role`
- `permission`
- `role_assignment`
- `policy`
- `approval_matrix`

### 2.2 Billing Kernel
Responsable de ciclo de vida de documentos comerciales/fiscales e impuestos.

Entidades:
- `billing_document`
- `billing_line`
- `tax_breakdown`
- `billing_series`
- `billing_payment_application` (v2)

Estados recomendados:
- `DRAFT -> ISSUED -> POSTED -> SETTLED`
- Anulación: `VOIDED`

### 2.3 Inventory Kernel
Responsable de ítems/UOM, almacenes, stock, movimientos y costo.

Entidades:
- `inventory_item`
- `uom`
- `uom_conversion`
- `warehouse`
- `stock_balance`
- `stock_movement`
- `stock_movement_line`
- `cost_layer` (si FIFO)

Regla:
- No stock negativo sin política explícita y auditada.

### 2.4 Accounting Kernel (Ledger)
Responsable de plan de cuentas, asientos, periodos y cierres.

Entidades:
- `chart_of_accounts`
- `account`
- `journal_entry`
- `journal_line`
- `fiscal_period`
- `posting_batch`
- `fx_rate`
- `revaluation_entry`

Reglas duras:
- `SUM(debit) == SUM(credit)`
- Sin posteos en periodos cerrados.

### 2.5 Vertical Modules (ej. Fuel)
Responsable de flujo operativo del negocio y emisión de hechos al kernel.

No responsable de redefinir reglas base del kernel.

---

## 3) Modelo de datos canónico transversal

Campos obligatorios en entidades transaccionales:
- `id` (UUID/ULID)
- `tenant_id` / `company_id`
- `branch_id` (si aplica)
- `status`
- `created_at`, `created_by`
- `updated_at`, `updated_by`
- `version` (optimistic locking)
- `source_module`, `source_type`, `source_id`

Trazabilidad técnica:
- `request_id`
- `correlation_id`
- `idempotency_key`

---

## 4) Contratos de integración (API + Eventos)

### 4.1 API interna (sync)
Comandos críticos:
- `POST /inventory/movements`
- `POST /billing/documents/{id}/issue`
- `POST /accounting/journal-entries/post`

Respuesta estándar:
- `resource_id`, `status`, `version`, `correlation_id`

### 4.2 Eventos de dominio (async)
Envelope recomendado:

```json
{
  "event_id": "uuid",
  "event_type": "billing.document.issued.v1",
  "occurred_at": "2026-03-07T12:00:00Z",
  "tenant_id": "uuid",
  "branch_id": "uuid",
  "source": {
    "module": "billing",
    "entity": "billing_document",
    "id": "uuid"
  },
  "correlation_id": "uuid",
  "idempotency_key": "string",
  "payload": {}
}
```

Eventos mínimos:
- `inventory.movement.posted.v1`
- `billing.document.issued.v1`
- `billing.document.voided.v1`
- `accounting.entry.posted.v1`
- `accounting.entry.reversed.v1`
- `fuel.sale.created.v1`
- `fuel.sale.cancelled.v1`

---

## 5) Outbox/Inbox + idempotencia

Flujo:
1. Persistir cambio de negocio + `outbox_event` en la misma transacción.
2. Dispatcher publica y marca `published_at`.
3. Consumidor registra en `inbox_event` con unicidad por `event_id`.
4. Retries exponenciales + DLQ + replay manual.

Tablas sugeridas:
- `outbox_event(id, aggregate_type, aggregate_id, event_type, payload, status, retries, next_retry_at, published_at)`
- `inbox_event(event_id, consumer_name, processed_at, status, error)`

---

## 6) Posting engine contable

Diseño:
- Reglas por `event_type`, país, tenant, régimen fiscal.
- Soporta impuestos, descuentos, medios de pago y costo de venta.

Flujo:
1. Recibe hecho económico.
2. Construye asiento.
3. Valida cuentas/periodo/balance.
4. Postea y referencia documento origen.
5. Emite `accounting.entry.posted.v1`.

Reversos:
- Asiento inverso con `reversal_of_entry_id`.
- Nunca borrar asientos.

---

## 7) Multiempresa e intercompany

Operación:
- Documento AR en empresa vendedora.
- Documento AP espejo en empresa compradora.

Contabilidad:
- Cuentas intercompany por contraparte.
- Eliminaciones para consolidación (v2).

Conciliación:
- `PENDING`, `MATCHED`, `MISMATCH`, `RESOLVED`.

---

## 8) Seguridad, cumplimiento y auditoría

- RBAC granular + contexto.
- SoD: crear/aprobar/postear/reversar segregado.
- Audit trail inmutable (hash chain recomendado).
- Cifrado selectivo de PII + masking.
- Políticas de retención y export legal.

---

## 9) Observabilidad y SRE

- Logs estructurados con `correlation_id`.
- Métricas de latencia/error/lag outbox/desbalance contable.
- Tracing distribuido (OpenTelemetry).
- SLO por dominio + runbooks de replay/reconciliación.

---

## 10) Versionado y cambios

- APIs: `/v1`, `/v2`.
- Eventos: sufijo `.v1`, `.v2`.
- Deprecación formal + schema registry + contract tests.

---

## 11) Roadmap sugerido (2 trimestres)

### Q1
1. Contratos canónicos (money/UOM/status/event envelope).
2. Framework único Outbox/Inbox.
3. Accounting mínimo (plan cuentas + asientos + periodos).
4. Integración Billing -> Accounting.
5. Integración Inventory -> Accounting.

### Q2
1. Intercompany v1 (AR/AP espejo + conciliación).
2. SoD + aprobaciones.
3. Reporting financiero/operativo unificado.
4. Reglas contables por país/tenant.
5. Hardening de performance, DR y resiliencia.

---

## 12) KPIs de éxito

- % transacciones con trazabilidad E2E.
- Tiempo de cierre diario/mensual.
- Diferencias de conciliación por 1,000 transacciones.
- % reprocesos exitosos de eventos.
- Incidentes de aislamiento tenant (objetivo: 0).
- Lead time para lanzar nuevos verticales.

---

## 13) Decisiones concretas recomendadas

1. Mantener **Fuel** como vertical.
2. Formalizar kernels de **Billing/Inventory/Accounting**.
3. Estandarizar `correlation_id` + `idempotency_key` en endpoints críticos.
4. Priorizar posting engine antes de nuevos verticales masivos.
5. Gobernanza por RFC corto para cambios de contrato.