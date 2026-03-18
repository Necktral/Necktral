# Context Card

**Proyecto:** Necktral ERP/CRM
**Fecha de corte usada:** 2026-03-15
**Objetivo inmediato:** convertir la matriz de endurecimiento en un plan **sprintable** y usable por Codex, con foco en kernels/core antes de Reportes y Dashboard.

## Estado factual del repo

* El proyecto declara una arquitectura donde los **kernels concentran la verdad operativa y financiera**, CEC actúa como **control plane**, y Shadow Ledger es proyección previa al GL formal, no una segunda contabilidad 
* El `Contract Pack v1.0` fija como base: scope multiempresa, RBAC por método, auditoría contractual, sync/idempotencia y QA determinista como puerta de integración 
* El estado ejecutivo del repo indica que el backend ya tiene **F1–F12 implementadas/certificadas en staging-first**, con toolchain y gates activos; lo pendiente fuerte es promoción/operación productiva, no rehacer Accounting/CEC desde cero  
* El roadmap de mejoras futuras deja explícito que todavía faltan: **Billing kernel reutilizable**, **Inventory kernel con trazabilidad fuerte**, **Outbox transaccional** y **Motor de reportes formal** 
* La autenticación contextual ya es una pieza fuerte: `JWTAuthWithOrgContext` exige `X-Company-Id`, valida membresías, inyecta `company/branch`, soporta `data_scope` READ intercompany y bloquea bypass de branch dentro de la misma company 
* La auditoría contractual ya está endurecida: payload canónico, `event_hash = SHA256`, `signature = HMAC`, y encadenamiento por partición/tenant
* Accounting ya refleja un estado maduro: lista de eventos económicos soportados, link operacional directo para BILLING/INVENTORY, selección de `PostingRuleSet`, validación/posting de drafts y publicación de `JournalPosted`
* Billing sí tiene ya un **contrato operativo mínimo** documentado (estados, eventos, RBAC y compat legacy), pero todavía como contrato mínimo, no como kernel completamente endurecido 

## Decisión de arquitectura vigente

1. **Primero endurecer kernels/core**
2. **Luego Reportes** como módulo transversal formal
3. **Después Dashboard** como consumidor de reportes + lecturas operativas/control

## Orden de trabajo correcto

1. IAM / Scope / RBAC / Audit
2. Integration / Event Backbone
3. Accounting
4. CEC
5. Billing
6. Inventory
7. Payments & Cash
8. Reportes
9. Dashboard

---

# Decision Log Update

**2026-03-15 — decisión nueva**

* Se deja de trabajar “dashboard-first”.
* El plan se reordena a **kernel-hardening-first**.
* Se confirma que **Reportes** debe ir antes que Dashboard.
* La ejecución para Codex se dividirá en sprints por bloques semánticos, no por UI.

**Racional**
El repo ya tiene base dura en IAM, Audit, Accounting y CEC, mientras Billing/Inventory/Outbox/Reportes siguen explícitamente en backlog de madurez. Empujar Dashboard antes de cerrar esos contratos degradaría la semántica del sistema

---

# Backlog Update (Sprintable)

## Convención de sprint

* Duración sugerida: **1 sprint = 1 semana**
* Tamaño de PR: pequeño/mediano
* Cada sprint debe cerrar con:

  * contrato/documento actualizado,
  * tests,
  * evidencia mínima,
  * checklist de rollback

---

## Sprint 0 — Baseline y guardrails para Codex

### Objetivo

Congelar el marco de trabajo y evitar que Codex implemente cosas fuera de ownership.

### Entregables

* `docs/ADR_KERNEL_HARDENING_PLAN_v1.0.md`
* `docs/ADR_KERNEL_OWNERSHIP_BOUNDARIES_v1.0.md`
* `docs/ADR_REPORTES_BEFORE_DASHBOARD_v1.0.md`
* `docs/operacion/CHECKLIST_KERNEL_HARDENING_PR_v1.0.md`

