# MATRIZ AVANZADA DE ENDURECIMIENTO DE KERNELS — NECKTRAL
Version: v1.0
Fecha base de analisis: 2026-03-15
Fuente: repo Necktral/Necktral + documentos oficiales + código backend
Uso previsto: backlog estructural para Codex / implementación guiada
Base contractual vigente: `docs/CONTRACT_PACK_v1.1.md` (organización) + `docs/CONTRACT_PACK_v2.0.md` (Sync); `v1.0` queda histórico

---

## 0. Regla rectora del programa

**Objetivo principal**
Endurecer los kernels hasta convertirlos en fronteras de verdad con:
- ownership explícito,
- invariantes no bypassables,
- scope multiempresa/branch obligatorio,
- RBAC por método y scope,
- auditoría contractual verificable,
- contratos de integración estables,
- idempotencia / determinismo,
- pruebas y gates.

**Regla semántica principal**
> Una sola verdad operativa, una sola verdad financiera final y capas derivadas no competitivas.

**Fundamento en el repo**
- La arquitectura formal define los kernels de verdad, los módulos core y la jerarquía de verdad.  
- Billing, Inventory y Accounting están definidos como ejes de verdad.  
- CEC es control plane.  
- Payments & Cash es módulo core de primer nivel.  
- Shadow Ledger es proyección determinista previa al posting formal, no segunda contabilidad.

**Implicación**
No se debe endurecer “por código”, sino por **semántica + contratos + enforcement + evidencia**.

---

## 1. Hechos comprobados del repo (baseline real)

### 1.1 Lo que ya está fuerte
- Backend core Django/DRF maduro.
- IAM / auth con contexto multiempresa.
- RBAC con permisos granulares y enforcement en permisos DRF.
- Auditoría contractual con hash/HMAC.
- Sync engine offline-first ya operativo como precedente contractual.
- GL/Shadow/CEC/Fases F1–F12 cerradas en staging-first.

### 1.2 Lo que todavía NO está igual de fuerte
- Billing: el blueprint lo trata como kernel, pero el diagnóstico todavía lo considera parcial/scaffolding.
- Inventory: igual; target correcto, pero madurez real inferior a Accounting/IAM/Audit.
- Payments & Cash: arquitectónicamente reconocido, pero requiere congelar su frontera semántica con Accounting.
- Frontend existe, pero no es la base para endurecer kernels; el hardening es backend-first.

### 1.3 Consecuencia metodológica
El orden correcto es:
1. endurecer kernels/core backend,
2. formalizar reportes,
3. luego dashboard.

---

## 2. Criterios universales de endurecimiento (aplican a TODO kernel)

| ID | Criterio | Qué significa exactamente | Evidencia / cierre |
|---|---|---|---|
| HK-01 | Ownership explícito | El kernel declara qué posee y qué tiene prohibido tocar | ADR/documento + tests + API consistente |
| HK-02 | Invariantes no negociables | Reglas de dominio que nunca pueden romperse | tests unit/integration + rechazo contractual |
| HK-03 | Scope no-bypassable | Toda operación corre con `company` y `branch` válidos | auth/context + RBAC + tests |
| HK-04 | RBAC por método | lectura, escritura, aprobación, reversa, export separados | permisos por endpoint/método |
| HK-05 | Auditoría contractual | todo write relevante deja evento válido y verificable | event_type/reason_code/subject_type + cadena íntegra |
| HK-06 | Idempotencia | repetir comando/evento no altera semántica | dedupe + tests |
| HK-07 | Contratos inter-módulo | eventos/API con schema estable y versionado | contract tests |
| HK-08 | Reversibilidad | no delete histórico crítico; solo reversa / compensación | tests + restricciones de dominio |
| HK-09 | Determinismo | mismo input/version => mismo output derivado | manifests + replay + certification |
| HK-10 | Gates de promoción | el kernel no se “declara listo” sin evidencia | verify_* / certify_* / CI |

