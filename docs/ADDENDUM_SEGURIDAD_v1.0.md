# Addendum Seguridad v1.0 — Plan de mejoras de seguridad y robustez

Version: v1.0  
Fecha: 2026-02-07  
Estado: **Plan operativo de seguridad (vivo)**

## Proposito

Asegurar que el sistema evolucione hacia un nivel **profesional y robusto** de seguridad, reduciendo riesgos de explotacion (p. ej. secuestro de sesion, abuso de API, fugas de datos en auditoria) sin introducir fragilidad operativa.

Este plan surge de un debate interno sobre **excelencia tecnica vs. riesgo sistemico**, y equilibra las **mejoras de seguridad** con su **costo de complejidad** para un proyecto gestionado por un solo desarrollador.

## Contexto actual

- El sistema aun no tiene usuarios publicos ni esta desplegado en produccion abierta.
- La rama principal es `master`.
- Existe infraestructura y documentacion de soporte en el repo (ver referencias).

## Referencias

- Runbook de rotacion de secretos: [docs/operacion/ROTACION_SECRETOS_v1.0.md](operacion/ROTACION_SECRETOS_v1.0.md)
- Backlog de mejoras futuras: [docs/FUTURAS_MEJORAS.md](FUTURAS_MEJORAS.md)
- Auditoria IA en PRs: [docs/AUDITORIA_IA.md](AUDITORIA_IA.md)
- Addendum offline-first: [docs/ADDENDUM_OFFLINE_FIRST_v1.0.md](ADDENDUM_OFFLINE_FIRST_v1.0.md)

## Debilidades de seguridad identificadas

1. **Tokens JWT en almacenamiento web (`localStorage`) – riesgo XSS (historico).**

- Antes: tokens en `localStorage` con `Authorization: Bearer <token>`.
- Estado actual: mitigado con cookies HttpOnly + CSRF; el frontend ya no persiste tokens.

2. **HTTPS/HSTS no forzado por configuracion base.**
   - En settings base se observa `SECURE_SSL_REDIRECT = False` y `SECURE_HSTS_SECONDS = 0`.
   - Si en produccion no se habilita HTTPS/HSTS en el terminador TLS, hay riesgo de MITM.

3. **Politica CSP presente pero incompleta.**

- Estado actual: CSP base en modo enforce (default/script/style/object/base-uri/frame-ancestors/form-action).
- Report-only activo para `connect-src`, `img-src`, `font-src` con endpoint de reportes.
- Falta endurecer y remover `unsafe-inline` donde aplique.

4. **Auditoria con posible sobre-exposicion de datos sensibles.**
   - Los snapshots de auditoria pueden contener PII o datos sensibles si no se filtran.
   - La UI de bitacora podria exponer campos que nunca debieron registrarse.

## Atenuantes y trade-offs actuales

- **`localStorage` por simplicidad:** se priorizo facilidad de implementacion en SPA, asumiendo mitigacion fuerte de XSS.
- **HTTPS/HSTS desactivado en dev:** se asume terminacion TLS en Nginx o balanceador en prod.
- **CSP parcial:** se implemento un minimo viable para evitar romper la UI durante desarrollo.
- **Auditoria exhaustiva:** se priorizo trazabilidad e integridad (firma HMAC), con filtrado pendiente.

## Estado actual (2026-02-09)

- Autenticacion por cookies HttpOnly + CSRF en SPA; sin tokens en `localStorage`.
- CSP base enforce + report-only para `connect-src` (endpoint `/api/csp/report/`).
- Nginx emite CSP report-only con `report-uri /api/csp/report/` para el frontend.
- Refresh tokens persistidos y revocables por sesion (rotacion y blacklist).
- Politica de contrasenas reforzada (longitud + complejidad).
- 2FA TOTP para cuentas admin con setup y QR (Anti-Replay garantizado).
- Security CI blocking: gitleaks + pip-audit + npm audit.
- Observabilidad basica: `X-Request-Id`, Sentry opcional y `/api/metrics/`.
- Auditoria con keyring (`AUDIT_HMAC_KEYS`) para rotacion segura de firmas.
- Logout idempotente con limpieza segura de cookies (incluso ante tokens corruptos).

## Riesgos pendientes (a confirmar)

- Configuracion TLS y headers en prod (HSTS, redireccion HTTPS, X-Forwarded-Proto).
- Throttling global fuera de login.
- Gobierno de secretos y segregacion por entorno.
- Supply chain (Dependabot, SBOM, pin de actions).
- Vectores XSS indirectos (ej. user-agent en UI de auditoria si se renderiza sin escape).

---

## Plan de accion priorizado

### A) Corto plazo (1–4 semanas)