### Tareas

1. Crear ADR con orden oficial de hardening.
2. Crear tabla única de ownership/prohibiciones:

   * IAM
   * Billing
   * Inventory
   * Payments & Cash
   * Accounting
   * CEC
   * Integration
3. Definir DoD universal por kernel.
4. Añadir checklist de PR específico para hardening.

### Definition of Done

* ADRs versionados en `docs/`
* checklist copiable para PR
* orden de trabajo congelado
* sin cambios de lógica todavía

### Riesgo principal

Codex empiece a “optimizar” sin fronteras de dominio.

### Dependencias

Ninguna.

---

## Sprint 1 — IAM / Scope / RBAC / Audit coverage

### Objetivo

Cerrar el enforcement universal de contexto y permisos.

### Fundamento del repo

`JWTAuthWithOrgContext` ya exige `X-Company-Id`, resuelve `company/branch`, soporta `data_scope` y bloquea bypass de `X-Data-Branch-Id` en la misma empresa 
El middleware antiguo existe como precedente duplicado de responsabilidad 

### Entregables

* matriz de coverage de endpoints operativos
* tests de scope por app crítica
* ADR corto sobre “camino canónico de contexto”

### Tareas

1. Inventariar endpoints operativos críticos:

   * billing
   * inventory
   * payments
   * accounting
   * cec
   * integration
2. Verificar cuáles usan realmente `JWTAuthWithOrgContext`.
3. Identificar si `OrgContextMiddleware` sigue siendo dependencia real o residual.
4. Agregar tests para:

   * falta `X-Company-Id`
   * `X-Branch-Id` inválido
   * sin membresía company
   * sin membresía branch
   * `data_scope` intercompany READ
   * bypass de `X-Data-Branch-Id`
5. Estandarizar denegaciones con `required_scope` cuando corresponda.

### Archivos probables a tocar

* `backend/src/apps/iam/authentication.py`
* `backend/src/apps/iam/context_middleware.py`
* `backend/src/config/settings*.py`
* tests nuevos en `backend/src/tests/`

### Definition of Done

* cobertura de tests de contexto en endpoints críticos
* decisión explícita sobre auth canónica vs middleware
* cero bypass de scope detectado en tests

### Riesgo principal

Romper rutas legacy o exentas de auth.

---

## Sprint 2 — Auditoría contractual y taxonomía mínima por kernel

### Objetivo

Asegurar que todos los writes críticos emitan auditoría contractual consistente.

### Fundamento del repo

El writer ya implementa payload canónico, SHA256, HMAC y cadena por partición con `company_id`/`branch_id` en metadata cuando existe contexto

### Entregables

* catálogo mínimo de `event_type` por kernel
* tests de auditoría en operaciones write críticas
* check de metadata enriquecida con scope

### Tareas

1. Revisar catálogos de eventos actuales por:

   * Billing
   * Inventory
   * Payments
   * Accounting
   * CEC
2. Detectar writes sin `write_event()`.
3. Añadir tests que verifiquen:

   * `company_id` en metadata
   * `branch_id` si aplica
   * `request_id`
   * cadena íntegra
4. Crear documento corto:

   * `docs/ADR_AUDIT_TAXONOMY_MIN_v1.0.md`

### Archivos probables a tocar

* `backend/src/apps/audit/contracts.py`
* `backend/src/apps/audit/writer.py`
* servicios/views de cada app que hagan writes
* tests audit

### Definition of Done

* cada operación crítica write deja evento auditable
* taxonomía mínima documentada
* tests de integridad pasan

### Riesgo principal

Agregar eventos sin armonizar catálogos.

---

## Sprint 3 — Integration / Event Backbone / Outbox hardening

### Objetivo

Cerrar el gap de outbox transaccional e idempotencia visible.

### Fundamento del repo

El roadmap lo marca como pendiente explícito: **Outbox transaccional** + reprocesamiento idempotente y visible 
La arquitectura exige envelope canónico, versionado y consistencia eventual entre contexts