---

## 3. Matriz maestra por kernel / módulo core

---

## 3.1 IAM / Tenant / Policy Kernel

### Rol semántico
Fuente de verdad de:
- identidad,
- membresías,
- contexto efectivo,
- permisos,
- grants,
- SoD / aprobaciones.

### Estado real observado
**Fuerte / maduro.**
Hay autenticación JWT + contexto organizacional obligatorio; `X-Company-Id` es regla fuerte para endpoints operativos.  
Existe además `data_scope` para lecturas intercompany y una regla explícita que impide bypass de sucursal en la misma empresa.  
El backend usa `JWTAuthWithOrgContext` como clase por defecto de DRF.

### Acciones exactas de endurecimiento

#### IAM-01 — Unificar una sola vía oficial de contexto
**Acción**
Elegir `JWTAuthWithOrgContext` como mecanismo canónico y dejar `context_middleware` solo como precedente legado o fallback documentado.

**Por qué**
Hoy conviven dos capas con responsabilidad parecida:
- `apps.iam.authentication.JWTAuthWithOrgContext`
- `apps.iam.context_middleware.OrgContextMiddleware`

Eso sirve como precedente, pero a largo plazo introduce ambigüedad sobre “dónde se garantiza el contexto”.

**DoD**
- un único camino canónico documentado,
- tests que prueban contexto inyectado,
- middleware legado marcado como transitional/deprecated si no se usa.

#### IAM-02 — Hacer obligatorio el scope efectivo para todo endpoint operativo
**Acción**
Revisar que todo endpoint operativo:
- niegue si falta `X-Company-Id`,
- valide branch contra company,
- marque `required_scope` al denegar.

**Por qué**
La autenticación actual ya lo hace como regla fuerte.  
Endurecer significa llevarlo a “100% coverage”, no dejar excepciones silenciosas.

**DoD**
- test matrix por app/endpoint crítico,
- 400/403/404 consistentes,
- `required_scope` presente al denegar.

#### IAM-03 — Formalizar intercompany READ y bloquear WRITE intercompany por contrato
**Acción**
Documentar y testear que el modo intercompany actual es solo lectura, salvo un diseño futuro explícito.

**Por qué**
El código actual lo trata así: el `data_scope` intercompany se valida con grant en modo `READ`.  
No debe quedar semánticamente ambiguo.

**DoD**
- tests de grant READ,
- rechazo de mutaciones cross-company,
- contrato documentado.

#### IAM-04 — SoD operativo en operaciones sensibles
**Acción**
Extender/normalizar el modelo de aprobaciones y segregación de funciones para:
- cierre,
- posting,
- reversas,
- cambios de configuración crítica.

**Por qué**
El blueprint lo exige como invariante transversal, y Accounting ya incorpora SoD en fases avanzadas.  
Debe existir patrón reutilizable, no solo soluciones puntuales.

**DoD**
- catálogo de operaciones sensibles,
- hooks reutilizables,
- tests de conflicto actor/aprobador.

### Riesgo si no se hace
- fuga multiempresa,
- bypass de scope,
- ambigüedad en permisos,
- trazabilidad pobre en denegaciones.

### Prioridad
**P0**

---

## 3.2 Billing / Fiscal Document Kernel

### Rol semántico
Fuente de verdad de:
- documentos comerciales/fiscales,
- drafts,
- emisión,
- anulación,
- credit notes,
- linkage documental,
- numeración fiscal,
- impuestos.

### Estado real observado
**Objetivo correcto, madurez parcial.**
La arquitectura y roadmap lo reconocen como kernel reutilizable, pero el diagnóstico todavía lo marca como scaffolding/parcial.  
Sí existen flujos y tests de documento create/issue/void auditados.

### Acciones exactas de endurecimiento

