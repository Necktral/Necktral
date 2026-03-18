# Kernel Hardening Baseline v1.1

Version: v1.1  
Fecha: 2026-03-17  
Estado: Activo (implementación S0-S8)

## Snapshot operativo (S0)

- Rama con cambios locales activos; no se asume árbol limpio.
- ADRs de hardening y ownership publicados en `docs/`.
- Backend canónico: `backend/src` + módulos de dominio en `modulos/`.

## Mapeo matriz -> código -> pruebas

| Bloque | Código principal | Pruebas base |
|---|---|---|
| IAM / Scope / RBAC | `apps/iam/authentication.py`, `apps/common/permissions.py` | `test_iam_scope_contracts.py` |
| Auditoría contractual | `apps/audit/writer.py`, `apps/audit/contracts.py` | `test_inventory_kernel_flow.py`, `test_billing_doc_flow.py`, `test_phase2_payments_api.py` |
| Integration Backbone | `apps/integration/services.py`, `apps/integration/models.py` | `test_phase3_outbox_dispatcher.py`, `test_integration_idempotency_concurrency.py` |
| Accounting freeze | `apps/accounting/services.py`, `apps/accounting/models.py` | `test_phase4_shadow_ledger.py`, `test_phase5_posting_controlled.py`, `test_payments_accounting_boundary.py` |
| CEC guardrails | `apps/cec/services.py`, `apps/cec/models.py` | `test_phase3_cec_orchestrator.py`, `test_phase3_cec_execute_api.py` |
| Billing kernel | `modulos/facturacion/services.py`, `modulos/facturacion/views.py` | `test_billing_doc_flow.py`, `test_billing_accounting_integration.py` |
| Inventory kernel | `modulos/inventarios/services.py`, `modulos/inventarios/views.py` | `test_inventory_kernel_flow.py`, `test_inventory_accounting_integration.py` |
| Payments & Cash | `apps/payments/services.py`, `apps/payments/models.py` | `test_phase2_payments_api.py`, `test_payments_accounting_boundary.py` |

## Regla de ejecución

- Cada sprint cierra: contrato + enforcement + tests + evidencia + rollback.
- No avanzar a Reportes/Dashboard hasta cierre de kernels/core.
