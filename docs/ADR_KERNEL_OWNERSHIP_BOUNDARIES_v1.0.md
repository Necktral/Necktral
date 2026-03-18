# ADR — Kernel Ownership Boundaries v1.0

Version: v1.0  
Fecha: 2026-03-17  
Estado: Aprobado

## Decisión

Cada kernel/módulo core mantiene ownership explícito y prohibiciones operativas. El hardening no puede violar estas fronteras.

## Matriz de ownership

| Bloque | Posee | No debe poseer |
|---|---|---|
| Auth Kernel (`modulos.auth_kernel`) | login, refresh, logout, me/acl, password, 2FA | bootstrap organizacional, ownership de company/branch/grants |
| Accounts (`apps.accounts`) | `User`, sesiones refresh, retos 2FA, migraciones, señales | orquestación de bootstrap, creación de estructura org, siembra RBAC |
| IAM / Tenant / Policy | identidad, membresías, contexto, RBAC, grants, SoD | stock, correlativos fiscales, journal final |
| Integration / Event Backbone | outbox, inbox, envelope, retry, replay, dedupe | lógica de dominio primaria |
| Accounting | `EconomicEvent`, `PostingRuleSet`, `JournalDraft`, `JournalEntry`, close | hechos operativos primarios |
| CEC | validación, reconciliación, evidencia, exceptions, manifests, gates | mutación de verdad primaria, posting final |
| Billing | documentos, estados, numeración, issue, void, linkage documental | stock/costo, journal final |
| Inventory | movimientos, balances derivados, costo, transferencias, ledger | numeración fiscal, journal final |
| Payments & Cash | intents, sesiones de caja, movimientos de caja, conciliación provider | journal final y ownership contable final |
| Reportes | salidas reproducibles, consultas derivadas, exportaciones controladas | verdad operativa o financiera primaria |
| Dashboard | composición visual y lecturas derivadas | ownership de dominio o reglas del negocio |

## Reglas de implementación

- Billing integra con Inventory/Accounting solo vía servicios y eventos canónicos.
- Inventory integra con Fuel/Billing sin permitir mutación directa por fuera del kernel.
- Payments/Cash puede producir eventos operativos, pero el cierre financiero formal sigue en Accounting.
- CEC abre excepciones y gates; no “arregla” manualmente datos fuente.
- Bootstrap inicial se divide por ownership: IAM (status/init-admin) y ORG (organization).

## Efecto sobre el código

- El backend activo es `backend/src`; cualquier referencia operativa a `backend/` es legacy.
- Los cambios de hardening deben explicitar qué frontera refuerzan y qué frontera no cruzan.