#### BILL-01 — Consolidar el agregado documental real
**Acción**
Formalizar `BillingDocument` como agregado canónico con estados explícitos mínimos:
- `DRAFT`
- `ISSUABLE`
- `ISSUED`
- `VOIDED`
- `CREDITED` / `SUPERSEDED` si aplica

**Por qué**
Sin máquina de estados contractual, “emitir” y “anular” se vuelven endpoints, no semántica de dominio.

**DoD**
- enum de estados estable,
- transiciones válidas/inválidas probadas,
- auditoría por transición.

#### BILL-02 — Congelar invariantes fiscales/documentales
**Acción**
Imponer como invariantes:
- unicidad fiscal por scope,
- prohibición de issue sin líneas/totales válidos,
- prohibición de void sin motivo,
- linkage obligatorio en credit note/void si aplica por normativa.

**Por qué**
La arquitectura ya define unicidad fiscal como invariante no negociable.

**DoD**
- constraints + validadores + tests,
- códigos de error contractuales.

#### BILL-03 — Separar estrictamente Billing de stock/costo y journal final
**Acción**
Prohibir por diseño que Billing:
- mueva stock directamente,
- calcule costo de inventario,
- genere JournalEntry final.

**Por qué**
La arquitectura lo prohíbe explícitamente.  
Billing puede producir hechos operativos y eventos; no verdad de otros kernels.

**DoD**
- no imports/direct writes indebidos,
- integración vía eventos/links בלבד.

#### BILL-04 — Estandarizar idempotencia documental
**Acción**
Hacer obligatorio `idempotency_key` en create/issue/void críticos, con conflicto si payload cambia.

**Por qué**
La semántica documental no debe duplicarse por retry/red.

**DoD**
- requests duplicadas devuelven mismo resultado,
- conflictos se rechazan con código estable.

#### BILL-05 — Contrato de auditoría de documento
**Acción**
Congelar catálogo mínimo de eventos:
- `BILLING_DOC_CREATED`
- `BILLING_DOC_ISSUED`
- `BILLING_DOC_VOIDED`
- `BILLING_CREDIT_NOTE_ISSUED`
- `BILLING_DOC_EXPORTED` (si aplica)

**Por qué**
Hoy hay auditoría, pero el hardening exige taxonomía contractual completa y estable.

**DoD**
- contrato documentado,
- tests de eventos emitidos,
- validación de catálogo.

#### BILL-06 — Contrato de integración operativo-contable
**Acción**
Todo documento que deba impactar Accounting debe emitir evento canónico con:
- correlation/causation,
- contract_version,
- schema_version,
- scope,
- source identifiers estables.

**Por qué**
Accounting ya espera normalización de eventos operativos y link directo para BILLING.

**DoD**
- outbox bien formado,
- test de link a `EconomicEvent`,
- no dual-write.

### Riesgo si no se hace
- facturas sin semántica estable,
- inconsistencias fiscales,
- duplicación documental,
- imposibilidad de reportes reproducibles.

### Prioridad
**P0-P1**

---

## 3.3 Inventory / Cost Kernel

### Rol semántico
Fuente de verdad de:
- item master,
- UOM,
- almacenes,
- movimientos,
- ajustes,
- transferencias,
- costo.

### Estado real observado
**Objetivo correcto, madurez parcial.**
El Contract Pack v2 ya define un contrato fuerte para Inventory kernel: movimientos, ledger, balances, scope estricto, idempotencia y evento `INVENTORY_MOVEMENT_POSTED`.  
El diagnóstico general, sin embargo, todavía lo ubica como módulo con madurez inferior y pendientes funcionales.

### Acciones exactas de endurecimiento

#### INV-01 — Hacer de Movement la única fuente primaria
**Acción**
Definir que:
- el movimiento es la verdad,
- balances son proyección,
- ningún endpoint muta saldo directamente.

**Por qué**
El contract v2 y el roadmap ya empujan el kardex/movimiento como fuente de verdad.