### Entregables

* ADR del envelope canónico operativo
* tabla de dedupe / política idempotente
* backlog técnico de consumers críticos

### Tareas

1. Inventariar `OutboxEvent` / `InboxEvent` y consumers existentes.
2. Verificar qué cambios de dominio publican evento dentro de la misma TX.
3. Definir contrato único del envelope:

   * `event_id`
   * `event_type`
   * `occurred_at`
   * `source_module`
   * `correlation_id`
   * `causation_id`
   * `schema_version`
   * `scope`
4. Crear tests de dedupe / replay para:

   * BILLING
   * INVENTORY
   * ACCOUNTING
5. Crear task list separada para consumers no idempotentes.

### Archivos probables a tocar

* `backend/src/apps/integration/models.py`
* `backend/src/apps/integration/services.py`
* `backend/src/apps/integration/management/commands/*`
* tests de integration

### Definition of Done

* envelope canónico congelado
* tests de replay/dedupe
* visibilidad básica de reproceso/error

### Riesgo principal

Reprocesos duplicando efectos de dominio.

---

## Sprint 4 — Accounting contract freeze

### Objetivo

Congelar lo que ya está fuerte y convertirlo en baseline estable.

### Fundamento del repo

Accounting ya soporta:

* `SUPPORTED_ECONOMIC_EVENTS`
* `OPERATIONAL_ACCOUNTING_EVENTS`
* runtime de posting
* `PostingRuleSet` activo por scope/fecha
* normalización de eventos
* generación/validación/posting de drafts
* publicación de `JournalPosted`

### Entregables

* `docs/ADR_ACCOUNTING_RULESET_V1_FREEZE.md`
* `docs/ADR_ACCOUNTING_EVENT_MATRIX_V1.md`
* fixtures oficiales de tests

### Tareas

1. Documentar tabla oficial:

   * `SUPPORTED_ECONOMIC_EVENTS`
   * `OPERATIONAL_ACCOUNTING_EVENTS`
2. Congelar criterios para `PostingRuleSet ACTIVE`.
3. Definir tests de determinismo mínimos:

   * mismo input => mismo draft
   * mismo draft => mismo journal
4. Revisar casos PAYMENTS:

   * hoy soportado en proyección,
   * no necesariamente en link operacional directo
5. Crear task separada para formalizar esa frontera.

### Archivos probables a tocar

* `backend/src/apps/accounting/services.py`
* `backend/src/apps/accounting/models.py`
* docs/operacion o docs/ADR
* tests accounting

### Definition of Done

* matriz de eventos documentada
* rule set v1 congelado
* tests de determinismo mínimos en verde

### Riesgo principal

Tocar demasiado Accounting y romper fases certificadas ya cerradas.

---

## Sprint 5 — CEC guardrails y excepciones

### Objetivo

Reafirmar a CEC como control plane, no mega-módulo.

### Fundamento del repo

La arquitectura le asigna a CEC validación, reconciliación, evidencia hashada, exceptions, manifests y gates, y le prohíbe mutar verdad primaria o postear contabilidad por su cuenta 

### Entregables

* ADR “CEC no muta verdad primaria”
* catálogo base de excepciones por módulo
* policy de `blocking` vs `non-blocking`

### Tareas

1. Inventariar `CECException` y fingerprints usados por Accounting.
2. Documentar severidades y estados abiertos.
3. Verificar que no existan writes indebidos desde CEC hacia verdad primaria.
4. Crear tests de regresión para:

   * apertura de excepción
   * dedupe por fingerprint
   * run reabierto por excepción blocking

### Archivos probables a tocar

* `backend/src/apps/cec/models.py`
* `backend/src/apps/cec/services.py`
* `backend/src/apps/accounting/services.py`
* tests CEC/accounting integration

### Definition of Done

* policy de excepción congelada
* pruebas de blocking correctas
* CEC confirmado como orquestador/control plane

