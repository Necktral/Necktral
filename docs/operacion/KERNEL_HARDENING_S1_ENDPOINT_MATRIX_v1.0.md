# S1 Endpoint Matrix — IAM / Scope / RBAC

Version: v1.0  
Fecha: 2026-03-17  
Estado: Activo

## Objetivo

Cobertura explícita de enforcement de contexto (`X-Company-Id`, `X-Branch-Id`) y denegaciones con `required_scope`.

## Endpoints críticos (operativos)

| Módulo | Endpoint | Auth/Scope esperado | Permiso base |
|---|---|---|---|
| Billing | `/api/billing/docs/*` | `company` obligatorio, `branch` obligatorio | `billing.*` |
| Inventory | `/api/inventory/*` | `company` obligatorio, `branch` obligatorio | `inventory.*` |
| Payments | `/api/payments/*` | `company` obligatorio, `branch` obligatorio | `payments.*` |
| Accounting | `/api/accounting/*` | `company` obligatorio; branch según operación | `accounting.*` |
| CEC | `/api/cec/*` | `company` obligatorio; branch por tipo de run | `cec.*` |
| Integration | `/api/integration/*` | `company` obligatorio para vistas operativas | `integration.*` |

## Casos de denegación que deben cubrirse en tests

- falta `X-Company-Id` -> `400 BAD_REQUEST`
- `X-Branch-Id` inválido -> `400 BAD_REQUEST`
- usuario sin membresía a `company` -> `403 SCOPE_FORBIDDEN` + `required_scope.company_id`
- usuario sin membresía a `branch` -> `403 SCOPE_FORBIDDEN` + `required_scope.branch_id`
- `X-Data-Company-Id` intercompany READ sin grant -> `403` por RBAC/scope
- bypass de `X-Data-Branch-Id` en misma compañía -> `400 BAD_REQUEST`