**DoD**
- no existe update directo de stock sin movimiento,
- balances reconstruibles desde movimientos.

#### INV-02 — Congelar contrato mínimo de movimientos
**Acción**
Soportar formalmente:
- receive,
- issue,
- adjust,
- transfer

con permisos por método ya definidos y errores contractuales:
- `INVENTORY_INVALID_SCOPE`
- `INVENTORY_INSUFFICIENT_STOCK`
- `INVENTORY_IDEMPOTENCY_CONFLICT`
- `INVENTORY_SCHEMA_INVALID`

**Por qué**
Ese contrato ya existe en el pack v2; endurecer es hacerlo obligatorio en implementación y tests.

**DoD**
- endpoints vivos,
- serializer/DTO estable,
- errores contractuales consistentes.

#### INV-03 — No stock negativo por defecto
**Acción**
Rechazar salidas/ajustes que rompan stock, salvo política explícita de backorder futura.

**Por qué**
La arquitectura lo define como invariante no negociable.

**DoD**
- validación centralizada,
- tests de rechazo,
- no “silent negative”.

#### INV-04 — Política de costo versionada
**Acción**
Congelar método de valuación y su versionado por ciclo/scope.  
No permitir cambios “transparentes” de promedio/FIFO/etc. sin evidencia.

**Por qué**
La arquitectura lo lista como decisión a congelar ahora.

**DoD**
- configuración versionada,
- metadatos de costo en movimientos/proyecciones,
- tests de estabilidad.

#### INV-05 — Ledger ordenado y paginado de forma estable
**Acción**
Mantener orden estable y paginación obligatoria en ledger/balances.

**Por qué**
El contract v2 lo exige; eso es parte del hardening, no una optimización opcional.

**DoD**
- `GET /ledger` y `GET /balances` con orden estable,
- límites máximos configurados,
- tests de paginación.

#### INV-06 — Integración con FUEL y Billing sin romper ownership
**Acción**
Permitir que Fuel/Billing disparen hechos que terminen en movimiento de inventario, pero sin que esos módulos muten inventario por fuera del kernel.

**Por qué**
El diagnóstico y changelog muestran que esa integración es necesaria, pero no debe romper ownership.

**DoD**
- servicio/adaptador explícito,
- correlation_id estable,
- evento + auditoría.

### Riesgo si no se hace
- saldos arbitrarios,
- costo inconsistente,
- imposibilidad de reproducir balances,
- verticales manipulando stock por fuera del kernel.

### Prioridad
**P0-P1**

---

## 3.4 Payments & Cash Module (módulo core de primer nivel)

### Rol semántico
Fuente de verdad de:
- intents,
- autorizaciones/capturas/refunds,
- conciliación provider,
- cash sessions,
- diferencias de caja.

### Estado real observado
**Arquitectónicamente reconocido, semántica aún por congelar.**
La arquitectura lo eleva a módulo core de primer nivel.  
El código contable ya soporta eventos PAYMENTS como `CashMovementPosted` y `CashSessionClosed`, pero el link operacional directo a accounting hoy está habilitado explícitamente solo para BILLING e INVENTORY.

### Acciones exactas de endurecimiento

#### PAY-01 — Congelar catálogo semántico de hechos de caja/pago
**Acción**
Definir catálogo mínimo:
- `PAYMENT_INTENDED`
- `PAYMENT_AUTHORIZED`
- `PAYMENT_CAPTURED`
- `PAYMENT_REFUNDED`
- `CASH_MOVEMENT_POSTED`
- `CASH_SESSION_CLOSED`
- `CASH_DIFFERENCE_DETECTED`

**Por qué**
Sin esto, caja/pago se vuelve “estado técnico” y no dominio operativo estable.

**DoD**
- catálogo documentado,
- auditoría contractual,
- payload mínimo definido.