### Riesgo principal

Acoplar CEC a lógica de corrección manual.

---

## Sprint 6 — Billing kernel hardening v1

### Objetivo

Pasar Billing de “contrato mínimo + compat legacy” a kernel documental más fuerte.

### Fundamento del repo

`BILLING_KERNEL_v1.0.md` ya define:

* estados mínimos `DRAFT -> ISSUED -> VOIDED`
* eventos `BILLING_DOC_CREATED`, `BILLING_DOC_ISSUED`, `BILLING_DOC_VOIDED`
* RBAC por método
* coexistencia de endpoints legacy y nuevos 
  Pero el roadmap todavía lo trata como mejora mediana pendiente 

### Entregables

* consolidación del agregado documental
* tests create/issue/void end-to-end
* contrato de deprecación legacy documentado

### Tareas

1. Auditar el estado real de:

   * `/api/billing/docs/`
   * `/api/billing/invoices/`
2. Verificar headers de deprecación en legacy.
3. Añadir invariantes:

   * no void de draft
   * no issue sin totales/líneas válidas
   * auditoría en create/issue/void
4. Crear matriz de permisos:

   * create
   * read
   * issue
   * void
5. Crear backlog separado para `CREDIT_NOTE` si no está formalizado aún.

### Archivos probables a tocar

* `docs/BILLING_KERNEL_v1.0.md`
* `modulos/facturacion/models.py`
* `modulos/facturacion/services.py`
* `modulos/facturacion/views.py`
* tests billing

### Definition of Done

* flujos create/issue/void probados
* RBAC por método estable
* legacy documentado y encapsulado

### Riesgo principal

Confundir compat legacy con verdad canónica.

---

## Sprint 7 — Inventory kernel hardening v1

### Objetivo

Convertir movimientos/kardex en verdad primaria efectiva.

### Fundamento del repo

La arquitectura y el backlog apuntan a Inventory como kernel de stock/movimientos/costo, con stock no negativo por defecto y política de costo versionada
El `Contract Pack v2.0` ya muestra contrato mínimo de errores `INVENTORY_*`, señal de que la semántica del kernel está en consolidación 

### Entregables

* ADR “movimiento = fuente de verdad”
* tests de balances reconstruibles
* contrato mínimo de movimientos

### Tareas

1. Inventariar endpoints y servicios de:

   * receive
   * issue
   * adjust
   * transfer
2. Verificar que no exista update directo de saldo.
3. Añadir tests de:

   * insuficiencia de stock
   * idempotencia
   * ajuste
   * transferencia
4. Congelar contrato de errores.
5. Crear task separada para política de costo versionada.

### Archivos probables a tocar

* `modulos/inventarios/models.py`
* `modulos/inventarios/services.py`
* `modulos/inventarios/views.py`
* tests inventory
* docs de contrato si falta versión formal

### Definition of Done

* movimiento como fuente primaria operacional
* saldos derivables/reconstruibles
* stock negativo bloqueado por defecto

### Riesgo principal

Persistir saldos “manuales” no explicables desde movimientos.

---

## Sprint 8 — Payments & Cash boundary freeze

### Objetivo

Congelar la frontera semántica entre operación de caja/pago y Accounting.

### Fundamento del repo

La arquitectura lo ubica como módulo core de primer nivel, pero Accounting hoy solo permite link operacional directo para BILLING/INVENTORY; PAYMENTS aparece en eventos soportados de proyección, no plenamente en write-time link operativo

### Entregables

* ADR de frontera PAYMENTS vs ACCOUNTING
* catálogo base de eventos de caja/pago
* backlog técnico de integración contable por evento

### Tareas

1. Congelar catálogo semántico:

   * `CashMovementPosted`
   * `CashSessionClosed`
   * diferencias
   * refund/capture si aplica
2. Definir por evento:

   * operacional puro
   * proyección shadow
   * link a accounting write-time
