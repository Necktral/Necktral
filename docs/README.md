# Documentación — Necktral ERP/CRM

Esta carpeta contiene la documentación funcional y técnica del proyecto.

## Objetivo

- Centralizar “guías de organización” (contratos, estándares y decisiones).
- Mantener alineación con el backend (Django/DRF), la auditoría contractual y el motor de sincronización.
- Servir como referencia para desarrollo, QA y despliegues.

## Documentos actuales

- [contexto_nucleos.md](contexto_nucleos.md) — Estado ejecutivo por fases, publicación GitHub y roadmap activo.
- [ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md](ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md) — Blueprint maestro de kernels, CEC, adaptadores fiscales y evolución a GL formal.
- [operacion/README.md](operacion/README.md) — Runbooks, toolchains y operación release F1–F12.
- [CONTRACT_PACK_v1.0.md](CONTRACT_PACK_v1.0.md) — Guía contractual del sistema (organización de kernels/módulos).
- [ESTANDAR_COMENTARIOS.md](ESTANDAR_COMENTARIOS.md) — Estándar de comentarios en el código.
- [ADDENDUM_OFFLINE_FIRST_v1.0.md](ADDENDUM_OFFLINE_FIRST_v1.0.md) — Reglas offline-first (sync, idempotencia y auditoría).
- [ADDENDUM_SEGURIDAD_v1.0.md](ADDENDUM_SEGURIDAD_v1.0.md) — Plan de mejoras de seguridad y robustez.
- [ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md](ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md) — Backlog ejecutable del addendum de seguridad.
- [BILLING_KERNEL_v1.0.md](BILLING_KERNEL_v1.0.md) — Contrato operativo del kernel de facturación.
- [FUTURAS_MEJORAS.md](FUTURAS_MEJORAS.md) — Roadmap de mejoras futuras (técnicas y de producto).

## Documentación operacional

- [operacion/README.md](operacion/README.md) — Playbooks y plantillas para operar el negocio.
- [operacion/import_export/README.md](operacion/import_export/README.md) — Pack operativo Import/Export & Sourcing (B2B).
- [operacion/ROTACION_SECRETOS_v1.0.md](operacion/ROTACION_SECRETOS_v1.0.md) — Runbook de rotación de secretos.
- [operacion/CD_DEPLOY_v1.0.md](operacion/CD_DEPLOY_v1.0.md) — Deploy continuo en VPS con Docker Compose.
- [operacion/SHADOW_LEDGER_FASE4A_CERTIFICACION_v1.0.md](operacion/SHADOW_LEDGER_FASE4A_CERTIFICACION_v1.0.md) — Certificación real E2E de Fase 4A (paridad, determinismo y go-live).
- [operacion/GL_FASE7A_CERTIFICACION_v1.0.md](operacion/GL_FASE7A_CERTIFICACION_v1.0.md) — Certificación real E2E de Fase 7A (GL formal, reportes y revaluación FX).
- [operacion/GL_FASE7B_INTERCOMPANY_CONSOLIDACION_v1.0.md](operacion/GL_FASE7B_INTERCOMPANY_CONSOLIDACION_v1.0.md) — Operación y certificación real E2E de Fase 7B (intercompany y consolidación).
- [operacion/STAGING_FIRST_EJECUCION_TOTAL_v1.0.md](operacion/STAGING_FIRST_EJECUCION_TOTAL_v1.0.md) — Ejecución integral backend de Fase 6/7A/7B en staging.
- [operacion/MATRIZ_OWNERSHIP_SLA_FASE6_7B_v1.0.md](operacion/MATRIZ_OWNERSHIP_SLA_FASE6_7B_v1.0.md) — Responsables y SLA por alertas críticas del bloque.
- [operacion/CHECKLIST_PROMOCION_PRODUCCION_FASE6_7B_v1.0.md](operacion/CHECKLIST_PROMOCION_PRODUCCION_FASE6_7B_v1.0.md) — Checklist de promoción a producción (sin ejecución automática).
- [operacion/GO_LIVE_FASE8_PRODUCCION_v1.0.md](operacion/GO_LIVE_FASE8_PRODUCCION_v1.0.md) — Operación de go-live controlado Fase 8.
- [operacion/GO_LIVE_FASE9_PROVIDER_v1.0.md](operacion/GO_LIVE_FASE9_PROVIDER_v1.0.md) — Operación de provider fiscal (Fase 9).
- [operacion/GO_LIVE_FASE10_PROCUREMENT_v1.0.md](operacion/GO_LIVE_FASE10_PROCUREMENT_v1.0.md) — Go-live operativo de procurement 4B.
- [operacion/GO_LIVE_FASE11_INTERCOMPANY_AVANZADO_v1.0.md](operacion/GO_LIVE_FASE11_INTERCOMPANY_AVANZADO_v1.0.md) — Go-live de intercompany avanzado.
- [operacion/GO_LIVE_FASE12_CIERRE_MENSUAL_CONTINUO_v1.0.md](operacion/GO_LIVE_FASE12_CIERRE_MENSUAL_CONTINUO_v1.0.md) — Cierre mensual continuo con gate unificado.
- [operacion/CODEX_GOVERNANCE_HANDOFF_v1.0.md](operacion/CODEX_GOVERNANCE_HANDOFF_v1.0.md) — Gobernanza estricta de Codex v1.1, handoff por tipo de cambio y límites por dominio.
- [operacion/ALERTAS_RCA_RELEASE_QA_v1.0.md](operacion/ALERTAS_RCA_RELEASE_QA_v1.0.md) — Matriz RCA de alertas release/QA (bloqueante, warning controlado, ruido esperado).
- [operacion/PLAN_MAESTRO_F1_F12_CIERRE_OPERATIVO_v1.0.md](operacion/PLAN_MAESTRO_F1_F12_CIERRE_OPERATIVO_v1.0.md) — Secuencia maestra de cierre release/seguridad/staging y preparación productiva.
- [operacion/PR_RELEASE_F1_F12_CHECKLIST.md](operacion/PR_RELEASE_F1_F12_CHECKLIST.md) — Checklist para apertura y cierre del PR de release.