#### PAY-02 — Decidir qué entra a Accounting en write-time y qué entra en close-time
**Acción**
Separar formalmente:
- eventos que generan `EconomicEvent` inmediato,
- eventos que solo se consideran en cierre/proyección,
- eventos puramente operativos sin impacto financiero directo.

**Por qué**
Hoy el código contable muestra una frontera mixta: PAYMENTS está en `SUPPORTED_ECONOMIC_EVENTS`, pero no en `OPERATIONAL_ACCOUNTING_EVENTS`.

**DoD**
- tabla de mapeo congelada,
- tests por tipo de evento,
- eliminación de ambigüedad.

#### PAY-03 — CashSession como agregado duro
**Acción**
Definir estados explícitos:
- `OPEN`
- `COUNT_PENDING`
- `REVIEW_PENDING`
- `CLOSED`
- `REOPENED_FOR_INVESTIGATION`

**Por qué**
La arquitectura ya propone esa máquina de estados base.

**DoD**
- transiciones con permisos,
- diferencia de caja tratada como excepción/hecho visible,
- auditoría completa.

#### PAY-04 — Conciliación provider separada del journal final
**Acción**
La conciliación de provider debe existir en Payments/Cash; el asiento final pertenece a Accounting.

**Por qué**
La arquitectura prohíbe que Payments/Cash posea journal final.

**DoD**
- modelos/servicios separados,
- cero posting final desde Payments.

### Riesgo si no se hace
- caja ambigua,
- diferencias no explicables,
- contabilidad inconsistente entre operación y cierre.

### Prioridad
**P1**

---

## 3.5 Accounting Kernel

### Rol semántico
Fuente de verdad de:
- `EconomicEvent`
- `PostingRuleSet`
- `JournalDraft`
- `JournalEntry`
- period close
- revaluation
- GL formal

### Estado real observado
**Fuerte / avanzado.**
La arquitectura y `contexto_nucleos` muestran F4–F12 cerradas en staging-first, incluyendo Shadow Ledger, posting controlado, GL formal, intercompany y cierre mensual continuo.  
El código ya refleja soporte real para:
- runtime de posting operacional,
- selección de rule sets activos,
- proyección shadow,
- posting,
- eventos `JournalPosted`,
- excepciones CEC asociadas.

### Acciones exactas de endurecimiento

#### ACC-01 — Congelar `PostingRuleSet v1`
**Acción**
Dejar estable:
- scope,
- vigencia,
- fiscal mode,
- versión,
- precedencia,
- estrategia de matching.

**Por qué**
La arquitectura lo pone en “decisiones a congelar ahora”; el código ya depende de selección activa por scope/fecha/mode.

**DoD**
- contrato publicado,
- fixtures oficiales,
- tests de selección determinista.

#### ACC-02 — Hacer explícita la tabla oficial de eventos soportados
**Acción**
Congelar la lista de eventos aceptados en:
- shadow projection,
- operational link,
- period close gate.

**Por qué**
Hoy el código ya tiene `SUPPORTED_ECONOMIC_EVENTS` y `OPERATIONAL_ACCOUNTING_EVENTS`; falta tratarlos como contrato formal.

**DoD**
- tabla documentada,
- tests de `UNSUPPORTED` / `DISABLED`,
- cambio controlado por versión.

#### ACC-03 — Determinismo fuerte de Shadow Ledger
**Acción**
Toda proyección debe depender de:
- normalized event,
- `contract_version`,
- `schema_version`,
- `rule_set_version`,
- `input_manifest_hash`.

**Por qué**
La arquitectura lo exige; el código ya guarda esos datos y abre excepciones si faltan reglas o si el draft es inválido.

**DoD**
- replay produce mismo resultado,
- manifest reproducible,
- exceptions bien categorizadas.

#### ACC-04 — JournalDraft nunca posteable si viola invariantes
**Acción**
Bloquear posting si:
- no balancea,
- período está cerrado,
- falta línea requerida,
- falla SoD,
- faltan aprobaciones.

