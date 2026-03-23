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
- [CONTRACT_PACK_v1.1.md](CONTRACT_PACK_v1.1.md) — Guía contractual vigente para organización y escalamiento modular.
- [CONTRACT_PACK_v1.0.md](CONTRACT_PACK_v1.0.md) — Base histórica de organización contractual.
- [CONTRACT_PACK_v2.0.md](CONTRACT_PACK_v2.0.md) — Contrato canónico vigente para Sync v2.
- [operacion/INVENTARIO_P0_LOCAL_MULTISUCURSAL_v1.0.md](operacion/INVENTARIO_P0_LOCAL_MULTISUCURSAL_v1.0.md) — Operación P0 del módulo de inventario local multisucursal (wizard item master + kernel aditivo).
- [ESTANDAR_COMENTARIOS.md](ESTANDAR_COMENTARIOS.md) — Estándar de comentarios en el código.
- [ADDENDUM_OFFLINE_FIRST_v1.0.md](ADDENDUM_OFFLINE_FIRST_v1.0.md) — Reglas offline-first (sync, idempotencia y auditoría).
- [ADDENDUM_SEGURIDAD_v1.0.md](ADDENDUM_SEGURIDAD_v1.0.md) — Plan de mejoras de seguridad y robustez.
- [ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md](ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md) — Backlog ejecutable del addendum de seguridad.
- [BILLING_KERNEL_v1.0.md](BILLING_KERNEL_v1.0.md) — Contrato operativo del kernel de facturación.
- [FUTURAS_MEJORAS.md](FUTURAS_MEJORAS.md) — Roadmap de mejoras futuras (técnicas y de producto).
- [ADR_KERNEL_HARDENING_PLAN_v1.0.md](ADR_KERNEL_HARDENING_PLAN_v1.0.md) — Orden oficial del programa backend-first de hardening.
- [ADR_KERNEL_OWNERSHIP_BOUNDARIES_v1.0.md](ADR_KERNEL_OWNERSHIP_BOUNDARIES_v1.0.md) — Ownership y prohibiciones por kernel/módulo core.
- [ADR_AUTH_KERNEL_EXTRACTION_v2.0.md](ADR_AUTH_KERNEL_EXTRACTION_v2.0.md) — Separación de auth kernel y split de bootstrap IAM/ORG con wrappers legacy.
- [ADR_REPORTES_BEFORE_DASHBOARD_v1.0.md](ADR_REPORTES_BEFORE_DASHBOARD_v1.0.md) — Regla de secuenciación reportes antes que dashboard.
- [engineering/branching_strategy.md](engineering/branching_strategy.md) — Estrategia de rama troncal `master`, releases y protección GitHub.
- [engineering/backend_module_reorg.md](engineering/backend_module_reorg.md) — Estado canónico de layout backend (`apps.modulos/*` + `kernels/*`).
- [engineering/github_branch_protection_checklist.md](engineering/github_branch_protection_checklist.md) — Checklist operativa para branch protection en GitHub UI.
- [arquitectura/reporting_dashboard_architecture.md](arquitectura/reporting_dashboard_architecture.md) — Separación técnica entre reporting formal y dashboard ejecutivo.
- [adr/ADR-00X-reporting-vs-dashboard.md](adr/ADR-00X-reporting-vs-dashboard.md) — ADR de desacople reporting vs dashboard.
- [adr/ADR-00Y-branching-model.md](adr/ADR-00Y-branching-model.md) — ADR de modelo de ramas y gobernanza.
- [adr/ADR-00Z-backend-module-layout.md](adr/ADR-00Z-backend-module-layout.md) — ADR del layout canónico de backend.
- [ADR_AUDIT_TAXONOMY_MIN_v1.0.md](ADR_AUDIT_TAXONOMY_MIN_v1.0.md) — Taxonomía mínima de auditoría contractual por kernel.
- [ADR_ACCOUNTING_RULESET_V1_FREEZE.md](ADR_ACCOUNTING_RULESET_V1_FREEZE.md) — Freeze contractual de `PostingRuleSet v1`.
- [ADR_ACCOUNTING_EVENT_MATRIX_V1.md](ADR_ACCOUNTING_EVENT_MATRIX_V1.md) — Matriz oficial de eventos contables soportados.
- [ADR_PAYMENTS_ACCOUNTING_BOUNDARY_V1.md](ADR_PAYMENTS_ACCOUNTING_BOUNDARY_V1.md) — Frontera semántica actual entre Payments y Accounting.
- [repo_higiene/README.md](repo_higiene/README.md) — Índice de artefactos de reorganización y limpieza controlada.
- [repo_higiene/resumen_reorganizacion_v1.1.md](repo_higiene/resumen_reorganizacion_v1.1.md) — Resumen de inventario técnico, decisiones KEEP/LEGACY/DELETE y checklist por lotes.
- [module_manifests/auth_kernel.v1.yaml](module_manifests/auth_kernel.v1.yaml) — Manifiesto contractual del Auth Kernel.
- [module_manifests/accounts_storage.v1.yaml](module_manifests/accounts_storage.v1.yaml) — Manifiesto contractual de storage de identidad.
- [module_manifests/iam_bootstrap.v1.yaml](module_manifests/iam_bootstrap.v1.yaml) — Manifiesto contractual de bootstrap IAM.
- [module_manifests/org_bootstrap.v1.yaml](module_manifests/org_bootstrap.v1.yaml) — Manifiesto contractual de bootstrap ORG.

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
- [operacion/PLAN_MAESTRO_F1_F12_CIERRE_OPERATIVO_v1.0.md](operacion/PLAN_MAESTRO_F1_F12_CIERRE_OPERATIVO_v1.0.md) — Secuencia maestra de cierre release/seguridad/staging y preparación productiva.
- [operacion/PR_RELEASE_F1_F12_CHECKLIST.md](operacion/PR_RELEASE_F1_F12_CHECKLIST.md) — Checklist para apertura y cierre del PR de release.
- [operacion/CHECKLIST_KERNEL_HARDENING_PR_v1.0.md](operacion/CHECKLIST_KERNEL_HARDENING_PR_v1.0.md) — Checklist operativo para PRs de hardening por kernel.
- [operacion/KERNEL_HARDENING_BASELINE_v1.1.md](operacion/KERNEL_HARDENING_BASELINE_v1.1.md) — Baseline de ejecución y mapeo matriz->código->tests.
- [operacion/KERNEL_HARDENING_S1_ENDPOINT_MATRIX_v1.0.md](operacion/KERNEL_HARDENING_S1_ENDPOINT_MATRIX_v1.0.md) — Matriz de endpoints críticos para cobertura de scope/RBAC.
- [operacion/RUNBOOK_TRANSICION_ACCOUNTING_BACKEND_API_20260319.md](operacion/RUNBOOK_TRANSICION_ACCOUNTING_BACKEND_API_20260319.md) — Migración operativa de consumidores contables a `/api/backend/accounting/*`.

## CI / QA

- CI principal (QA Gates 1–3): `.github/workflows/qa-ci.yml`
- Snapshot/reporting: `.github/workflows/pm-snapshot.yml`
- Security CI (blocking): `.github/workflows/security-ci.yml`
- Simulación de carga auth (k6): `.github/workflows/auth-load-simulation.yml`

## Reglas

- Todo en español.
- Mantener los documentos cortos, accionables y versionados (título + versión + fecha).
- Cuando un documento defina reglas/invariantes, enlazar a los módulos relevantes del código (p.ej. auditoría contractual, RBAC, sync engine).
- Para backend, la ruta canónica de código es `backend/`; cualquier alias histórico (`login_module`) se considera legacy local no canónico.
- La evidencia operativa masiva vive fuera del versionado normal de GitHub y se consume por rutas/convención en `docs/operacion/evidencia/**`.
- En Git se mantienen solo runbooks, índices y referencias de evidencia (no dumps masivos).
