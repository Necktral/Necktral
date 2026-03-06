# Contract Pack v1.0 — Guía contractual del sistema

Versión: v1.0  
Fecha: 2026-01-26  
Estado: **Guía de organización (viva)**

## Propósito

Este documento define el **contrato de organización** del ERP/CRM: cómo deben comportarse los kernels y módulos para que el sistema sea consistente, auditable, multiempresa y operable con QA determinista.

- Es una **guía normativa** para diseño e implementación.
- Debe mantenerse alineada con el código (auditoría contractual, RBAC y sync engine).

## Alcance

- Kernels (dominio transversal): facturación, inventarios, cuentas por cobrar/pagar, tesorería, etc.
- Módulos operativos (verticales): p.ej. Estación de Servicios (FUEL).
- Contratos transversales: auditoría, seguridad/RBAC, multiempresa, sync/offline.

## Convenciones del repositorio

- Todo en español.
- Preferencia por servicios de dominio + serializers/DTOs explícitos.
- QA como “puerta” (gates) y CI determinista.

## Contratos transversales (base actual del repo)

### 1) Multiempresa (scope)

- El backend opera en un contexto de **company** y, opcionalmente, **branch**.
- El scope efectivo se aplica en permisos y queries.

> Nota: el detalle exacto de headers y reglas debe mantenerse consistente con el backend.

### 2) Autorización (RBAC)

- Los endpoints deben aplicar permisos por método (lectura/escritura separadas).
- El catálogo estándar vive en `seed_rbac_v01`.

### 3) Auditoría contractual (invariante)

- Los endpoints de escritura deben emitir eventos con:
  - `event_type` permitido por contrato.
  - `reason_code` permitido.
  - `subject_type` permitido.
- La integridad es encadenada por hash y firmada con HMAC en PROD.

Referencias del repo:

- Contrato de eventos/subjects/reasons: `backend/src/apps/audit/contracts.py`
- Verificación de integridad: `backend/src/apps/audit/management/commands/audit_verify_chain.py`

### 4) Sync / Offline (precedente)

Existe un precedente implementado para sincronización por lotes con:

- firma Ed25519 por comando,
- canonicalización determinista,
- idempotencia por `command_id`.

Referencias del repo:

- API/serialización: `backend/src/apps/sync_engine/serializers.py`
- Vistas: `backend/src/apps/sync_engine/views.py`

## Kernels y módulos

### Kernels (objetivo)

Este repositorio está preparado para crecer a kernels (Billing, Inventory, AR/AP, Treasury). El contrato de organización define:

- Fronteras de responsabilidad (qué pertenece a cada kernel).
- Tipos de documentos/estados y sus transiciones.
- Reglas de auditoría por operación.
- Reglas de sync/outbox cuando aplique.

## Sección normativa: Kernels (objetivo)

### Palabras normativas

- **MUST / DEBE**: invariante contractual (si se incumple, es bug y el PR no se integra).
- **MUST NOT / NO DEBE**: prohibición contractual.
- **SHOULD / CONVIENE**: recomendación fuerte (se puede excepcionar con justificación y test).
- **MAY / PUEDE**: opcional.

### Glosario mínimo

- **company**: tenant operativo. La mayoría de reglas se evalúan dentro del scope de company.
- **branch**: sub-scope opcional dentro de company.
- **scope**: combinación efectiva de `company` + `branch` que restringe permisos y queries.
- **kernel**: dominio transversal (p.ej. Billing, Inventory) reutilizable por múltiples módulos.
- **módulo vertical**: dominio “vertical” de operación (p.ej. FUEL) que consume kernels y agrega lógica específica.
- **evento de auditoría**: registro append-only con integridad (hash + firma + encadenamiento por partición).
- **comando**: unidad de sincronización; representa un cambio (intención/acción), no un “estado final”.

### A) Contrato transversal: Multiempresa (Scope) + propagación de contexto

1. **Contexto de request**

- Todo endpoint opera con un contexto efectivo de **company** y opcionalmente **branch**.
- El contexto se usa para:
  - enforcement de permisos (RBAC),
  - filtrado de queries,
  - particionamiento de auditoría.
- La auditoría **DEBE** derivar `partition_key` por company cuando existe, o `SYSTEM` cuando no existe contexto.

2. **Auditoría enriquecida con scope**

- Cuando existe `company`/`branch` en request, el writer **DEBE** agregar `company_id` y `branch_id` dentro de `metadata`.
- Por contrato, endpoints de escritura **DEBEN** asegurar que el request tenga contexto correcto para que auditoría y permisos queden alineados.

