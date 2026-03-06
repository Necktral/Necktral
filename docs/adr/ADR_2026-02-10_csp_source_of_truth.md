# ADR 2026-02-10 - CSP source of truth y report-only en Nginx

## Contexto

- El frontend se sirve por Nginx y el backend por Django.
- Existen politicas CSP en Django y en Nginx que pueden divergir.
- Se necesita visibilidad de violaciones antes de endurecer la politica.

## Decision

- Mantener el CSP enforce actual en Nginx para el frontend.
- Agregar un CSP report-only en Nginx con `report-uri /api/csp/report/`.
- Conservar django-csp para el backend y el endpoint de reportes.

## Alcance

- Solo el server Nginx y el endpoint de reportes CSP del backend.
- No se endurece el enforce en esta iteracion.

## Consecuencias

- Se obtiene evidencia de violaciones sin romper la UI.
- Se requiere revisar logs para evitar ruido.
- Paso siguiente: eliminar `unsafe-inline` en `style-src` cuando la UI lo permita.

## Riesgo

- Reportes pueden crecer si hay muchos assets o extensiones del navegador.
- La politica enforce aun permite `unsafe-inline` en estilos.

## Criterios de aceptacion

- El header `Content-Security-Policy-Report-Only` esta presente.
- El backend registra reportes via `/api/csp/report/`.
