# Contract Pack v2.0 — Sync v2 canónico (unificado)

Versión: v2.0  
Fecha: 2026-01-31  
Estado: **Contrato canónico vigente**

## Propósito

Este documento define el **contrato canónico Sync v2**. Todo lo demás (v1.0) sigue vigente para contratos transversales no relacionados con sync y se considera base. Cuando exista divergencia, **v2.0 manda** para Sync.

Referencias:

- Base contractual general: `docs/CONTRACT_PACK_v1.0.md`
- Auditoría contractual: `backend/src/apps/audit/contracts.py`

---

## 1) Endpoint canónico

- **POST /api/sync/batch/** con `protocol_version = "2"`.
- Endpoints legacy (`/api/sync-hmac/batch/` y rutas v1) son **wrappers** que traducen a v2 y no contienen lógica de negocio.

### 1.1) Estado de implementación (sync_engine actual)

En el backend actual (`apps.sync_engine`), el endpoint expuesto **/api/sync/batch/** procesa un batch con firma **por comando** (Ed25519). El request esperado por el core es:

- `batch_id` (UUID)
- `device_id` (UUID) — header `X-Device-Id` tiene prioridad
- `sent_at` (ISO8601, opcional)
- `commands` (lista)

Cada comando usa:

- `command_id`, `command_type`
- `company_id`, `branch_id`
- `occurred_at`, `sequence`
- `payload`, `payload_hash`, `prev_hash`
- `signature` (firma Ed25519 por comando)

El esquema **request-level** con `protocol_version/ts/nonce/auth` aplica a wrappers legacy y aún no está integrado en el core `sync_engine`.

---

## 2) Request v2 (schema obligatorio)

Campos obligatorios:

- `protocol_version`: "2"
- `device_id`: UUID
- `ts`: unix epoch (segundos)
- `nonce`: string único por request
- `auth`: `{ scheme, signature, key_id? }`
  - `scheme`: `hmac` | `ed25519`
  - `signature`: base64
  - `key_id`: opcional (rotación)
- `batch_id`: UUID
- `batch`: lista de comandos

Comando (mínimo):

- `command_id`: UUID
- `type`: string
- `scope`: `{ company_id, branch_id }`
- `occurred_at`: ISO8601
- `payload`: objeto

Campos opcionales:

- `payload_hash`: sha256 hex
- `sequence`: int
- `prev_hash`: string
- `command_sig`: base64 (firma por comando, opcional)

---

## 3) Canonicalización y string‑to‑sign unificado

**Body canónico**: JSON ordenado por keys, separadores `,` `:`, sin espacios, UTF‑8.

`string_to_sign = f"{ts}.{nonce}.{sha256(canonical_json(body_sin_signature))}"`

- `scheme == hmac` → `signature = HMAC(shared_secret, string_to_sign)`
- `scheme == ed25519` → `signature = Ed25519.sign(private_key, string_to_sign)`

---

## 4) Anti‑replay (invariante)

Orden obligatorio:

1. Validar ventana temporal.
2. Verificar firma.
3. Persistir nonce (único por device).
4. Si hay colisión → `REPLAY_DETECTED`.

**Constraint**: unicidad `(device_id, nonce)`.

---

## 5) Idempotencia (única)

La fuente de verdad es `AppliedCommand` del core sync.

Reglas:

- Repetir `command_id` con mismo `payload_hash` → respuesta cacheada (`DUPLICATE`).
- Repetir con `payload_hash` distinto → `SYNC_PAYLOAD_MISMATCH`.

---

## 6) Auditoría contractual

Sync v2 **DEBE** emitir eventos contractuales:

- `SYNC_BATCH_RECEIVED`
- `SYNC_COMMAND_APPLIED`
- `SYNC_COMMAND_REJECTED`
- `SYNC_COMMAND_DUPLICATE`

Los eventos deben incluir `company_id`, `branch_id`, `device_id` en `metadata` cuando aplique.

---

## 7) Respuesta

Respuesta de batch:

- `server_time`
- `batch_id`
- `device_id`
- `device_status`
- `results`: lista por comando
- `summary`: `{ received, applied, rejected, duplicate }`

Respuesta por comando:

- `status`: `APPLIED` | `REJECTED` | `DUPLICATE`
- `refs` si aplica
- `reason` en rechazos

---

## 8) Códigos de error estables

- `MISSING_HEADERS`
- `INVALID_TS`
- `TS_OUT_OF_WINDOW`
- `UNKNOWN_OR_INACTIVE_DEVICE`
- `SYNC_DEVICE_NO_HMAC_SECRET`
- `SYNC_DEVICE_NO_PUBLIC_KEY`
- `BAD_SIGNATURE`
- `REPLAY_DETECTED`
- `SYNC_INVALID_SIGNATURE`
- `SYNC_PAYLOAD_MISMATCH`
- `SYNC_FORBIDDEN_SCOPE`
- `SYNC_TIME_SKEW`
- `SYNC_LIMIT_EXCEEDED`
- `DEVICE_ID_MISMATCH`

---

## 9) Compatibilidad legacy

Los endpoints legacy deben:

- adaptar request legacy a Sync v2;
- firmar request‑level según el esquema legacy (HMAC) **pero ejecutar el core v2**;
- devolver errores estables y consistentes.

---

## 10) Ejemplos

### Request (HMAC)

```json
{
  "protocol_version": "2",
  "device_id": "<uuid>",
  "ts": 1738300000,
  "nonce": "n-123",
  "auth": { "scheme": "hmac", "signature": "..." },
  "batch_id": "<uuid>",
  "batch": [
    {
      "command_id": "<uuid>",
      "type": "DEMO_PING",
      "scope": { "company_id": 1, "branch_id": 2 },
      "occurred_at": "2026-01-31T12:00:00Z",
      "payload": { "msg": "ok" }
    }
  ]
}
```

### Response

```json
{
  "server_time": "2026-01-31T12:00:01Z",
  "batch_id": "<uuid>",
  "device_id": "<uuid>",
  "device_status": "ACTIVE",
  "results": [
    { "command_id": "<uuid>", "status": "APPLIED", "refs": { "pong": true } }
  ],
  "summary": { "received": 1, "applied": 1, "rejected": 0, "duplicate": 0 }
}
```

---

## 11) Deprecación (legacy) + métricas + plan de retiro

**Headers obligatorios en wrappers legacy**

- `Deprecation: true`
- `Sunset: 2026-03-31T00:00:00Z`
- `Link: </docs/CONTRACT_PACK_v2.0.md>; rel="deprecation"`

**Métricas mínimas (legacy)**

- `metrics:sync_legacy:requests`
- `metrics:sync_legacy:errors:<ERROR_CODE>`

**Plan de retiro (hitos)**

- T0: Sync v2 canónico operativo (hoy).
- T0 + 30 días: legacy con warnings + seguimiento de métricas.
- T0 + 60 días: no se aceptan nuevas devices legacy.
- T0 + 90 días: legacy retirado.

---

## Inventory Kernel Contract (v1.0 dentro de pack v2.0)

**inventory_kernel.contract_version:** 1.0

### Propósito

Definir el **kernel de inventario** como fuente de verdad, con reglas invariantes, auditoría contractual y APIs mínimas para movimientos, ledger y balances.

### Entidades canónicas

- **Movement**: evento de stock (entrada/salida/ajuste/transferencia) con trazabilidad e idempotencia.
- **LedgerEntry**: asiento canónico por movimiento (si aplica doble entrada o evento contable de inventario).
- **BalanceSnapshot**: balance por `item/warehouse/branch` con reglas de consistencia.

### Invariantes

1. **Scope estricto**: todo endpoint opera con `company_id` y `branch_id` validados por RBAC.
2. **No stock negativo** (si aplica): reglas explícitas de rechazo o backorder; no se permite “silencioso”.
3. **Idempotencia**: movimientos duplicados por `command_id` o `movement_id` deben ser deduplicados.
4. **Auditoría contractual**: evento `INVENTORY_MOVEMENT_POSTED` obligatorio para todo movimiento aplicado.
5. **Orden estable** para ledger: `(posted_at, id)` o `(sequence, id)`.

### Catálogo canónico (event_type + reason_code)

**Event types canónicos (Inventory):**

- `INVENTORY_MOVEMENT_POSTED`
- `INVENTORY_ADJUSTMENT_POSTED`
- `INVENTORY_TRANSFER_POSTED`

**Reason codes canónicos (Inventory):**

- `INVENTORY_INVALID_SCOPE`
- `INVENTORY_INSUFFICIENT_STOCK`
- `INVENTORY_IDEMPOTENCY_CONFLICT`
- `INVENTORY_SCHEMA_INVALID`

> Nota: `SYNC_*` queda reservado para errores/políticas del pipeline (firma, scope, límites, skew, schema del comando).

### Semántica de rechazo (pipeline vs negocio)

- **Pipeline (sync):** firma, scope, límites, skew, schema de comando ⇒ `SYNC_*`.
- **Negocio (inventario):** reglas de movimiento/stock ⇒ `INVENTORY_*`.

**Frontera de scope:**

- `SYNC_FORBIDDEN_SCOPE`: el dispositivo/usuario **no tiene derecho** a operar ese `company_id/branch_id` (pipeline).
- `INVENTORY_INVALID_SCOPE`: el scope es válido, pero el payload apunta a entidades fuera del scope (warehouse/item fuera de branch/company, etc.).

### Resultado de handler (contrato)

- `APPLIED` con `refs` estables.
- `REJECTED` con `reason` (reason_code contractual) y `details` mínimos.
- `DUPLICATE` con `refs` (si aplica).

### Sync Inventory (comandos)

El kernel de inventario soporta comandos offline en Sync v2 con los siguientes tipos estables:

- `INVENTORY_MOVEMENT_RECEIVE` (alias canónico: `INVENTORY.MOVEMENT.RECEIVE`)
- `INVENTORY_MOVEMENT_ISSUE` (alias canónico: `INVENTORY.MOVEMENT.ISSUE`)
- `INVENTORY_MOVEMENT_ADJUST` (alias canónico: `INVENTORY.MOVEMENT.ADJUST`)
- `INVENTORY_TRANSFER` (alias canónico: `INVENTORY.TRANSFER`)

Reglas adicionales:

- Si se envía `idempotency_key`, el servidor **DEBE** rechazar conflictos de payload con `INVENTORY_IDEMPOTENCY_CONFLICT`.
- Errores de negocio **DEBEN** mapearse a los códigos contractuales `INVENTORY_*`.

### Endpoints mínimos (v1)

**Movimientos**

- `POST /api/inventory/movements/receive/` — entrada (RBAC: `inventory.movement.receive`).
- `POST /api/inventory/movements/issue/` — salida (RBAC: `inventory.movement.issue`).
- `POST /api/inventory/movements/adjust/` — ajuste (RBAC: `inventory.movement.adjust`).
- `POST /api/inventory/transfers/` — transferencia (RBAC: `inventory.transfer.create`).

**Ledger**

- `GET /api/inventory/ledger/` — **paginado estricto** (RBAC: `inventory.ledger.read`).
- Filtros: `warehouse_id`, `item_id`, `movement_type`, `since`, `until`.
- Orden estable: `(created_at, id)`.

**Balances**

- `GET /api/inventory/balances/` — **paginado estricto** (RBAC: `inventory.balance.read`).
- Filtros: `warehouse_id`, `item_id`.
- Orden estable: `(warehouse_id, item_id)`.

### Paginación y límites

- Paginación **obligatoria** (cursor/seek preferible, offset aceptable con límites).
- Orden estable y límite máximo definido para evitar lecturas masivas.

### Precisión decimal y redondeo

- `qty` y `qty_on_hand`: **string decimal** con escala fija (4 decimales).
- `unit_cost` y `avg_cost`: **string decimal** con escala fija (6 decimales).
- Redondeo: **half-up** (ROUND_HALF_UP) en backend.

### Respuesta paginada (forma canónica)

```json
{
  "count": 123,
  "limit": 50,
  "offset": 0,
  "results": [{ "...": "..." }]
}
```

### Errores contractuales mínimos

- `INVENTORY_INVALID_SCOPE`
- `INVENTORY_INSUFFICIENT_STOCK`
- `INVENTORY_IDEMPOTENCY_CONFLICT`
- `INVENTORY_SCHEMA_INVALID`
