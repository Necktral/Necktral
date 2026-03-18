# Certificación Real Fase 4A — Shadow Ledger

Versión: v1.0  
Fecha: 2026-03-08  
Estado: **Operativo (staging -> producción)**

## Propósito

Ejecutar una certificación **real end-to-end** de Fase 4A, sin smoke tests, con evidencia auditable y bloqueo explícito de drift entre entornos.

## 1) Paridad obligatoria de entorno

Antes de cualquier promoción:

1. Exportar manifiesto de staging:

```bash
python manage.py export_phase4_env_manifest --company-id <COMPANY_ID> --output artifacts/staging_phase4_manifest.json
```

2. Exportar manifiesto de producción objetivo:

```bash
python manage.py export_phase4_env_manifest --company-id <COMPANY_ID> --output artifacts/prod_phase4_manifest.json
```

3. Comparar manifiestos en modo estricto (bloquea drift):

```bash
python manage.py compare_phase4_env_manifests \
  --left artifacts/staging_phase4_manifest.json \
  --right artifacts/prod_phase4_manifest.json
```

Si falla la comparación, **no promover**.

## 2) Preparación de datos reales controlados

1. Cargar snapshot anonimizado reciente de producción en staging.
2. Confirmar migraciones aplicadas y consistentes.
3. Sembrar RuleSet v1 por compañía:

```bash
python manage.py seed_posting_rules_v1 --company-id <COMPANY_ID>
```

## 3) Ejecución real E2E (happy path)

1. Ejecutar flujo real por APIs:
- Billing (documentos emitidos/anulados)
- Inventory (movimientos/ajustes/transferencias)
- Payments/Cash (movimientos/cierres)
- CEC (`CloseRun` hasta `PACKAGED`)

2. Certificar corrida por `run_id`:

```bash
python manage.py certify_shadow_ledger_run \
  --run-id <RUN_ID> \
  --company-id <COMPANY_ID> \
  --output artifacts/certificacion_happy_<RUN_ID>.json
```

Criterio:
- `passed=true`
- `deterministic_replay=true`
- `first_manifest_hash == second_manifest_hash`
- `CloseRun` permanece en `PACKAGED`.

## 4) Ejecución real (error path bloqueante)

1. Probar escenario controlado de regla faltante/inválida.
2. Certificar corrida bloqueante:

```bash
python manage.py certify_shadow_ledger_run \
  --run-id <RUN_ID_BLOQUEANTE> \
  --company-id <COMPANY_ID> \
  --expect-blocked \
  --output artifacts/certificacion_blocked_<RUN_ID_BLOQUEANTE>.json
```

Criterio:
- `passed=true` con `blocked=true`
- `CloseRun` en `REOPENED_EXCEPTION`
- existe `CEC.CloseRunBlocked`
- existe `CECException` bloqueante `source_module=ACCOUNTING`.

## 5) Operación continua (real)

Comando recomendado de ciclo operativo:

```bash
python manage.py run_shadow_ledger_cycle \
  --company-id <COMPANY_ID> \
  --project-limit 100 \
  --dispatch-limit 200 \
  --max-inbox-failed 0 \
  --max-outbox-failed 0 \
  --max-stale-pending-triggers 0 \
  --max-projection-failed 0
```

Ejemplo `cron` (cada 5 min):

```cron
*/5 * * * * cd /srv/erp_crm/backend && /srv/venv/bin/python manage.py run_shadow_ledger_cycle --company-id <COMPANY_ID> --project-limit 100 --dispatch-limit 200 --max-inbox-failed 0 --max-outbox-failed 0 --max-stale-pending-triggers 0 --max-projection-failed 0 >> /var/log/erp/shadow_ledger_cycle.log 2>&1
```

## 6) Ownership y SLA

- **Owner funcional**: Contabilidad/Finanzas (aprobación de reglas y cierres).
- **Owner técnico**: Backend/Plataforma (operación batch, fallos y paridad).
- **SLA incidente crítico (`CloseRunBlocked`)**: atención inicial < 30 min, resolución/mitigación < 4 h.
- **SLA inbox failed** (`consumer=accounting.projector`): remediación < 1 h.

## 7) Criterio de Go-Live

Se permite promoción solo si:

1. Paridad de entorno sin drift.
2. Happy path real certificado y reproducible.
3. Error path real bloqueante certificado.
4. Evidencias (`*.json`) hash/firmadas almacenadas.
5. Regresión técnica (`pytest -q`) en verde.

## 8) Gate automatizado (recomendado)

Para bloquear promoción con un solo comando:

```bash
python manage.py verify_phase4_go_live \
  --company-id <COMPANY_ID> \
  --staging-manifest artifacts/staging_phase4_manifest.json \
  --prod-manifest artifacts/prod_phase4_manifest.json \
  --happy-evidence artifacts/certificacion_happy_<RUN_ID>.json \
  --blocked-evidence artifacts/certificacion_blocked_<RUN_ID_BLOQUEANTE>.json \
  --output artifacts/phase4_go_live_gate.json
```

El comando falla (exit code != 0) si detecta cualquier incumplimiento:
- drift de paridad entre staging/producción;
- evidencia happy/blocking inválida;
- `shadow_ledger_v1` no activo para la compañía;
- `InboxEvent(status=FAILED, consumer=accounting.projector)` por encima del umbral permitido.

## 9) Fase 5 inicial: posting controlado

Una vez que Fase 4A está estable, se puede ejecutar posting formal:

```bash
python manage.py approve_journal_drafts \
  --company-id <COMPANY_ID> \
  --run-id <RUN_ID_PACKAGED>

python manage.py post_journal_drafts \
  --company-id <COMPANY_ID> \
  --run-id <RUN_ID_PACKAGED> \
  --require-approved

python manage.py close_fiscal_period \
  --company-id <COMPANY_ID> \
  --year <YYYY> \
  --month <MM>
```

Reglas operativas del comando:
- solo postea drafts `VALIDATED`/`APPROVED_FOR_POSTING`;
- respeta idempotencia (`JournalEntry` 1:1 por draft);
- no postea en período cerrado (`FiscalPeriod.status=CLOSED`);
- publica evento `ACCOUNTING.JournalPosted`.
