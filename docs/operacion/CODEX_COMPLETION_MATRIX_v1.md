# CODEX Completion Matrix v1

Version: v1  
Fecha: 2026-04-16  
Estado: Línea base operativa de incompletitud/completitud (modo cierre)

## Objetivo

Establecer una línea base verificable del estado real del software por módulo y por dominio operativo, para priorizar cierres sin ambigüedad.

## Fuente de verdad y método

- Fuente primaria: código y contratos ejecutables del repo.
- Fuente secundaria: documentación operativa/arquitectura (solo para contexto; si contradice código, se marca gap).
- Cruces obligatorios usados:
  - Backend rutas: `backend/src/config/urls.py`, `backend/src/apps/**/urls.py`.
  - Política de rutas: `backend/src/config/routing_policy.py`, `qa/reports/route_contract_report.json`.
  - Frontend wiring: `frontend/src/router/routes.ts`, `frontend/src/pages/*`, `frontend/src/services/*`, `frontend/src/layouts/MainLayout.vue`.
  - Tests: `backend/src/tests/*`, `backend/src/apps/**/tests*`, `frontend/src/**/__tests__/*.spec.ts`.
  - Operación/runbooks: `docs/operacion/*`, `qa/*`.

## Reglas deterministas de clasificación

- `cerrado`: superficies requeridas alineadas, sin drift crítico verificable.
- `parcial`: implementación usable pero con al menos una superficie requerida incompleta.
- `roto`: contradicción verificable (contrato/código, referencia inexistente, wiring incoherente).
- `no iniciado`: sin evidencia mínima implementada.
- `incierto`: etiqueta de confianza; no reemplaza `estado_global`.

## Perfil UI por tipo de dominio

- UI requerida (12 dominios operativos): ORG, HR, IAM/RBAC, Audit, Sync, Billing, Inventory, Payments/Cash, Reporting, FUEL, Retail POS, Compras.
- `backend-aware`: para módulos transversales sin obligación de UI dedicada, la columna `frontend` puede quedar `cerrado` si la ausencia de pantalla dedicada es intencional y consistente.

## Sección A — Matriz Canónica por Módulo

