# ADR — Kernel Hardening Plan v1.0

Version: v1.0  
Fecha: 2026-03-17  
Estado: Aprobado para ejecución

## Decisión

Necktral adopta un programa de hardening backend-first, sprintable, centrado en `backend/src` y `modulos`.

El orden oficial de ejecución es:

1. IAM / Scope / RBAC / Audit
2. Integration / Event Backbone
3. Accounting
4. CEC
5. Billing
6. Inventory
7. Payments & Cash
8. Reportes
9. Dashboard

## Fundamento

- El backend ya cerró F1–F12 en staging-first; el foco ahora es congelar contratos e invariantes, no rehacer kernels maduros.
- IAM, Audit, Integration, Accounting y CEC ya existen como base real.
- Billing, Inventory y Payments/Cash ya tienen código operativo, pero aún requieren cierre semántico y contractual.
- Reportes y Dashboard quedan bloqueados hasta que el bloque kernel/core tenga evidencia verificable.

## Reglas operativas

- Ruta backend canónica: `backend/src`.
- `backend/` se considera árbol legacy/duplicado local no canónico.
- No introducir nuevos ownerships de dominio.
- No introducir reglas contables finales fuera de Accounting.
- PRs pequeños o medianos, por kernel o bloque coherente.
- Cada PR de hardening debe cerrar contrato, enforcement, tests, evidencia mínima y rollback.

## Definition of Done del programa

- ADRs y checklists publicados.
- Contratos clave congelados por documento y pruebas.
- Gaps reales cubiertos con tests/regresión, no con rediseño especulativo.
- Ningún trabajo de Reportes o Dashboard antes del cierre del bloque kernel/core.
