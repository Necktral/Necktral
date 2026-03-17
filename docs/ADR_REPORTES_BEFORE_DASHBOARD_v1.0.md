# ADR — Reportes Before Dashboard v1.0

Version: v1.0  
Fecha: 2026-03-17  
Estado: Aprobado

## Decisión

Reportes va antes que Dashboard.

## Racional

- Dashboard es consumidor; no debe definir semántica ni ownership.
- Reportes necesita verdad endurecida aguas abajo: scope, auditoría, contratos y determinismo.
- Empujar Dashboard antes de cerrar kernels produce UI útil a corto plazo pero debilita semántica y reproducibilidad.

## Regla de ejecución

- No abrir APIs ni flujos de Dashboard como fuente de verdad.
- No abrir módulo transversal de Reportes hasta cerrar el bloque kernel/core.
- Cuando Reportes abra, deberá hacerlo con contrato reproducible, RBAC y auditoría.

## Condición de desbloqueo

Se habilita Reportes solo después de cerrar:

- IAM / Scope / RBAC / Audit
- Integration / Event Backbone
- Accounting
- CEC
- Billing
- Inventory
- Payments & Cash