**Por qué**
Parte de esto ya existe en el código y tests; endurecer es completarlo y no permitir bypasses.

**DoD**
- test suite exhaustiva,
- códigos de error estables,
- rollback seguro.

#### ACC-05 — JournalEntryLine formal obligatorio
**Acción**
No considerar GL “cerrado” sin líneas completas, no solo totales agregados.

**Por qué**
El plan operativo F7A ya habla de GL formal con COA, líneas y reportes financieros; el hardening debe asumir eso como baseline.

**DoD**
- `ensure_journal_entry_lines()` cubierto,
- reportes basados en líneas reales.

#### ACC-06 — Cierre de período como gate sistémico real
**Acción**
Integrar en close:
- outbox health,
- drafts abiertos,
- reconciliación,
- excepciones blocking,
- SoD.

**Por qué**
El repo ya tiene gates y toolchain; debe seguir siendo regla, no “modo manual”.

**DoD**
- `verify_*` en PASS,
- artifacts firmados,
- no close si hay blocking.

### Riesgo si no se hace
- GL no confiable,
- proyección no reproducible,
- cierres opinables,
- reportes inseguros.

### Prioridad
**P0**

---

## 3.6 CEC Control Plane (no kernel de verdad, pero crítico para hardening)

### Rol semántico
Control plane de:
- validación,
- reconciliación,
- evidencia,
- exceptions,
- manifests,
- gates,
- close orchestration.

### Estado real observado
**Fuerte en diseño y ejecución staged.**
La arquitectura y fases cerradas muestran CEC como pieza central de cierre y control.

### Acciones exactas de endurecimiento

#### CEC-01 — Prohibición explícita de mutar verdad primaria
**Acción**
Mantener y testear que CEC:
- no re-numera documentos,
- no ajusta stock,
- no postea journal por su cuenta.

**Por qué**
La arquitectura lo prohíbe literalmente.

**DoD**
- sin writes indebidos,
- orquestación pura,
- excepciones en vez de “arreglos”.

#### CEC-02 — Modelo de excepción y evidencia congelado
**Acción**
Formalizar:
- fingerprint,
- severity,
- blocking,
- related_object,
- lifecycle de excepción.

**Por qué**
Accounting ya usa `CECException` como mecanismo de bloqueo/proyección.

**DoD**
- catálogo de excepciones por módulo,
- dedupe fiable,
- evidencia hashada.

#### CEC-03 — Run manifests y health gates como artefacto obligatorio
**Acción**
Todo cierre/rerun crítico debe producir:
- output manifest,
- hash,
- resumen,
- gate result.

**Por qué**
Tu operación F4–F12 ya se apoya en manifests y certify/verify scripts.

**DoD**
- runner canónico,
- artefactos firmados,
- comparación de manifests.

### Riesgo si no se hace
- cierres no reproducibles,
- “fix manual” fuera de control,
- pérdida de trazabilidad.

### Prioridad
**P0**

---

## 3.7 Integration / Event Backbone (módulo core crítico)

### Rol semántico
No es kernel de verdad, pero es infraestructura semántica obligatoria para endurecer kernels.

### Acciones exactas de endurecimiento

#### INT-01 — Outbox transaccional real
**Acción**
Todo cambio de dominio que deba emitirse a otros contextos debe persistir evento en la misma TX.

**Por qué**
Está listado como mejora explícita en `FUTURAS_MEJORAS.md`.

**DoD**
- no dual-write,
- retry seguro,
- visibilidad operativa.

#### INT-02 — Inbox/replay/dedupe formal
**Acción**
Consumo idempotente con:
- consumer fijo,
- status,
- retries,
- dedupe por `event_id`.

**Por qué**
Sin esto no hay consistencia eventual segura.

**DoD**
- reproceso sin duplicación,
- métricas por estado,
- tests de replay.

#### INT-03 — Envelope canónico congelado
**Acción**
Todos los eventos inter-módulo usan el mismo sobre mínimo.