1. **Hardening anti-XSS en frontend (CSP y sanitizacion)**
   - Objetivo: minimizar ejecucion de codigo no autorizado en el cliente.
   - Acciones:
     - Auditar el frontend en busca de `v-html` o render HTML crudo.
     - Fortalecer CSP con `base-uri 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, `form-action 'self'`, `connect-src` limitado.
     - Eliminar `unsafe-inline` donde sea posible (usar nonces/hashes si aplica).
   - DoD:
     - No hay `v-html` ni HTML crudo sin sanitizar.
     - CSP completa en runtime, con verificacion en consola.
     - PoC de XSS no ejecuta codigo.
   - Riesgos:
     - CSP muy estricta puede romper la UI; iterar con pruebas completas.

2. **Forzar HTTPS y HSTS en produccion**
   - Objetivo: cifrado obligatorio y prevencion de downgrade.
   - Acciones:
     - Redireccion HTTP->HTTPS en terminador TLS.
     - HSTS con `max-age` prudente (>= 6 meses) e `includeSubDomains` si aplica.
     - En Django prod: `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT = True` y cookies `Secure`.
   - DoD:
     - `curl -I` confirma redireccion y `Strict-Transport-Security`.
     - Cookies sensibles marcadas como `Secure`.
     - Documentacion de hardening en docs.
   - Riesgos:
     - Activar HSTS sin TLS valido puede bloquear acceso.

3. **Rate limiting y control de abuso en APIs clave**
   - Objetivo: prevenir scraping, abuso y degradacion del servicio.
   - Acciones:
     - Limites por ruta en Nginx para `/api/auth/*` y endpoints costosos.
     - Throttling DRF por tipo de endpoint (lectura vs escritura).
     - Limites de paginacion max en listados.
   - DoD:
     - 429 al exceder limites, con logs de eventos.
     - Uso normal no afectado por falsos positivos.
   - Riesgos:
     - Limites muy bajos bloquean usuarios legitimos.

4. **Redaccion de datos sensibles en auditoria**
   - Objetivo: mantener trazabilidad sin fuga de datos sensibles.
   - Acciones:
     - Allowlist por entidad para campos auditables.
     - Filtrar `before_snapshot`/`after_snapshot` y metadatos.
     - Validar permisos de lectura de bitacora.
   - DoD:
     - Tests que garantizan redaccion de campos prohibidos.
     - Integridad HMAC sigue pasando.
   - Riesgos:
     - Filtrado excesivo puede reducir utilidad forense.

5. **Gobernanza de secretos y configuracion sensible**
   - Objetivo: evitar secretos en repo y permitir rotacion segura.
   - Acciones:
     - Escaneo de secretos en CI (trivy fs ya ayuda; agregar reglas si falta).
     - Separar secrets por entorno.
     - Documentar rotacion y pasos de verificacion.
   - DoD:
     - CI marca secretos por error.
     - Runbook de rotacion operativo (ver referencia).
   - Riesgos:
     - Falsos positivos en scanning; ajustar reglas.

6. **Migracion de autenticacion (cookies HttpOnly + CSRF)**
   - Objetivo: eliminar tokens accesibles por JS y reducir impacto de XSS en browser.
   - Acciones:
     - Usar cookies HttpOnly como transporte primario en browser.
     - Mantener header para clientes no-browser bajo demanda.
     - Validar CSRF en mutaciones cuando el transporte sea cookie.
   - DoD:
     - Login/refresh/logout operan con cookies en SPA.
     - No hay tokens en `localStorage`.
   - Riesgos:
     - CORS/CSRF mal configurados pueden romper el flujo en prod.

7. **Contrato unificado de errores API**
   - Objetivo: errores consistentes y seguros para frontend.
   - Acciones:
     - Definir envelope `{code, message, details, request_id}`.
     - Mapear codes a `reason_code` de auditoria.
     - Ajustar frontend a nuevo formato.
   - DoD:
     - 100% errores relevantes siguen el mismo formato.
     - Tests de contrato pasan.
   - Riesgos:
     - Cambio coordinado backend/frontend para evitar regresiones.

8. **Observabilidad minima (errores, logs, trazabilidad)**
   - Objetivo: diagnosticar incidentes y correlacionar requests.
   - Acciones:
     - Integrar Sentry (backend + frontend).
     - Logs estructurados con `request_id`.
     - Metricas basicas (latencia, 401/403/5xx).
   - DoD:
     - Errores reproducibles rastreables por `request_id`.
     - Dashboard minimo operativo.
   - Riesgos:
     - Cuidar PII en eventos de monitoreo.

### B) Mediano plazo (1–3 meses)

1. **Pruebas frontend y E2E**
   - Objetivo: prevenir regresiones en auth, permisos y flujos criticos.
   - Acciones:
     - Unit/component tests (Vitest/Jest).
     - E2E (Playwright/Cypress) con flujos criticos.
   - DoD:
     - E2E corre en CI y protege rutas criticas.
   - Riesgos:
     - Fragilidad de tests si la UI cambia frecuentemente.

2. **CI/CD con despliegue reproducible**
   - Objetivo: releases trazables, rollback rapido y despliegue confiable.
   - Acciones:
     - Build -> tag -> push de imagenes Docker.
     - Deploy reproducible (compose/runner).
     - Rollback por tag.
   - DoD:
     - Release = tag = imagen = deploy.
   - Riesgos:
     - Configuracion de secrets y permisos en CI.

3. **Supply chain y dependencias**
   - Objetivo: reducir riesgos de librerias vulnerables.
   - Acciones:
     - Dependabot o equivalente.
     - SBOM si aplica.
     - Actions pinneadas por SHA.
   - DoD:
     - Actualizaciones automatizadas y revisables.
   - Riesgos:
     - Actualizaciones frecuentes pueden requerir QA adicional.

### C) Largo plazo (3–9 meses)

1. **Particionado/retencion de audit log**
   - Acciones: particionar por fecha, politica de retencion y archivado cifrado.

2. **Seguridad perimetral avanzada**
   - Acciones: WAF, reglas anti-bot, deteccion de anomalias.

3. **Threat modeling y revisiones recurrentes**
   - Acciones: documento por modulo y checklist por PR/release.

4. **Hardening multi-tenant extremo**
   - Acciones: evaluar RLS en Postgres si el negocio lo exige.

---

## Orden sugerido de implementacion

- Primero CSP/XSS y HTTPS/HSTS.
- Luego redaccion de auditoria y rate limiting.
- Despues secretos, contrato de errores y observabilidad.
- Finalmente migracion de autenticacion, pruebas, CI/CD y supply chain.

## Notas operativas

- Trabajar por PRs pequenos y secuenciales.
- Registrar cambios en CHANGELOG/BITACORA cuando se implementen.
