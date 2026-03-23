# Sync v2 Compatibility Matrix

Fecha: 2026-03-21  
Estado: Activo (alineado al código del repositorio)

## 1) Endpoints y rol actual

| Endpoint | Estado | Rol |
|---|---|---|
| `POST /api/sync/batch/` | Canónico | Acepta legacy (`SyncBatchIn`) y v2 (`protocol_version="2"`). |
| `POST /api/sync-hmac/batch/` | Legacy | Wrapper: valida firma HMAC legacy + delega aplicación/idempotencia al core `sync_engine`. |

Referencias:
- `backend/src/config/urls.py`
- `backend/src/apps/modulos/sync_engine/views.py`
- `backend/src/apps/modulos/sync/views.py`

## 2) Contratos de entrada soportados

### Legacy (`/api/sync/batch/`)
- `batch_id`, `device_id?`, `sent_at?`, `commands[]` (firma Ed25519 por comando).
- Compatibilidad preservada.

### v2 (`/api/sync/batch/`)
- `protocol_version`, `device_id`, `ts`, `nonce`, `auth{scheme,signature}`, `batch_id`, `batch[]`.
- Request-level security: ventana temporal + anti-replay por nonce en core.

Referencias:
- `backend/src/apps/modulos/sync_engine/serializers.py`
- `backend/src/apps/modulos/sync_engine/services.py`
- `docs/CONTRACT_PACK_v2.0.md`

## 3) Invariantes de seguridad

- `TS_OUT_OF_WINDOW`: validación temporal request-level.
- `BAD_SIGNATURE`: firma request-level inválida (v2) o firma legacy inválida (`sync-hmac`).
- `REPLAY_DETECTED`: nonce duplicado por dispositivo (tabla core `sync_engine.DeviceRequestNonce`).

Referencias:
- `backend/src/apps/modulos/sync_engine/models.py`
- `backend/src/apps/modulos/sync_engine/services.py`
- `backend/src/apps/modulos/sync/views.py`

## 4) Headers de deprecación legacy

- `Deprecation: true`
- `Link: </docs/CONTRACT_PACK_v2.0.md>; rel="deprecation"`
- `Sunset: <opcional por entorno>` (solo si `SYNC_HMAC_LEGACY_SUNSET` está definido)

Referencia:
- `backend/src/apps/modulos/sync/views.py`

## 5) Checklist de salida por fase (5 fases conservadoras)

1. Contrato/matriz sincronizados con código.
2. `/api/sync/batch/` en dual-mode (legacy + v2).
3. Request-level security centralizada en core.
4. `sync-hmac` sin lógica paralela de aplicación/idempotencia.
5. Legacy estable sin fecha fija de retiro, controlado por flags + métricas (`metrics:sync_legacy:*`).