3. Evaluar si `CashSessionClosed` con diferencia distinta de cero es el único evento contable actual soportado, como ya sugiere `_event_is_supported()` 
4. Crear tabla de mapeo.

### Archivos probables a tocar

* `backend/src/apps/payments/*`
* `backend/src/apps/accounting/services.py`
* tests payments/accounting

### Definition of Done

* frontera semántica documentada
* sin ambigüedad sobre qué postea y cuándo

### Riesgo principal

Caja y contabilidad divergiendo según pantalla o proceso.

---

# Codex Delegation

## Ask Prompt (para que Codex inspeccione el codebase antes de tocar)

```text
Proyecto: Necktral ERP/CRM (repo: Necktral/Necktral)

Objetivo:
Validar el plan sprintable de kernel hardening contra el codebase real y devolver un informe de factibilidad por sprint.

Necesito que inspecciones el repo y respondas, para cada sprint 1–8:
1. Archivos exactos a tocar
2. Dependencias reales
3. Riesgos de regresión
4. Tests ya existentes reutilizables
5. Gaps entre la documentación y la implementación actual
6. Si el sprint es PR-small, PR-medium o PR-large

Prioridades:
- No inventes ownerships.
- Respeta la jerarquía: kernels de verdad -> reportes -> dashboard.
- Verifica especialmente:
  - IAM/contexto (`JWTAuthWithOrgContext`, `OrgContextMiddleware`)
  - auditoría contractual (`apps/audit`)
  - outbox/inbox (`apps/integration`)
  - accounting (`apps/accounting/services.py`)
  - billing (`modulos/facturacion`)
  - inventory (`modulos/inventarios`)
  - payments (`apps/payments`)

Salida esperada:
- tabla por sprint
- lista de archivos
- dependencias
- riesgos
- recomendación de orden final si encuentras algo inconsistente
```

## Code Prompt (para que Codex empiece implementación)

```text
Implementa Sprint 1 del plan de kernel hardening en Necktral.

Sprint 1 = IAM / Scope / RBAC / Audit coverage

Objetivo:
Cerrar el enforcement universal de contexto y permisos sin cambiar ownership de dominio.

Tareas:
1. Inventariar endpoints operativos críticos y verificar cuáles dependen realmente de JWTAuthWithOrgContext.
2. Revisar si OrgContextMiddleware sigue siendo necesario o si debe quedar explícitamente como precedente/deprecado.
3. Añadir tests para:
   - falta X-Company-Id
   - X-Branch-Id inválido
   - usuario sin membresía a company
   - usuario sin membresía a branch
   - X-Data-Company-Id / X-Data-Branch-Id en modo READ intercompany
   - bloqueo de bypass de X-Data-Branch-Id dentro de la misma company
4. Estandarizar required_scope cuando aplique denegación.
5. No cambies comportamiento de endpoints exentos salvo que haya bug real demostrado por test.

Restricciones:
- No cambies la jerarquía arquitectónica.
- No metas Reportes ni Dashboard.
- No inventes nuevos permisos de negocio.
- Mantén PR pequeño/mediano.
- Escribe o ajusta tests primero cuando sea posible.

Entregables:
- cambios de código mínimos y precisos
- tests nuevos/ajustados
- breve nota técnica en docs o comentario de PR con:
  - qué se cambió
  - por qué
  - riesgos
```

## Orden sugerido para Codex

1. Sprint 1
2. Sprint 2
3. Sprint 3
4. Sprint 4
5. Sprint 5
6. Sprint 6
7. Sprint 7
8. Sprint 8

La razón de este orden es que primero se estabiliza el **marco transversal de verdad** (scope/audit/events), luego el **núcleo financiero/control**, y recién después los kernels operativos aún más inmaduros o con frontera semántica pendiente

Si querés, en el siguiente paso te lo convierto a una **tabla PR por PR** con columnas: `sprint`, `PR title`, `archivos`, `tests`, `riesgo`, `rollback`.
