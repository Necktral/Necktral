# Documentación — Necktral ERP/CRM

Esta carpeta contiene la documentación funcional y técnica del proyecto.

## Objetivo

- Centralizar “guías de organización” (contratos, estándares y decisiones).
- Mantener alineación con el backend (Django/DRF), la auditoría contractual y el motor de sincronización.
- Servir como referencia para desarrollo, QA y despliegues.

## Documentos actuales

- [ESTANDAR_COMENTARIOS.md](ESTANDAR_COMENTARIOS.md) — Estándar de comentarios en el código.

- [CONTRACT_PACK_v1.0.md](CONTRACT_PACK_v1.0.md) — Guía contractual del sistema (organización de kernels/módulos).
- [ADDENDUM_OFFLINE_FIRST_v1.0.md](ADDENDUM_OFFLINE_FIRST_v1.0.md) — Reglas offline-first (sync, idempotencia y auditoría).
- [ADDENDUM_SEGURIDAD_v1.0.md](ADDENDUM_SEGURIDAD_v1.0.md) — Plan de mejoras de seguridad y robustez.
- [ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md](ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md) — Backlog ejecutable del addendum de seguridad.
- [ADDENDUM_MODULOS_BLUEPRINT_v1.0.md](ADDENDUM_MODULOS_BLUEPRINT_v1.0.md) — Blueprint obligatorio para nuevos módulos.
- [BILLING_KERNEL_v1.0.md](BILLING_KERNEL_v1.0.md) — Contrato operativo del kernel de facturación.
- [FUTURAS_MEJORAS.md](FUTURAS_MEJORAS.md) — Roadmap de mejoras futuras (técnicas y de producto).

## Documentación operacional

- [operacion/README.md](operacion/README.md) — Playbooks y plantillas para operar el negocio.
- [operacion/import_export/README.md](operacion/import_export/README.md) — Pack operativo Import/Export & Sourcing (B2B).
- [operacion/ROTACION_SECRETOS_v1.0.md](operacion/ROTACION_SECRETOS_v1.0.md) — Runbook de rotación de secretos.
- [operacion/CD_DEPLOY_v1.0.md](operacion/CD_DEPLOY_v1.0.md) — Deploy continuo en VPS con Docker Compose.

## CI / QA

- CI principal (QA Gates 1–3): `.github/workflows/qa-ci.yml`
- Snapshot/reporting: `.github/workflows/pm-snapshot.yml`
- Security CI (blocking): `.github/workflows/security-ci.yml`
- Simulación de carga auth (k6): `.github/workflows/auth-load-simulation.yml`

## Reglas

- Todo en español.
- Mantener los documentos cortos, accionables y versionados (título + versión + fecha).
- Cuando un documento defina reglas/invariantes, enlazar a los módulos relevantes del código (p.ej. auditoría contractual, RBAC, sync engine).