### B) Contrato transversal: Auditoría contractual (EAU v1 como etiqueta interna)

> Nota: el repo usa la sigla “EAU v1” como etiqueta interna del contrato del writer.

1. **Invariantes de integridad**

- El payload de auditoría se canonicaliza como JSON determinista (orden estable de keys, separadores sin espacios).
- Se calcula `event_hash = SHA256(payload_canónico)`.
- Se calcula `signature = HMAC(event_hash)` con `AUDIT_HMAC_KEY`.
- El encadenamiento se hace por partición (`prev_event_hash`) y se mantiene cabeza de cadena por partición.

2. **Schema mínimo del evento (campos críticos)**

El writer construye un payload con campos contractuales que el sistema considera “fuente de verdad”. Ejemplos de campos presentes en el payload canónico:

- `schema_version`, `module`, `event_type`, `reason_code`
- `subject_type`, `subject_id`
- `partition_key`
- `timestamp_server`
- `actor_user_id`, `device_id`
- `ip_server_seen`, `offline_mode`
- `path`, `method`, `user_agent`
- `before_snapshot`, `after_snapshot`
- `metadata`
- `prev_event_hash`

3. **Regla de oro**

- Todo endpoint que **cambie estado** (write) **DEBE** emitir evento de auditoría.
- Todo evento **DEBE** cumplir catálogos contractuales: `event_type`, `reason_code`, `subject_type`.

### C) Contrato transversal: Catálogos contractuales (event_type / reason_code / subject_type)

1. **Validación estricta**

- `event_type` **DEBE** pertenecer a `ALLOWED_EVENT_TYPES` o el sistema falla.
- `reason_code` vacío es permitido; si no es vacío, **DEBE** pertenecer a `ALLOWED_REASON_CODES`.
- `subject_type` **DEBE** pertenecer a `ALLOWED_SUBJECT_TYPES`.

2. **Taxonomía ya reservada por el repo**

El contrato ya incluye tipos para AUTH, SYNC, RBAC, ORG, HR, FUEL, INVENTORY y BILLING. Ejemplos:

- SYNC: `SYNC_BATCH_RECEIVED`, `SYNC_COMMAND_APPLIED`, `SYNC_COMMAND_REJECTED`, `SYNC_COMMAND_DUPLICATE`
- FUEL: `FUEL_SHIFT_OPENED`, `FUEL_SALE_CREATED`, `FUEL_INTERCOMPANY_OUTBOX_ENQUEUED`

3. **Regla de evolución**

- Cambios aditivos (agregar nuevos `event_type`/`reason_code`/`subject_type`) son aceptables si vienen con tests y documentación.
- Cambios breaking (renombrar/eliminar) requieren bump de versión contractual, migración y actualización de verificación.

### D) Contrato transversal: Sync / Offline (precedente implementado)

1. **Unidad de sync = comando**

- La sincronización viaja como **comandos** firmados, idempotentes por `command_id`.

2. **Firma determinista**

- `occurred_at` se canonicaliza a UTC con microsegundos para firma determinista.
- El mensaje firmado **NO es JSON**: es una concatenación estable con separador `|`:
  - `command_id|command_type|company_id|branch_id|occurred_at|sequence|payload_hash|prev_hash`

3. **Política operativa (límites duros)**

La policy del servicio define límites contractuales:

- `max_commands_per_batch = 100` (configurable por `SYNC_MAX_COMMANDS_PER_BATCH`)
- `max_payload_bytes = 64000` (configurable por `SYNC_MAX_PAYLOAD_BYTES`)
- `max_device_clock_skew_seconds = 6 horas` (configurable por `SYNC_MAX_DEVICE_CLOCK_SKEW_SECONDS`)

4. **Auditoría de sync**

Los resultados de sync se expresan en auditoría usando event_types permitidos por contrato (`SYNC_BATCH_RECEIVED`, `SYNC_COMMAND_APPLIED`, `SYNC_COMMAND_REJECTED`, `SYNC_COMMAND_DUPLICATE`) y reason_codes específicos de sync (por ejemplo `SYNC_INVALID_SIGNATURE`, `SYNC_LIMIT_EXCEEDED`, `SYNC_TIME_SKEW`).

### E) Cierre contractual: qué se considera “hecho”

Un kernel/módulo se considera “integrado” cuando:

