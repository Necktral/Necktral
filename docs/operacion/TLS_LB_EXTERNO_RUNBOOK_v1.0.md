# TLS LB Externo Runbook (v1.0)

Fecha: 2026-03-22  
Estado: Activo

## Objetivo

Operar el stack con terminacion TLS en LB externo y Nginx interno en `:80`, dejando a Django como source of truth para seguridad HTTP (HSTS/cookies/CSP).

## Arquitectura operativa

- Cliente -> HTTPS -> LB externo (termina TLS)
- LB -> HTTP interno -> Nginx del contenedor web (`listen 80`)
- Nginx -> backend Django (`backend:8000`)

Requisito de contrato:
- El LB debe enviar `X-Forwarded-Proto: https` al upstream.

## Headers requeridos del LB al backend web

- `X-Forwarded-Proto=https` (obligatorio)
- `X-Forwarded-For=<client_ip_chain>`
- `Host=<public_host>`

## Checklist post-deploy

1. HTTPS y redirect
- `curl -I http://<dominio>/api/schema/` debe redirigir a `https` en el borde.
- `curl -I https://<dominio>/api/schema/` debe responder sin mixed content.

2. HSTS y cookies secure
- `curl -I https://<dominio>/api/schema/ | grep -i strict-transport-security`
- Verificar cookies sensibles con atributo `Secure` en respuestas de auth.

3. CSP unica (sin duplicidad)
- `curl -I https://<dominio>/api/schema/ | grep -i content-security-policy`
- Debe existir una sola politica efectiva (emitida por Django).
- Confirmar ausencia de `unsafe-inline` en la politica enforce.

4. Health checks
- `GET /api/backend/iam/bootstrap/status/` = 200
- `GET /api/backend/metrics/` = 200 con usuario autorizado

## Resolucion rapida de incidentes

- Si falta HSTS: validar forwarding de `X-Forwarded-Proto=https` en LB.
- Si cookies no salen `Secure`: validar `DJANGO_DEBUG=0` y settings `prod.py`.
- Si aparece doble CSP: revisar que Nginx no inyecte CSP y que Django sea la unica fuente.
