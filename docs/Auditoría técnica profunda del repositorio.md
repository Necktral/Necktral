# Necktral ERP/CRM — Auditoría técnica profunda del repositorio (documento ejecutable de decisión)

- Versión: v2.0
- Fecha: 2026-03-13
- Estado: Activo para ejecución (priorización 30/60/90)
- Alcance: revisión técnica del repositorio local `ERP_CRM` (backend, contratos, CI/QA y operación)
- Método: análisis estático de código/configuración/documentación + muestreo cruzado de hallazgos críticos
- Corte de evidencia: commit `0d8be91`

## Resumen ejecutivo

Este documento reemplaza el formato narrativo anterior por un formato de decisión y seguimiento. La tesis técnica principal se mantiene: el stack base está bien estructurado, pero el punto débil actual es la gobernanza de evidencia y la convergencia contractual de Sync.

Supuestos y defaults aplicados en esta versión:

- Rigor balanceado: evidencia fuerte en riesgos críticos, sin pretensión de cobertura exhaustiva de todos los módulos.
- Alcance de esta iteración: mejora documental; no se ejecutan cambios de código.
- Idioma y forma: español, accionable, versionado y con enlaces directos a código, alineado a [docs/README.md](README.md) (Reglas, L51-L57).
- Cuando no hay prueba concluyente de operación (por ejemplo, terminación TLS real en borde), se marca explícitamente como `pendiente de validación`.

Opinión avanzada consolidada:

- El riesgo estructural #1 es la deriva contractual entre Sync canónico y legacy, no la falta de funcionalidades.
- Hay controles de seguridad ya implementados en backend productivo; el gap está en validar y cerrar borde/proxy, no en reabrir hardening base ya existente.

## Riesgos priorizados

| ID | Riesgo | Severidad | Impacto | Probabilidad | Estado | Evidencia verificable | Acción prioritaria | KPI de cierre |
|---|---|---|---|---|---|---|---|---|
| R-01 | Dualidad de protocolos Sync (`/api/sync/` vs `/api/sync-hmac/`) | Critical | Inconsistencia funcional, mayor superficie y deuda operativa | Alta | Pendiente | [config/urls.py](../backend/src/config/urls.py) (L38-L39), [sync_engine/views.py](../backend/src/apps/sync_engine/views.py) (L277-L313), [sync/views.py](../backend/src/apps/sync/views.py) (L33-L120) | Definir núcleo único de ejecución y dejar legacy como wrapper sin lógica de negocio | 100% de batches legacy ejecutan core v2; 0 rutas con idempotencia paralela |
| R-02 | Contrato v2 no convergido completamente al core (`protocol_version/ts/nonce/auth`) | High | Riesgo contractual y de compatibilidad futura | Alta | Pendiente | [docs/CONTRACT_PACK_v2.0.md](CONTRACT_PACK_v2.0.md) (L20-L22, L40), [sync_engine/views.py](../backend/src/apps/sync_engine/views.py) (L286-L313) | Definir y ejecutar plan de convergencia por fases (gateway/request-level + core) | Suite de contrato Sync v2 en verde + matriz de compatibilidad publicada |
| R-03 | OpenAPI expuesto con `AllowAny` en rutas de schema | High | Enumeración de superficie API en despliegues no aislados | Media | Parcial | [config/urls.py](../backend/src/config/urls.py) (L27-L29) | Aplicar política por entorno (`DEBUG/flag`) y control de acceso en prod | En prod, `/api/schema/*` no accesible anónimamente |
| R-04 | Cobertura reportada sesgada por alcance de `sync_engine` | High | Señal incompleta para ORG/HR/RBAC/AUDIT | Alta | Parcial | [backend/.coveragerc](../backend/.coveragerc) (L1-L3), [Makefile](../Makefile) (L102-L103), [docs/QUALITY_COVERAGE_DIAGNOSTIC.md](QUALITY_COVERAGE_DIAGNOSTIC.md) (L9-L12) | Introducir cobertura por invariantes y tablero por dominios críticos | KPI por dominio (accounts/iam/rbac/audit/sync) con umbrales explícitos |

## Evidencia verificable

### Muestreo crítico (repositorio actual)

| Hallazgo | Estado observado | Evidencia |
|---|---|---|
| Existen dos rutas de sincronización activas | Confirmado | [config/urls.py](../backend/src/config/urls.py) (L38-L39) |
| `sync_engine` procesa batch con `X-Device-Id` y firma por comando | Confirmado | [sync_engine/views.py](../backend/src/apps/sync_engine/views.py) (L279-L313) |
| `sync-hmac` usa headers `X-Device-Ts/Nonce/Signature` + anti-replay propio | Confirmado | [sync/views.py](../backend/src/apps/sync/views.py) (L33-L101) |
| Contrato v2 exige endpoint canónico y wrappers legacy, y documenta lag request-level en core | Confirmado | [CONTRACT_PACK_v2.0.md](CONTRACT_PACK_v2.0.md) (L20-L22, L40) |
| OpenAPI está abierto con `AllowAny` | Confirmado | [config/urls.py](../backend/src/config/urls.py) (L27-L29) |
| Gate 2 corre coverage con rcfile centrado en `sync_engine` | Confirmado | [backend/.coveragerc](../backend/.coveragerc) (L1-L3), [Makefile](../Makefile) (L102-L103) |

