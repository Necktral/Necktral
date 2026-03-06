# Backend (backend) — Resumen rápido

Este archivo es un resumen local del backend. La documentación canónica vive en:

- [README raíz](../../README.md)
- [README del backend](../README.md)
- [BITACORA](../../BITACORA.md)
- [CHANGELOG](../../CHANGELOG.md)

## Arranque en DEV (Docker)

```bash
cp .env.example .env
docker compose up -d --build
```

Migraciones:

```bash
docker compose exec -T backend python src/manage.py migrate --noinput
```

## Puntos clave recientes

- Auditoría con keyring (`AUDIT_HMAC_KEYS`) y `signature_key_id`.
- Observabilidad básica: `X-Request-Id` y `/api/metrics/`.
- Listados ORG/HR/RBAC paginados (`limit/offset` + `count/limit/offset/results`).

## Comandos útiles

- `python src/manage.py seed_rbac_v01`
- `python src/manage.py bootstrap_company --company-name ... --branch-name ... --admin-username ...`
- `python src/manage.py seed_auth_users` (seed para k6)

## Tests

```bash
source system_wis/bin/activate
cd backend
pytest
```

---

Actualizado: 2026-02-09.