1. sus endpoints aplican scope y RBAC;
2. cada operación write emite auditoría contractual (catálogos + hash + firma + encadenamiento);
3. si aplica offline/sync, define comandos versionados y respeta idempotencia;
4. todo lo anterior queda cubierto por tests (QA Gates).

### Módulos verticales (ejemplo: FUEL)

- Deben integrarse con contratos transversales (RBAC, auditoría contractual, scope).
- Reportes y cierres deben ser reproducibles y auditables.

### F) Contrato transversal: Errores y códigos (API) — v1.0

1. **Envelope único**

Toda respuesta de error (HTTP >= 400) **DEBE** usar el siguiente formato:

```json
{
  "error": {
    "code": "<STRING>",
    "http_status": 422,
    "message": "<STRING>",
    "details": { "<OBJECT>": "..." },
    "retryable": false,
    "request_id": "<STRING>",
    "timestamp": "<RFC3339 UTC>"
  }
}
```

2. **request_id (trazabilidad)**

- El backend **DEBE** propagar y devolver `X-Request-Id`.
- Si el cliente no lo envía, el backend **DEBE** generar uno.
- `error.request_id` **DEBE** coincidir con el header `X-Request-Id`.

3. **retryable (reintento)**

- `error.retryable` **DEBE** ser `true` solo cuando el cliente puede reintentar sin cambios semánticos.
- En v1.0 se define como:
  - `true` para `429` (rate limit) y `503` (service unavailable)
  - `false` en el resto

4. **Regla de `details`**

- `error.details` **DEBE** ser siempre un objeto JSON.
- Para validaciones (`422`):
  - `details.fields`: mapa `campo -> [mensajes]`
  - `details.non_field_errors`: lista de mensajes generales

Ejemplo de validación:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "http_status": 422,
    "message": "Validación fallida.",
    "details": {
      "fields": { "email": ["Formato inválido."] },
      "non_field_errors": []
    },
    "retryable": false,
    "request_id": "...",
    "timestamp": "..."
  }
}
```

5. **Tabla de códigos (v1.0)**

- `400`: `BAD_REQUEST`
- `401`:
  - `AUTH_UNAUTHENTICATED` (falta credencial)
  - `AUTH_INVALID_TOKEN` (token inválido)
  - `AUTH_TOKEN_EXPIRED` (token expirado)
- `403`:
  - `RBAC_FORBIDDEN` (permiso faltante)
  - `SCOPE_FORBIDDEN` (scope/tenant incorrecto)
- `404`: `NOT_FOUND`
- `409`: `CONFLICT`
- `422`: `VALIDATION_ERROR`
- `429`: `RATE_LIMITED`
- `503`: `SERVICE_UNAVAILABLE`
- `5xx`: `INTERNAL_ERROR`

6. **Hints de diagnóstico (opcionales)**

- `RBAC_FORBIDDEN` puede incluir `details.missing_permissions`.
- `SCOPE_FORBIDDEN` puede incluir `details.required_scope` y `details.effective_scope`.

### G) Seguridad operativa: rotación de secretos y throttling

1. **Rotación de secretos (política técnica)**

- El backend **DEBE** soportar modo dual durante la rotación (clave actual + clave previa).
- La ventana de rotación **DEBE** estar definida y ser auditable.
- Debe existir un procedimiento de rollback (volver a clave previa) sin downtime.

2. **Throttling (rate limit) coherente**

- La API **DEBE** aplicar límites globales mínimos (anon/user) y límites por endpoint sensible.
- Endpoints de alto costo (auth/sync/admin writes/heavy reads) **DEBEN** usar scopes dedicados.
- Respuestas 429 **DEBEN** usar el envelope contractual y `retryable=true`.

## Estado actual en este repo (resumen)

- Implementado: ORG/HR/RBAC + auditoría contractual.
- Implementado: sync engine (precedente) para dispositivos.
- Implementado: módulo FUEL (base + endpoints operativos/reportes según MVP).
- Implementado: kernels de facturación e inventarios como apps reales.

## CI/QA (gates)

- CI principal: `.github/workflows/qa-ci.yml` (QA CI Gates 1–3)
- Snapshot/reporting: `.github/workflows/pm-snapshot.yml` (PM Snapshot)

---

Si vas a modificar este documento: mantener la versión y agregar un changelog breve al final.

## Changelog

- 2026-01-28: Se completó la sección normativa (Kernels) con el texto contractual completo.
- 2026-01-28: Se agregó el contrato transversal de errores API (envelope + `X-Request-Id`).
