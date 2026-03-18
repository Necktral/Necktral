# Addendum Offline-first v1.0 — Sync, idempotencia y auditoría offline

Versión: v1.0  
Fecha: 2026-01-26  
Estado: **Guía de organización (viva)**

## Propósito

Definir reglas para operación con móviles **con o sin internet**, garantizando:

- consistencia (idempotencia y deduplicación),
- seguridad (firma/verificación),
- trazabilidad (auditoría contractual),
- límites operativos (tamaños, batches, tolerancias).

## Precedente existente en el repo (lo que ya está implementado)

El repo ya incluye un motor de sync (`sync_engine`) con un contrato claro:

- Enrollment: basado en sesión/JWT y scope.
- Batch: autenticación por dispositivo + firma Ed25519 por comando.
- Mensaje de firma determinista (sin ambigüedad JSON).
- Idempotencia por `command_id`.

Referencias del repo:

- Serializers y contrato: `backend/src/apps/sync_engine/serializers.py`
- Vistas: `backend/src/apps/sync_engine/views.py`
- Servicios/idempotencia: `backend/src/apps/sync_engine/services.py`

## Contrato offline-first (normativo)

### 1) Comandos como unidad de sincronización

- Cada cambio de estado en el dominio viaja como **comando** (no como “estado final”).
- Cada comando debe tener:
  - `command_id` (idempotencia)
  - `occurred_at` (tiempo del dispositivo, canonizado)
  - `payload` (schema validable)
  - `signature` (Ed25519)

### 2) Idempotencia y deduplicación

- El servidor debe tratar `command_id` como clave única.
- Reintentos por mala red deben resultar en **DUPLICATE** sin aplicar dos veces.

### 3) Lotes (batch)

- El cliente envía lotes acotados por tamaño y cantidad.
- El servidor devuelve un receipt con conteos y resumen de errores.

> Nota: los límites exactos deben mantenerse consistentes con la policy del backend.

### 4) Auditoría

- Operaciones aplicadas/rechazadas deben quedar trazadas.
- Si un comando genera efectos en un kernel/módulo, debe emitir los eventos contractuales correspondientes.

Referencia del contrato de auditoría:

- `backend/src/apps/audit/contracts.py`

## Extensiones recomendadas (pendientes / por implementar)

Estas extensiones son típicas en offline-first y están contempladas como guía de evolución:

- `device_seq`: secuencia monotónica por dispositivo para detectar huecos.
- Outbox de integración: cola de eventos/deltas entre módulos o hacia terceros.
- Quarantine: bloqueo temporal de dispositivos con comportamiento anómalo.

## Texto normativo completo

### A) Modelo mental: “offline-first” como degradación controlada

- El móvil **PUEDE** operar sin internet, pero el sistema **DEBE** preservar:
  1. idempotencia (no duplicar efectos),
  2. seguridad (firma verificable),
  3. trazabilidad (auditoría contractual),
  4. límites (no aceptar batches/payloads fuera de policy).

### B) Contrato de comandos (lo que el servidor espera, y lo que el cliente garantiza)

1. **Campos de identidad e idempotencia**

- `command_id`: identificador único global (clave de deduplicación).
- `command_type`: nombre estable, versionable.
- `company_id` y `branch_id` (branch puede ser vacío/None).
- `occurred_at`: timestamp del dispositivo (se canoniza a UTC con microsegundos para firma determinista).
- `payload_hash`: SHA-256 del payload canónico (determinista).
- `prev_hash`: vínculo con el comando anterior (si se usa chaining; si no, vacío).
- `sequence`: opcional (si existe, debe ser monotónico por dispositivo; si no existe, vacío/None).

2. **Regla de firma**

- Mensaje firmado (bytes) con separador `|` y sin JSON:
  - `command_id|command_type|company_id|branch_id|occurred_at|sequence|payload_hash|prev_hash`

3. **Verificación**

- La verificación usa Ed25519 (clave pública 32 bytes, firma 64 bytes). Firma inválida implica rechazo.

### C) Contrato de “receipt” (respuesta del batch)

Para cada batch, el servidor retorna:

- conteos agregados,
- resultado por `command_id` con estado:
  - `APPLIED`: aplicado y persistido,
  - `DUPLICATE`: ya existía (idempotencia),
  - `REJECTED`: no aplicable por política, firma, schema o scope.

- El estado `REJECTED` **DEBE** venir acompañado por un `reason_code` de sync permitido por contrato (ejemplos: `SYNC_INVALID_SIGNATURE`, `SYNC_SCHEMA_INVALID`, `SYNC_FORBIDDEN_SCOPE`, `SYNC_LIMIT_EXCEEDED`, `SYNC_TIME_SKEW`).

### D) Límites duros (policy) y su racionalidad

El backend define límites contractuales que el cliente debe respetar:

- máximo 100 comandos por batch,
- máximo 64 KB por comando/payload (`max_payload_bytes`),
- tolerancia de skew temporal de 6 horas.

Reglas:

- Si un batch excede límites, el servidor puede rechazar parcial o totalmente, pero **DEBE** reportar `reason_code` consistente (`SYNC_LIMIT_EXCEEDED` o equivalente permitido por el catálogo).

### E) Auditoría de sync (trazabilidad obligatoria)

- Cada batch recibido debe dejar rastro: `SYNC_BATCH_RECEIVED`.
- Cada comando debe quedar trazado como:
  - `SYNC_COMMAND_APPLIED` (aplicado),
  - `SYNC_COMMAND_DUPLICATE` (idempotente/deduplicado),
  - `SYNC_COMMAND_REJECTED` (rechazado).
- Los `reason_code` de error deben venir del catálogo permitido.

### F) Extensiones recomendadas (evolución prevista por el repo)

El roadmap del repo contempla extensiones típicas del offline-first:

- `device_seq` monotónico por dispositivo, detección de huecos, y estrategias de recuperación,
- cuarentena/revocación automática ante anomalías (firma inválida repetida, skew extremo),
- outbox transaccional de integración y reprocesamiento idempotente.

Norma de diseño para estas extensiones:

- deben ser observables (visible para gerencia/operación),
- deben ser auditables (eventos contractuales),
- deben ser idempotentes (reintentos seguros).

## Checklist para nuevos kernels (Billing/Inventory/...)

- Definir comandos y schemas (versionados).
- Asegurar idempotencia por `command_id`.
- Emitir auditoría contractual por operación.
- Respetar scope multiempresa.
- Añadir tests de sync + auditoría en el estilo existente.

---

Si vas a modificar este documento: mantener la versión y agregar un changelog breve al final.

## Changelog

- 2026-01-28: Se completó la sección normativa offline-first (comandos, firma, receipt, policy y auditoría).