## Agente de codificación

- [COPILOT_CODING_AGENT.md](COPILOT_CODING_AGENT.md) — Funcionalidad, flujo y configuración del Copilot Coding Agent (Frente 1).

## Estrategia de ejecución

- [project/EXECUTION_FRONTS_STRATEGY.md](project/EXECUTION_FRONTS_STRATEGY.md) — División de trabajo en 3 frentes: Cloud (lógica), Local/Codex (tests), Frontend (APIs, fase posterior).
- [project/CODEX_OPERATING_BRIEF.md](project/CODEX_OPERATING_BRIEF.md) — Protocolo operacional para Codex (Frente 2).
- [project/NECKTRAL_MASTER_ROADMAP.md](project/NECKTRAL_MASTER_ROADMAP.md) — Secuencia priorizada de objetivos.

## Análisis y diagnóstico

- [ANALISIS_ROBUSTEZ_MULTIPLATAFORMA_v1.0.md](ANALISIS_ROBUSTEZ_MULTIPLATAFORMA_v1.0.md) — Fallos, cuellos de botella, inconsistencias, huecos y sugerencias para robustecer el sistema.
- [DIAGNOSTICO_SISTEMA_2026-03.md](DIAGNOSTICO_SISTEMA_2026-03.md) — Diagnóstico de madurez del sistema (marzo 2026).
- [QUALITY_COVERAGE_DIAGNOSTIC.md](QUALITY_COVERAGE_DIAGNOSTIC.md) — Estado de cobertura y calidad (objetivo: 95%–100% en todos los dominios).

## CI / QA

- CI principal (QA Gates 1–3): `.github/workflows/qa-ci.yml`
- Snapshot/reporting: `.github/workflows/pm-snapshot.yml`
- Security CI (blocking): `.github/workflows/security-ci.yml`
- Simulación de carga auth (k6): `.github/workflows/auth-load-simulation.yml`

## Topología de Fuel (transición vigente)

- Módulo canónico Fuel: `backend/src/apps/modulos/estacion_servicios`.
- Rutas:
  - canónica: `/api/backend/estacion-servicios/*`
  - alias canónico transicional: `/api/backend/fuel/*`
  - legacy: `/api/fuel/*` con headers `Deprecation`, `Sunset`, `Link`.

## Topología de Kernels (canónica)

- Accounting: `backend/src/apps/kernels/accounting`
- Billing: `backend/src/apps/kernels/facturacion`
- Inventory: `backend/src/apps/kernels/inventarios`
- Payments/Cash: `backend/src/apps/kernels/payments`
- Compatibilidad temporal (2 releases): `apps.modulos.{accounting,facturacion,inventarios,payments}`

## Reglas

- Todo en español.
- Mantener los documentos cortos, accionables y versionados (título + versión + fecha).
- Cuando un documento defina reglas/invariantes, enlazar a los módulos relevantes del código (p.ej. auditoría contractual, RBAC, sync engine).
- La evidencia operativa masiva vive fuera del versionado normal de GitHub y se consume por rutas/convención en `docs/operacion/evidencia/**`.
- En Git se mantienen solo runbooks, índices y referencias de evidencia (no dumps masivos).
