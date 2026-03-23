# Runbook Operativo de Enrolamiento de Dispositivos

Versión: v1.0  
Fecha: 2026-03-20  
Estado: Activo

## 1) Objetivo

Operar el enrolamiento/revocación de dispositivos móviles en entorno DEV o QA usando el contrato canónico `sync_engine`.

## 2) Prerrequisitos

- Stack arriba: `db`, `backend`, `frontend`.
- Usuario admin con permisos `sync.device.enroll` y `sync.device.revoke`.
- Contexto activo válido (`X-Company-Id`, opcional `X-Branch-Id`).
- Auth en cookie (`AUTH_TOKEN_TRANSPORT=cookie`) y CORS/CSRF para `localhost:3000/3001/3100`.
- `DJANGO_JWT_SIGNING_KEY` configurada con minimo 32 bytes (backend no inicia si no cumple).

Nota: los ejemplos usan `localhost:3100`; si tu frontend corre en `3000` o `3001`, reemplaza `Origin`/`Referer`.

## 3) Procedimiento estándar

### Paso 1: Login web

```bash
curl -sS -c /tmp/cookies.txt \
  -X POST http://localhost:8000/api/backend/auth/login/ \
  -H 'Origin: http://localhost:3100' \
  -H 'Content-Type: application/json' \
  --data '{"username":"k6_admin","password":"Aa!9_Sim_Seed"}'
```

Extraer CSRF:

```bash
awk '$6=="nt_csrf"{print $7}' /tmp/cookies.txt | tail -n1
```

### Paso 2: Crear challenge de enrolamiento

```bash
curl -sS -b /tmp/cookies.txt \
  -X POST http://localhost:8000/api/backend/sync/enrollment/challenges/ \
  -H 'Origin: http://localhost:3100' \
  -H 'Referer: http://localhost:3100/' \
  -H "X-CSRFToken: <csrf>" \
  -H 'X-Company-Id: 2' \
  -H 'X-Branch-Id: 3' \
  -H 'Content-Type: application/json' \
  --data '{"company_id":2,"branch_id":3,"label_hint":"Dispositivo Campo","expires_in_minutes":15}'
```

Salida esperada: `challenge_id`, `enrollment_code`, `expires_at`.

### Paso 3: Enrolar dispositivo (sin JWT)

```bash
curl -sS -X POST http://localhost:8000/api/backend/sync/enroll/ \
  -H 'Origin: http://localhost:3100' \
  -H 'Content-Type: application/json' \
  --data '{"enrollment_code":"<code>","public_key_b64":"<ed25519_public_key_b64>","label":"Campo-01","meta":{"os":"android"}}'
```

Salida esperada: `device_id`, `device_status=ACTIVE`, `policy`.

### Paso 4: Sincronizar batch firmado

```bash
curl -sS -X POST http://localhost:8000/api/backend/sync/batch/ \
  -H "X-Device-Id: <device_id>" \
  -H 'Content-Type: application/json' \
  --data @batch_signed.json
```

Salida esperada: `summary.applied >= 1` para comandos válidos.

### Paso 5: Listar dispositivos

```bash
curl -sS -b /tmp/cookies.txt \
  'http://localhost:8000/api/backend/sync/devices/?limit=20&offset=0' \
  -H 'Origin: http://localhost:3100' \
  -H 'X-Company-Id: 2' \
  -H 'X-Branch-Id: 3'
```

### Paso 6: Revocar dispositivo

```bash
curl -sS -b /tmp/cookies.txt \
  -X POST http://localhost:8000/api/backend/sync/devices/<device_id>/revoke/ \
  -H 'Origin: http://localhost:3100' \
  -H 'Referer: http://localhost:3100/' \
  -H "X-CSRFToken: <csrf>" \
  -H 'X-Company-Id: 2' \
  -H 'X-Branch-Id: 3' \
  -H 'Content-Type: application/json' \
  --data '{}'
```

Salida esperada: `status=REVOKED`.

## 4) Diagnóstico rápido de incidentes

| Síntoma | Señal | Hipótesis | Acción inmediata |
|---|---|---|---|
| `AUTH_CSRF_FAILED` | `403` en challenge/revoke | Falta `X-CSRF-Token` o cookie desincronizada | Re-login y reenviar `X-CSRF-Token` + `Referer` |
| `RBAC_FORBIDDEN` | `403` con denegación RBAC | Usuario sin `sync.device.enroll`/`sync.device.revoke` | Asignar rol/grant en company |
| `SCOPE_FORBIDDEN` | `403` por scope | Header de contexto inválido o sin membresía | Corregir `X-Company-Id`/`X-Branch-Id` y membresías |
| `400 X-Company-Id requerido` | Error de contexto | Header ausente | Enviar `X-Company-Id` válido |
| `403 Código inválido/expirado` | Falla en `/sync/enroll/` | Challenge usado o vencido | Crear nuevo challenge |
| `SYNC_INVALID_SIGNATURE` | Batch rechazado | Firma no coincide con payload canónico | Refirmar comando y validar `payload_hash` |
| `SYNC_TIME_SKEW` | Device en cuarentena | Reloj dispositivo fuera de ventana | Sincronizar hora, re-enrolar si aplica |

## 5) Rollback operacional (sin cambios de API)

- Revocar `device_id` comprometido.
- Invalidar challenges activos generando nuevos códigos one-time.
- Forzar re-enrolamiento con nueva llave pública del dispositivo.
- Mantener investigación en `audit` por `request_id`/`device_id`.

## 6) Comandos de observabilidad mínima

```bash
docker compose logs -f backend
docker compose logs -f frontend
curl -i -X OPTIONS 'http://localhost:8000/api/backend/auth/login/' \
  -H 'Origin: http://localhost:3100' \
  -H 'Access-Control-Request-Method: POST'
docker compose exec -T backend python src/manage.py run_operational_accounting_projector --company-id 2 --limit 200
```

Criterio de salud CORS: `Access-Control-Allow-Origin` y `Access-Control-Allow-Credentials: true`.

## 7) Gate oficial auth/sync

```bash
make qa-auth-sync-reset-run
```

Este gate ejecuta setup reproducible (reset + seed + bootstrap) y smoke end-to-end con artefacto en `qa/reports/auth_sync_smoke_report.{json,md}`.