| dominio | módulos/backend fuente | backend | frontend | contratos | tests | ops/runbook | estado_global | confianza | evidencia | siguiente_accion_exacta |
|---|---|---|---|---|---|---|---|---|---|---|
| `kernels.accounting` | `backend/src/apps/kernels/accounting` | cerrado | cerrado | cerrado | cerrado | cerrado | cerrado | alta | `backend/src/apps/kernels/accounting/urls.py`; `backend/src/tests/test_phase5_accounting_api.py`; `docs/operacion/GL_FASE7A_CERTIFICACION_v1.0.md` | Mantener baseline; solo monitoreo de drift en guards de arquitectura/rutas. |
| `kernels.facturacion` | `backend/src/apps/kernels/facturacion` | cerrado | no iniciado | cerrado | cerrado | cerrado | parcial | alta | `backend/src/apps/kernels/facturacion/urls.py`; `backend/src/tests/test_billing_kernel.py`; `docs/operacion/GO_LIVE_BILLING_INVENTORY_F4_F5_v1.0.md` | Implementar UI mínima de facturación (lista + emisión + anulación) contra `/api/billing/*`. |
| `kernels.inventarios` | `backend/src/apps/kernels/inventarios` | cerrado | cerrado | cerrado | cerrado | cerrado | cerrado | alta | `backend/src/apps/kernels/inventarios/urls.py`; `frontend/src/pages/InventoryPage.vue`; `frontend/src/features/inventory/__tests__/inventory-commit.spec.ts` | Endurecer smoke funcional de inventario como check estable por lote de release. |
| `kernels.payments` | `backend/src/apps/kernels/payments` | cerrado | no iniciado | parcial | parcial | parcial | parcial | media (`incierto`: sin UI ni smoke operativo dedicado en repo) | `backend/src/apps/kernels/payments/urls.py`; `backend/src/tests/test_payments_services.py` | Diseñar y ejecutar primer lote UI Payments/Cash (intents + cash session open/close + movimientos). |
| `kernels.reporting` | `backend/src/apps/kernels/reporting` | cerrado | parcial | cerrado | cerrado | cerrado | parcial | alta | `backend/src/apps/kernels/reporting/urls.py`; `backend/src/apps/kernels/reporting/tests/test_api.py`; `docs/operacion/REPORTING_R8_GOBIERNO_OBSERVABILIDAD_v1.0.md` | Completar UI de runs/exports/snapshots/saved-views (hoy solo analytics embed). |
| `modulos.accounting` (shim compat) | `backend/src/apps/modulos/accounting` | parcial | cerrado | parcial | parcial | parcial | parcial | alta | `backend/src/apps/modulos/accounting/__init__.py`; `docs/README.md` (compat temporal kernels) | Definir plan de retiro del namespace legacy y fecha objetivo de eliminación. |
| `modulos.accounts` | `backend/src/apps/modulos/accounts` | cerrado | cerrado | cerrado | parcial | parcial | parcial | media (`incierto`: drift docs/tests en README) | `backend/src/apps/modulos/accounts/urls.py`; `frontend/src/stores/auth.store.ts`; `frontend/src/pages/LoginPage.vue`; `backend/src/tests/test_auth_throttling_me_context.py` | Corregir drift documental de tests inexistentes y consolidar runbook auth/session. |
| `modulos.audit` | `backend/src/apps/modulos/audit` | cerrado | cerrado | cerrado | parcial | parcial | parcial | media | `backend/src/apps/modulos/audit/contracts.py`; `backend/src/apps/modulos/audit/urls.py`; `frontend/src/pages/AuditBitacoraPage.vue` | Crear smoke de auditoría UI↔API y checklist operativo específico del dominio audit. |
| `modulos.cec` | `backend/src/apps/modulos/cec` | cerrado | cerrado | parcial | parcial | parcial | parcial | media (`incierto`: sin UI dedicada ni matriz estado/evento explícita) | `backend/src/apps/modulos/cec/urls.py`; `backend/src/tests/test_phase3_cec_execute_api.py`; `docs/ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md` | Formalizar catálogo de estados/eventos/ownership CEC en artefactos contractuales v1. |
| `modulos.common` | `backend/src/apps/modulos/common` | cerrado | cerrado | parcial | parcial | parcial | parcial | media | `backend/src/apps/modulos/common/urls.py`; `qa/contracts/*`; `qa/reports/*` | Documentar contrato operativo de métricas (`/api/metrics/`) y su consumo esperado. |
| `modulos.compras` | `backend/src/apps/modulos/compras` | cerrado | no iniciado | parcial | parcial | cerrado | parcial | alta | `backend/src/apps/modulos/compras/urls.py`; `backend/src/tests/test_phase10_procurement_4b.py`; `docs/operacion/GO_LIVE_FASE10_PROCUREMENT_v1.0.md` | Implementar primera UI de compras (crear/post/void documento) contra `/api/procurement/*`. |
| `modulos.dashboard` | `backend/src/apps/modulos/dashboard` | cerrado | parcial | cerrado | parcial | cerrado | parcial | media | `backend/src/apps/modulos/dashboard/urls.py`; `frontend/src/stores/dashboard.store.ts`; `frontend/src/pages/AnalyticsPage.vue` | Añadir cobertura frontend para flujo de token embed y errores de expiración/redeem. |
| `modulos.estacion_servicios` | `backend/src/apps/modulos/estacion_servicios` | cerrado | parcial | parcial | cerrado | cerrado | parcial | media | `backend/src/apps/modulos/estacion_servicios/urls.py`; `backend/src/tests/test_fuel_shift_flow.py`; `frontend/src/pages/FuelDashboardPage.vue`; `backend/src/config/routing_policy.py` | Cerrar UI operativa de turnos/ventas/cancelación; hoy solo dashboard/health. |
| `modulos.facturacion` (shim compat) | `backend/src/apps/modulos/facturacion` | parcial | no iniciado | parcial | parcial | parcial | parcial | alta | `backend/src/apps/modulos/facturacion/__init__.py`; `backend/src/config/urls.py` | Retirar dependencia de imports legacy y fijar sunset técnico en plan de release. |
| `modulos.hr` | `backend/src/apps/modulos/hr` | cerrado | cerrado | parcial | parcial | parcial | parcial | media | `backend/src/apps/modulos/hr/urls.py`; `frontend/src/pages/HrEmployeesPage.vue`; `frontend/src/pages/HrPositionsPage.vue`; `backend/src/tests/test_hr_position_role_automation.py` | Completar smoke end-to-end HR con asignación, provisionamiento y revoke-access. |
| `modulos.iam` | `backend/src/apps/modulos/iam` | cerrado | parcial | parcial | parcial | parcial | parcial | media | `backend/src/apps/modulos/iam/urls.py`; `backend/src/tests/test_iam_context_headers.py`; `frontend/src/pages/HrEmployeesPage.vue` (dependencia indirecta de permiso IAM) | Definir y construir UI IAM mínima (contexto/capacidades) o declarar explícitamente no-UI. |
| `modulos.integration` | `backend/src/apps/modulos/integration` | cerrado | cerrado | parcial | parcial | parcial | parcial | media (`incierto`: sin contrato operativo publicado por módulo) | `backend/src/apps/modulos/integration/urls.py`; `backend/src/tests/test_integration_idempotency_concurrency.py` | Publicar runbook corto de outbox/inbox y smoke reproducible de ack/sent. |
| `modulos.inventarios` (shim compat) | `backend/src/apps/modulos/inventarios` | parcial | cerrado | parcial | parcial | parcial | parcial | alta | `backend/src/apps/modulos/inventarios/__init__.py`; `frontend/src/pages/InventoryPage.vue` | Retirar imports legacy de inventarios y consolidar uso exclusivo de kernel canónico. |
| `modulos.org` | `backend/src/apps/modulos/org` | cerrado | cerrado | parcial | parcial | parcial | parcial | media (`incierto`: README referencia tests no presentes) | `backend/src/apps/modulos/org/urls.py`; `frontend/src/pages/OrgCompaniesPage.vue`; `frontend/src/pages/OrgBranchesPage.vue` | Añadir suite de pruebas ORG faltante documentada en README o corregir documentación. |
| `modulos.payments` (shim compat) | `backend/src/apps/modulos/payments` | parcial | no iniciado | parcial | parcial | parcial | parcial | alta | `backend/src/apps/modulos/payments/__init__.py`; `backend/src/config/urls.py` | Definir retiro del shim y activar solo `apps.kernels.payments`. |
| `modulos.rbac` | `backend/src/apps/modulos/rbac` | cerrado | parcial | parcial | parcial | parcial | parcial | media | `backend/src/apps/modulos/rbac/urls.py`; `backend/src/tests/test_rbac_list_endpoints.py`; `frontend/src/services/rbac.service.ts` | Implementar UI de administración RBAC (roles/permisos) o congelar explícitamente como API-only. |
| `modulos.retail_pos` | `backend/src/apps/modulos/retail_pos` | cerrado | cerrado | cerrado | cerrado | cerrado | cerrado | alta | `backend/src/apps/modulos/retail_pos/urls.py`; `frontend/src/pages/PosTerminalPage.vue`; `frontend/src/pages/OperationalCockpitPage.vue`; `qa/reports/retail_pos_*` | Mantener hardening y evidencias de piloto; no abrir alcance nuevo en este dominio. |
| `modulos.sync` (`/api/sync-hmac/*`) | `backend/src/apps/modulos/sync` | cerrado | cerrado | parcial | cerrado | cerrado | parcial | media | `backend/src/apps/modulos/sync/urls.py`; `backend/src/apps/modulos/sync/tests/test_sync_batch.py`; `backend/src/config/urls.py` | Definir contrato de coexistencia/retiro de `sync-hmac` frente a `sync_engine` canónico. |
| `modulos.sync_engine` (`/api/sync/*`) | `backend/src/apps/modulos/sync_engine` | cerrado | cerrado | cerrado | cerrado | cerrado | cerrado | alta | `backend/src/apps/modulos/sync_engine/urls.py`; `backend/src/tests/test_sync_v2_contract.py`; `frontend/src/pages/SyncEnrollmentPage.vue`; `frontend/src/pages/SyncDevicesPage.vue` | Mantener baseline y agregar smoke de regresión UI canónica por sesión de release. |

