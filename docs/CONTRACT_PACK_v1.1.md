# Contract Pack v1.1 — Organización Contractual y Escalamiento Modular

Versión: v1.1  
Fecha: 2026-03-17  
Estado: **Vigente (base de organización)**

## Propósito

Este documento define la evolución contractual de organización del ERP/CRM para:

- ordenar el repositorio con una raíz canónica de backend;
- escalar a 15–20 módulos sin romper ownership ni contratos transversales;
- formalizar tipología de módulos (`kernel`, `core`, `transversal`, `vertical`);
- establecer un manifiesto mínimo obligatorio por módulo.

## Precedencia contractual

1. **Sync:** `docs/CONTRACT_PACK_v2.0.md` manda cuando exista divergencia en Sync.
2. **Organización base:** este `v1.1` manda en tipología modular, ownership y reglas de onboarding.
3. **Histórico:** `docs/CONTRACT_PACK_v1.0.md` queda como referencia base histórica.

## Alcance

- Kernels de verdad (dominio transversal): Billing, Inventory, Accounting, IAM/Policy.
- Módulos core de soporte: Payments/Cash, CEC, Integration/Event Backbone.
- Módulos transversales (planificados): Reportes, Dashboard.
- Módulos verticales operativos: Fuel y verticales futuros.
- Contratos transversales: scope, RBAC, auditoría, errores API y Sync/offline.

## Convención canónica de repositorio

### Backend canónico

- La raíz canónica de backend es: `login_module/` (código en `login_module/src/`).
- Todo contrato, CI, QA y documentación operativa debe apuntar a `login_module/`.

### Árbol legacy local

- `backend/` se considera **legacy local no canónico**.
- `backend/` no es fuente de verdad para desarrollo, CI ni release.
- Si existe localmente, su tratamiento es de higiene (`LEGACY` o `DELETE` según artefacto).

## Tipología formal de módulos

| Tipo | Rol | Puede ser fuente de verdad | Restricción principal |
|---|---|---|---|
| `kernel` | Dominio transversal reutilizable por múltiples módulos | Sí | No invadir ownership de otros kernels |
| `core` | Capacidades sistémicas de soporte operacional | Sí (solo en su dominio) | No mutar verdades ajenas fuera de contrato |
| `transversal` | Consumo/derivación multi-módulo (lectura, composición, observabilidad) | No (por defecto) | No crear verdad primaria de negocio |
| `vertical` | Operación específica por industria/proceso | Sí en su vertical | Debe consumir kernels/core vía contratos |

## Contratos transversales (vigentes)

### 1) Multiempresa (scope)

- Todo endpoint operativo corre con contexto efectivo `company` y opcional `branch`.
- El scope aplica en permisos, queries y particionamiento de auditoría.
- Denegaciones deben ser trazables con `required_scope` cuando aplique.

### 2) RBAC

- Permisos diferenciados por método y operación (`read`, `write`, `approve`, `reverse`, `export`).
- Catálogo y siembra bajo `seed_rbac_v01` (o evolución compatible documentada).

### 3) Auditoría contractual

- Toda escritura de estado debe emitir evento contractual válido.
- `event_type`, `reason_code` y `subject_type` deben pertenecer al catálogo permitido.
- Integridad encadenada + firma HMAC según política del entorno.

Referencia de catálogo: `login_module/src/apps/audit/contracts.py`.

### 4) Sync / offline

- Sync sigue la precedencia de `CONTRACT_PACK_v2.0.md`.
- Wrappers legacy pueden existir, pero el core canónico debe mantenerse unificado.

### 5) Errores API (envelope)

- Se mantiene el envelope único de errores definido en `v1.0`.
- `X-Request-Id` es obligatorio y debe corresponder con `error.request_id`.

## Reglas de escalamiento modular (15–20 módulos)

1. Ningún módulo nuevo entra sin tipología explícita (`kernel/core/transversal/vertical`).
2. Ningún módulo nuevo entra sin **Module Contract Manifest** aprobado.
3. Ningún módulo nuevo entra sin pruebas contractuales y evidencia de enforcement.
4. Todo módulo debe declarar explícitamente qué **posee** y qué tiene **prohibido** tocar.
5. Integraciones entre módulos deben ser versionadas y testeadas (contract tests).
6. Cambios breaking de contratos requieren versionado y migración explícita.

## Module Contract Manifest (obligatorio)

Todo módulo nuevo o endurecido debe declarar, como mínimo, los campos:

- `module_id`
- `module_type`
- `ownership`
- `forbidden_writes`
- `upstream_dependencies`
- `published_events`
- `consumed_events`
- `rbac_surface`
- `audit_catalog`
- `contract_version`

### Plantilla mínima (normativa)

```yaml
module_id: "<string-unico>"
module_type: "kernel|core|transversal|vertical"
contract_version: "1.0"

ownership:
  owns:
    - "<aggregate_or_capability>"
  invariants:
    - "<non_negotiable_rule>"

forbidden_writes:
  - "<module_or_aggregate>"

upstream_dependencies:
  - module_id: "<dependency_module>"
    contract_version: "<version>"
    mode: "api|event|query"

published_events:
  - event_type: "<EVENT_NAME>"
    schema_version: "1"

consumed_events:
  - event_type: "<EVENT_NAME>"
    source_module: "<module_id>"

rbac_surface:
  permissions:
    - "<permission.code>"

audit_catalog:
  event_types:
    - "<EVENT_TYPE>"
  reason_codes:
    - "<REASON_CODE>"
```

## Estado de módulos transversales planificados

### Reportes

- Estado: **planificado**.
- Tipo previsto: `transversal` (sujeto a ADR de implementación).
- Alcance en esta fase: contractual/documental; sin implementación funcional.

### Dashboard

- Estado: **planificado**.
- Tipo previsto: `transversal` (sujeto a ADR de implementación).
- Alcance en esta fase: contractual/documental; sin implementación funcional.

## Cierre contractual (DoD por módulo)

Un módulo se considera integrado cuando cumple:

1. scope + RBAC sin bypass;
2. auditoría contractual en writes;
3. contratos de integración versionados y probados;
4. manifest contractual completo y vigente;
5. evidencia verificable en QA/gates.

## No objetivos de esta versión

- No implementar funcionalmente `Reportes` ni `Dashboard`.
- No introducir cambios runtime/API por este documento.
- No promover `backend/` como ruta de desarrollo.

## Referencias

- Histórico base: `docs/CONTRACT_PACK_v1.0.md`
- Sync canónico: `docs/CONTRACT_PACK_v2.0.md`
- Blueprint de dominio: `docs/ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md`
- Matriz de endurecimiento: `docs/MATRIZ AVANZADA DE ENDURECIMIENTO DE KERNELS — NECKTRAL.md`

## Changelog

- 2026-03-17: Se crea `v1.1` para formalizar tipología modular, manifiesto contractual obligatorio, backend canónico y política de escalamiento.
