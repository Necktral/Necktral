# Throttling y limites (API)

Version: v1.0
Fecha: 2026-02-10
Estado: **Guia operativa**

## Objetivo

Definir limites de rate limit para reducir abuso y mantener estabilidad en picos, con valores verificables para backend (DRF) y Nginx.

## Targets (DRF)

Variables en `.env`/`.env.prod`:

- DRF_THROTTLE_ANON=30/min
- DRF_THROTTLE_USER=300/min
- DRF_THROTTLE_AUTH_LOGIN=10/min
- DRF_THROTTLE_AUTH_REFRESH=30/min
- DRF_THROTTLE_AUTH_LOGOUT=30/min
- DRF_THROTTLE_AUTH_SENSITIVE=20/min
- DRF_THROTTLE_ME_READ=120/min
- DRF_THROTTLE_ME_ACL_READ=60/min
- DRF_THROTTLE_BOOTSTRAP=5/hour

## Targets (Nginx)

En [docker/nginx/default.conf](../../docker/nginx/default.conf):

- auth_per_ip: 5r/m (burst 10)
- api_per_ip: 15r/s (burst 60)

## Criterios de ajuste

- Si hay 429 falsos en picos legitimos, subir primero `DRF_THROTTLE_USER` y `DRF_THROTTLE_ME_READ`.
- Si hay abuso real, bajar `DRF_THROTTLE_AUTH_LOGIN` y `auth_per_ip`.
- Siempre validar con k6 y registrar evidencia (p95 + tasa 429).

## Verificacion recomendada

- k6 baseline sin 429 forzados.
- k6 con `ENABLE_429_TEST=1` y `ONLY_429_TEST=1` para validar que el limite se dispara.
