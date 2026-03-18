# PR Checklist — Release F1-F12

PR target: `release/f6-f12-staging-pass-20260310 -> master`

## Titulo sugerido

`release: f1-f12 backend staging-pass + docs normalization`

## Checklist obligatorio

- [ ] CI backend en verde.
- [ ] CI seguridad en verde.
- [ ] `manage.py check` PASS.
- [ ] `pytest -q backend/src` PASS.
- [ ] `npm run lint/typecheck/test/build` PASS.
- [ ] Bug bounty local vigente en PASS.
- [ ] Resumen ejecutivo actualizado en `docs/contexto_nucleos.md`.
- [ ] Blueprint mantenido en `docs/ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md`.
- [ ] Riesgos y rollback documentados en descripcion del PR.

## Riesgos conocidos

- Vulnerabilidades frontend sin fix upstream pueden quedar en modo compensacion.
- Promocion a produccion bloqueada hasta gates de seguridad/staging en PASS.

## Politica de merge

- Squash merge.
- Sin merge con gates en rojo.
