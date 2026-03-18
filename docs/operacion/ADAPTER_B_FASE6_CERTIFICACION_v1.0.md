# Certificación Real Fase 6 — Adapter B (Piloto 1 Sucursal)

Versión: v1.0  
Fecha: 2026-03-08  
Estado: **Operativo (staging -> producción)**

## Propósito

Ejecutar certificación **real end-to-end** para Fase 6 (Adapter B) con evidencia auditable, paridad de entorno y gate de promoción estricto.

## 1) Paridad de entorno obligatoria

1. Exportar manifiesto de staging:

```bash
python manage.py export_phase6_env_manifest \
  --company-id <COMPANY_ID> \
  --branch-id <BRANCH_ID> \
  --output artifacts/staging_phase6_manifest.json
```

2. Exportar manifiesto de producción objetivo:

```bash
python manage.py export_phase6_env_manifest \
  --company-id <COMPANY_ID> \
  --branch-id <BRANCH_ID> \
  --output artifacts/prod_phase6_manifest.json
```

3. Comparar en modo estricto:

```bash
python manage.py compare_phase6_env_manifests \
  --left artifacts/staging_phase6_manifest.json \
  --right artifacts/prod_phase6_manifest.json
```

Si hay drift, **no promover**.

## 2) Certificación real de ejecución

### Happy path

```bash
python manage.py certify_adapter_b_run \
  --company-id <COMPANY_ID> \
  --branch-id <BRANCH_ID> \
  --output artifacts/fase6_happy.json
```

Criterio:
- `passed=true`
- `blocked=false`
- `close_run_status=PACKAGED`
- `deterministic_replay=true`
- `job_counts.printed > 0`

### Error path bloqueante

```bash
python manage.py certify_adapter_b_run \
  --company-id <COMPANY_ID> \
  --branch-id <BRANCH_ID> \
  --expect-blocked \
  --output artifacts/fase6_blocked.json
```

Criterio:
- `passed=true`
- `blocked=true`
- `close_run_status=REOPENED_EXCEPTION`
- `cec_blocking_exceptions > 0`

## 3) Gate automatizado de go-live

```bash
python manage.py verify_phase6_go_live \
  --company-id <COMPANY_ID> \
  --branch-id <BRANCH_ID> \
  --staging-manifest artifacts/staging_phase6_manifest.json \
  --prod-manifest artifacts/prod_phase6_manifest.json \
  --happy-evidence artifacts/fase6_happy.json \
  --blocked-evidence artifacts/fase6_blocked.json \
  --max-inbox-failed 0 \
  --max-outbox-failed 0 \
  --max-failed-jobs 0 \
  --max-retry-overdue 0 \
  --max-contingency-open 0 \
  --output artifacts/fase6_go_live_gate.json
```

El comando falla (exit code != 0) cuando cualquier check queda en rojo.

## 4) Operación continua del piloto

Comando de ciclo operativo:

```bash
python manage.py run_adapter_b_cycle \
  --company-id <COMPANY_ID> \
  --branch-id <BRANCH_ID> \
  --print-limit 100 \
  --dispatch-limit 200 \
  --max-inbox-failed 0 \
  --max-outbox-failed 0 \
  --max-failed-jobs 0 \
  --max-retry-overdue 0 \
  --max-stale-pending 0 \
  --max-open-contingency 0
```

Ejemplo cron (cada 5 minutos):

```cron
*/5 * * * * cd /srv/erp_crm/backend && /srv/venv/bin/python manage.py run_adapter_b_cycle --company-id <COMPANY_ID> --branch-id <BRANCH_ID> --print-limit 100 --dispatch-limit 200 --max-inbox-failed 0 --max-outbox-failed 0 --max-failed-jobs 0 --max-retry-overdue 0 --max-stale-pending 0 --max-open-contingency 0 >> /var/log/erp/adapter_b_cycle.log 2>&1
```

## 5) Ownership y SLA

- **Owner funcional**: Operación/Facturación.
- **Owner técnico**: Backend/Plataforma.
- **SLA contingencia abierta** (`FiscalStatus=CONTINGENCY`): atención inicial < 30 min, mitigación < 4 h.
- **SLA job FAILED**: remediación < 1 h.

## 6) Evidencia y firma

- Todos los comandos de certificación/gate/ciclo generan evidencia con:
  - `evidence_hash`
  - `signature`
  - `signature_type`
- Variable opcional para firma HMAC:

```bash
export PHASE6_EVIDENCE_SECRET="<SECRET>"
```

Sin `PHASE6_EVIDENCE_SECRET`, la firma cae a `sha256` determinista.