## Sección B — Consolidación por Dominio Operativo (Top 12)

| dominio | módulos/backend fuente | backend | frontend | contratos | tests | ops/runbook | estado_global | confianza | evidencia | siguiente_accion_exacta |
|---|---|---|---|---|---|---|---|---|---|---|
| ORG | `modulos.org`, `modulos.accounts` (bootstrap org) | cerrado | cerrado | parcial | parcial | parcial | parcial | media | `backend/src/apps/modulos/org/urls.py`; `frontend/src/pages/OrgCompaniesPage.vue`; `frontend/src/pages/OrgBranchesPage.vue`; `README.md` (tests ORG referenciados) | Cerrar gap de pruebas ORG documentadas vs pruebas reales y consolidar smoke ORG. |
| HR | `modulos.hr` (+ dependencia RBAC/IAM) | cerrado | cerrado | parcial | parcial | parcial | parcial | media | `backend/src/apps/modulos/hr/urls.py`; `frontend/src/pages/HrEmployeesPage.vue`; `frontend/src/pages/HrPositionsPage.vue`; `backend/src/tests/test_hr_*` | Crear smoke de flujo HR principal (empleado -> asignación -> provision -> revoke). |
| IAM/RBAC | `modulos.iam`, `modulos.rbac`, `modulos.accounts` | cerrado | parcial | parcial | parcial | parcial | parcial | media | `backend/src/apps/modulos/iam/urls.py`; `backend/src/apps/modulos/rbac/urls.py`; `frontend/src/services/rbac.service.ts` | Implementar superficie UI mínima para administración IAM/RBAC o declarar explícitamente API-only con evidencia. |
| Audit | `modulos.audit` | cerrado | cerrado | cerrado | parcial | parcial | parcial | media | `backend/src/apps/modulos/audit/contracts.py`; `frontend/src/pages/AuditBitacoraPage.vue`; `backend/src/tests/test_auth_audit_request_id.py` | Añadir prueba funcional UI→detalle evento y checklist operativo de auditoría. |
| Sync | `modulos.sync_engine` (canónico), `modulos.sync` (legacy/hmac) | cerrado | cerrado | cerrado | cerrado | cerrado | cerrado | alta | `backend/src/config/urls.py`; `frontend/src/pages/SyncEnrollmentPage.vue`; `qa/reports/sync_pos_contract_guard.txt` | Mantener dualidad bajo control y definir plan de deprecación de `sync-hmac`. |
| Billing | `kernels.facturacion`, `modulos.facturacion` (shim) | cerrado | no iniciado | cerrado | cerrado | cerrado | parcial | alta | `backend/src/apps/kernels/facturacion/urls.py`; `backend/src/tests/test_billing_kernel.py`; `docs/operacion/GO_LIVE_BILLING_INVENTORY_F4_F5_v1.0.md` | Construir lote UI Billing v1 (docs list/issue/void) conectado a `/api/billing/*`. |
| Inventory | `kernels.inventarios`, `modulos.inventarios` (shim) | cerrado | cerrado | cerrado | cerrado | cerrado | cerrado | alta | `backend/src/apps/kernels/inventarios/urls.py`; `frontend/src/pages/InventoryPage.vue`; `frontend/src/features/inventory/__tests__/*` | Mantener estabilidad y agregar smoke reproducible por rama antes de release. |
| Payments/Cash | `kernels.payments`, `modulos.payments` (shim) | cerrado | no iniciado | parcial | parcial | parcial | parcial | media (`incierto`: sin UI ni runbook dedicado de cash session) | `backend/src/apps/kernels/payments/urls.py`; `backend/src/tests/test_payments_services.py` | Ejecutar cierre UI Payments/Cash (intents + cash session + movimientos). |
| Reporting | `kernels.reporting`, `modulos.dashboard` | cerrado | parcial | cerrado | cerrado | cerrado | parcial | alta | `backend/src/apps/kernels/reporting/urls.py`; `frontend/src/pages/AnalyticsPage.vue`; `qa/reporting_contract_version_guard.py` | Implementar UI de operación de datasets/runs/exports/snapshots; no solo iframe. |
| FUEL | `modulos.estacion_servicios` | cerrado | parcial | parcial | cerrado | cerrado | parcial | media | `backend/src/apps/modulos/estacion_servicios/urls.py`; `frontend/src/pages/FuelDashboardPage.vue`; `frontend/src/pages/FuelHealthPage.vue`; `backend/src/config/routing_policy.py` | Completar UI transaccional de turnos/ventas/compensación y corregir drift documental de rutas. |
| Retail POS | `modulos.retail_pos` | cerrado | cerrado | cerrado | cerrado | cerrado | cerrado | alta | `backend/src/apps/modulos/retail_pos/urls.py`; `frontend/src/pages/PosTerminalPage.vue`; `qa/reports/retail_pos_edge_e2e_guard.json` | Continuar hardening operativo; mantener gates contractuales POS sin flexibilizar. |
| Compras | `modulos.compras` | cerrado | no iniciado | parcial | parcial | cerrado | parcial | alta | `backend/src/apps/modulos/compras/urls.py`; `backend/src/tests/test_phase10_procurement_4b.py`; `docs/operacion/GO_LIVE_FASE10_PROCUREMENT_v1.0.md` | Crear UI Compras v1 (crear, postear, anular) y smoke por flujo principal. |

## Hallazgos críticos detectados durante el corte v1

1. Hay dominios con backend cerrado pero sin UI operable (`Billing`, `Payments/Cash`, `Compras`).
2. `Reporting` en frontend está reducido a embed; falta operación directa del contrato `/api/reporting/*`.
3. `FUEL` expone solo tablero/salud en UI; faltan acciones transaccionales clave.
4. Existen shims de compatibilidad legacy (`modulos.{accounting,facturacion,inventarios,payments}`) aún activos.
5. Hay drift documental verificable en README (referencias a tests no presentes) y señal de drift de canonicidad de rutas Fuel entre docs y policy/código.

## Criterio de uso de esta matriz

- Esta matriz es baseline de cierre técnico; no reemplaza los guards QA.
- Si cambia código/contrato, la matriz debe recalcularse antes del siguiente lote de implementación.
- Si un estado se actualiza a `cerrado`, debe venir con evidencia de validación en handoff A-F.
