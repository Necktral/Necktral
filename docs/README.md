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
- [FUTURAS_MEJORAS.md](FUTURAS_MEJORAS.md) — Roadmap de mejoras futuras (técnicas y de producto).

## Documentación operacional

- [operacion/README.md](operacion/README.md) — Playbooks y plantillas para operar el negocio.
- [operacion/import_export/README.md](operacion/import_export/README.md) — Pack operativo Import/Export & Sourcing (B2B).

## CI / QA

- CI principal (QA Gates 1–3): `.github/workflows/qa-ci.yml`
- Snapshot/reporting: `.github/workflows/pm-snapshot.yml`

Notas de robustez:

- Si el runner es limitado y ves `exit code 137` (OOM kill) durante `qa-backend-wait`, el backend fuerza `runserver` en CI (ver `docker/entrypoint.sh`).
- La espera de “backend ready” tiene timeout ampliado (ver `qa/wait_backend_ready.py`).

## Reglas

- Todo en español.
- Mantener los documentos cortos, accionables y versionados (título + versión + fecha).
- Cuando un documento defina reglas/invariantes, enlazar a los módulos relevantes del código (p.ej. auditoría contractual, RBAC, sync engine).