### Recalibración de seguridad (evitar trabajo duplicado)

- `TLS/HSTS/cookies secure` en settings productivos ya está implementado a nivel Django: [prod.py](../backend/src/config/settings/prod.py) (L19-L32).
- El backlog operativo todavía marca trabajo de borde/terminación TLS y validación de rutas HTTP/HTTPS: [ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md](ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md) (EPICA A2, L53-L67).
- El `compose.prod.yaml` expone `web` en puerto 80, por lo que la terminación TLS puede estar fuera del stack y debe verificarse en infraestructura real: [compose.prod.yaml](../compose.prod.yaml) (L61-L62).

Decisión de estado para este frente:

- No clasificar como `pendiente puro`.
- Clasificar como `parcial` con foco en validación y cierre de gap de borde/proxy.

## Plan 30/60/90

### Quick wins (0-7 días)

1. Limpiar y fijar trazabilidad de esta auditoría (sin citas inválidas, con evidencia de archivo/línea).
2. Definir semáforo por riesgo (`pendiente/parcial/cerrado`) y owner por iniciativa.
3. Abrir tareas para restringir OpenAPI en prod y agregar prueba de regresión de acceso.
4. Publicar checklist de validación de borde TLS/HSTS (`curl -I`, headers, cookies `Secure`).

Entregable de salida: versión v2.1 del documento con matriz de ejecución firmada por Tech Lead + Security/Ops.

### Horizonte 30 días

1. Sync: diseño de convergencia v2 (legacy como wrapper real) con plan de retiro y métricas de adopción.
2. Cobertura: primera versión de tablero por invariantes (no solo `% total`).
3. Seguridad: OpenAPI restringido en producción + validación documentada del borde TLS.

Entregable de salida: RFC técnico + PRs de control perimetral y pruebas de contrato mínimas.

### Horizonte 60 días

1. Sync: implementar wrapper legacy que delega ejecución al core v2.
2. Contract tests: suite de compatibilidad para request-level y respuesta estable.
3. Cobertura: umbrales mínimos por dominio crítico (`accounts/iam/rbac/audit/sync`).

Entregable de salida: CI con reportes por dominio y compatibilidad legacy/v2 validada.

### Horizonte 90 días

1. Sync: retirar lógica de negocio residual en legacy y mantener sólo compatibilidad temporal.
2. Operación: cierre formal del gap TLS/HSTS en infraestructura de producción con evidencia repetible.
3. Gobernanza: integrar esta auditoría al ciclo de release como gate documental de decisión.

Entregable de salida: acta de cierre de riesgos R-01/R-02 y downgrade de severidad en R-03/R-04.

## Matriz de ejecución

| Iniciativa | Owner | Horizonte | KPI | Criterio de cierre |
|---|---|---|---|---|
| I-01 Convergencia Sync (core único) | Backend Lead | 30-90 días | `% requests legacy que delegan en core v2` | Legacy sin lógica de negocio propia y evidencia en pruebas de contrato |
| I-02 Contrato v2 request-level | Backend Lead + Arquitectura | 30-60 días | `tests de contrato Sync v2 en CI` | `protocol_version/ts/nonce/auth` validado de forma consistente en flujo definido |
| I-03 Restricción OpenAPI prod | Security Lead + Backend Lead | 0-30 días | `acceso anónimo a /api/schema/* en prod = 0` | Evidencia de pruebas negativas + configuración por entorno |
| I-04 Cobertura por invariantes | QA Lead + Backend Lead | 30-60 días | `umbral por dominio crítico publicado y monitoreado` | Reporte CI incluye dominios críticos con objetivos explícitos |
| I-05 Validación borde TLS/HSTS | Security/Ops | 0-60 días | `% ambientes productivos con validación TLS/HSTS firmada` | Checklist A2 completado y enlazado en runbook operativo |
| I-06 Gobernanza de evidencia | Tech Lead | 0-30 días | `100% riesgos High/Critical con evidencia verificable` | Auditoría versionada sin citas inválidas y con owners asignados |

## Anexos

### A. Opciones de parche (solo referencia)

1. OpenAPI por entorno en [config/urls.py](../backend/src/config/urls.py): reemplazar `AllowAny` por política condicional (`AllowAny` en dev, autenticado/permiso en prod).
2. Deprecation headers en legacy sync ([sync/views.py](../backend/src/apps/sync/views.py)): añadir `Deprecation`, `Sunset`, `Link` para hacer observable el retiro.
3. Cobertura por dominios en [backend/.coveragerc](../backend/.coveragerc): extender `source` y sostener umbrales por componente.

### B. Checklist de validación de consistencia documental

- [ ] Cero marcadores de cita inválidos en el documento.
- [ ] 100% de riesgos High/Critical con evidencia verificable.
- [ ] 100% de acciones con `owner`, `KPI`, `horizonte`, `criterio de cierre`.
- [ ] Sin contradicciones entre riesgo declarado y estado observado (`implementado/parcial/pendiente`).