**Por qué**
La arquitectura lo exige y Accounting ya depende de normalización consistente.

**DoD**
- contract tests,
- schema versionado.

### Riesgo si no se hace
- integración frágil,
- eventos inconsistentes,
- proyecciones duplicadas o perdidas.

### Prioridad
**P0**

---

## 4. Matriz de priorización real (orden recomendado)

| Orden | Bloque | Justificación |
|---|---|---|
| 1 | IAM / Scope / RBAC / Audit | Sin esto no existe verdad multiempresa confiable |
| 2 | Integration Backbone (Outbox/Inbox/Envelope) | Sin esto los kernels no se integran de forma segura |
| 3 | Accounting | Ya está fuerte; congelarlo primero da base a reportes y control |
| 4 | CEC | Cierra reproducibilidad y control de run/cierre |
| 5 | Billing | Kernel correcto pero aún necesita endurecimiento semántico |
| 6 | Inventory | Igual que Billing; debe pasar de scaffolding a verdad basada en movimientos |
| 7 | Payments & Cash | Formalizar frontera con Accounting y caja operativa |
| 8 | Reportes | Después de endurecer verdad y control |
| 9 | Dashboard | Solo consumidor, no fuente de verdad |

---

## 5. Reglas operativas para Codex

### 5.1 Qué SÍ puede tocar
- tests,
- contratos,
- validadores,
- serializers/DTOs,
- permisos,
- eventos,
- wiring de auditoría,
- runbooks/checklists/ADR técnicos,
- servicios de dominio,
- migrations si son estrictamente necesarias.

### 5.2 Qué NO debe inventar
- nuevos ownerships de dominio,
- posting rules “de ejemplo” sin aprobación,
- estados de negocio no documentados,
- integraciones directas que violen ownership,
- cálculos financieros finales fuera de Accounting.

### 5.3 Política de implementación
- PRs pequeños, por kernel.
- Cada PR debe cerrar:
  - contrato,
  - enforcement,
  - test,
  - evidencia mínima.
- Ningún hardening se marca “completo” sin DoD verificable.

---

## 6. Template de trabajo por kernel (para Codex)

## [NOMBRE_DEL_KERNEL]

### Objetivo semántico
- ...

### Hechos actuales del repo
- ...
- ...

### Gaps reales
- ...
- ...

### Acciones exactas
1. ...
2. ...
3. ...

### Contratos a congelar
- ...
- ...

### Tests obligatorios
- unit:
- integration:
- contract:
- regression:

### Riesgo si no se hace
- ...

### DoD
- ...
- ...

---

## 7. Conclusión ejecutiva

El endurecimiento de kernels en Necktral no debe entenderse como “completar features”.
Debe entenderse como:

> **convertir los dominios núcleo en verdades operativas/financieras con fronteras semánticas, invariantes, auditoría, scope, contratos y determinismo comprobable.**

En el estado actual del repo:
- **IAM / RBAC / Audit / Sync / Accounting / CEC** ya ofrecen una base fuerte.
- **Billing** e **Inventory** son los dos núcleos que más necesitan pasar de intención arquitectónica a verdad endurecida.
- **Payments & Cash** necesita congelación semántica formal antes de Reportes/Dashboard.

---

## 8. Siguiente paso recomendado

Generar cuatro PRDs/ADR técnicos consecutivos:

1. `ADR_KERNEL_HARDENING_IAM_SCOPE_AUDIT.md`
2. `ADR_KERNEL_HARDENING_ACCOUNTING_CEC.md`
3. `ADR_KERNEL_HARDENING_BILLING.md`
4. `ADR_KERNEL_HARDENING_INVENTORY_PAYMENTS.md`

y luego recién:

5. `ADR_REPORTES_TRANSVERSAL.md`
6. `ADR_DASHBOARD_COMPOSITIONAL.md`
