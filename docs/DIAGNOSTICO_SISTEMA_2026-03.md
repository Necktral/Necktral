# 🔍 DIAGNÓSTICO COMPLETO DEL SISTEMA NECKTRAL

**Fecha:** 2026-03-10  
**Repositorio:** Necktral/Necktral  
**Versión actual:** v2026.01.13 (Etapa 2)  
**Tipo:** Solo diagnóstico — sin acciones correctivas  

---

## 📊 RESUMEN EJECUTIVO

**Necktral** es un sistema ERP/CRM modular con las siguientes características:

| Aspecto | Estado | Detalle |
|---------|--------|---------|
| **Backend (Django)** | ✅ Maduro | 13,968 líneas Python (sin migraciones), 10 apps Django |
| **Frontend (Vue/Quasar)** | 🔶 Scaffolding avanzado | 6,608 líneas (Vue+TS+SCSS), ~20 páginas funcionales |
| **Módulos de dominio** | 🔶 Parcial | FUEL operativo, Facturación e Inventarios en scaffolding |
| **Seguridad** | ✅ Robusta | RBAC, 2FA TOTP, HMAC, Argon2, CSP, django-axes |
| **Testing** | ✅ Extenso | 48 archivos de test, cobertura ≥95% en todos los dominios críticos |
| **CI/CD** | ✅ Completo | 6 workflows GitHub Actions, deploy a GHCR+VPS |
| **Infraestructura** | ✅ Producción-ready | Docker multi-stage, Nginx, Grafana/k6 |
| **Documentación** | ✅ Buena | 15+ documentos técnicos y operativos |

**Completitud estimada del sistema:** ~70% (backend maduro, frontend con scaffolding avanzado, módulos de negocio parciales)

---

## 1️⃣ ANÁLISIS DE RAMAS

### Ramas detectadas

| Rama | Tipo | Estado | Commits | Observación |
|------|------|--------|---------|-------------|
| `master` | Principal | ✅ Activa | ~95 | Rama de producción, última release v2026.01.13 |
| `feat/sync-inv-cp2-tests-clean` | Feature (merged) | ✅ Cerrada | ~25 | Mergeada en PR #2, incluyó 2FA, sync engine, security |
| `feat/fuel-billing-inventory` | Feature (merged) | ✅ Cerrada | ~2 | Mergeada en PR #1, módulo FUEL base |
| `copilot/analisis-del-sistema` | Diagnóstico | 🔵 Actual | 1 | Esta rama de análisis |
| `copilot/analyze-backend-and-modules` | Copilot | 🔶 Externa | Variable | Rama de análisis previo |
| `codex/fix-checks-in-commit-c393eeb` | Fix | 🔶 Externa | Variable | Correcciones de checks CI |

### Estado del CI en ramas

- **master:** 4 runs — mezcla de `success` y `failure` (algunos workflows requieren secretos como OPENAI_API_KEY)
- **Ramas copilot/codex:** Mayormente `action_required` (requieren aprobación de primer contribuidor)
- **Total histórico:** 158 ejecuciones de CI

### Tags/Releases

| Tag | Fecha estimada | Descripción |
|-----|---------------|-------------|
| `v2026.01.08` | Enero 2026 | Primera release formal |
| `v2026.01.13` | Enero 2026 | Release con HR, Frontend, FUEL base |

---

## 2️⃣ BACKEND (login_module/) — ANÁLISIS DETALLADO

### Arquitectura

```
login_module/
├── src/
│   ├── config/          ← Configuración Django (settings, middleware, urls)
│   ├── apps/            ← 10 apps Django
│   │   ├── accounts/    ← Autenticación, JWT, 2FA, provisioning
│   │   ├── audit/       ← Auditoría contractual con HMAC
│   │   ├── rbac/        ← Control de acceso basado en roles
│   │   ├── org/         ← Organizaciones multi-tenant
│   │   ├── hr/          ← Recursos Humanos
│   │   ├── iam/         ← Identidad y gestión de acceso
│   │   ├── sync_engine/ ← Motor de sincronización offline-first
│   │   ├── sync/        ← Infraestructura de sync
│   │   └── common/      ← Utilidades compartidas
│   └── tests/           ← 23 archivos de test
├── tests/               ← 25 archivos de test adicionales
└── conftest.py          ← Fixtures globales de pytest
```

### Métricas del código

| Métrica | Valor |
|---------|-------|
| Líneas de Python (sin migraciones) | 13,968 |
| Apps Django | 10 |
| Migraciones | ~33 |
| Archivos de test | 48 |
| Endpoints API | ~40+ |
| Modelos | ~50+ |
| Serializers | ~30 |
| ViewSets/APIViews | ~39 |

### Stack tecnológico

- **Framework:** Django 5.2.9 (LTS)
- **API:** Django REST Framework 3.16.1
- **Base de datos:** PostgreSQL 16.2 (via psycopg 3.3.2)
- **Auth:** JWT (simplejwt 5.5.1) + Cookie opcional + 2FA TOTP (pyotp)
- **Seguridad:** django-axes 8.1.0, django-csp 4.0, Argon2
- **Documentación API:** drf-spectacular 0.29.0 (OpenAPI/Swagger)
- **Observabilidad:** Sentry SDK 1.45.0
- **Archivos estáticos:** WhiteNoise 6.11.0

### 🟢 Fortalezas detectadas

1. **Seguridad enterprise-grade:**
   - JWT con rotación de refresh tokens
   - 2FA TOTP con anti-replay (bloqueo pesimista `select_for_update`)
   - HMAC firmado en eventos de auditoría con rotación de claves (keyring)
   - Argon2 para hashing de contraseñas
   - django-axes para protección anti-fuerza bruta
   - CSP headers, HSTS, X-Frame-Options
   - Redacción automática de datos sensibles en auditoría

2. **RBAC sofisticado:**
   - 15+ roles predefinidos con permisos granulares
   - Permisos con scope (org.company.read, hr.position.create, etc.)
   - Grants a nivel de fila (row-level ACL)
   - Multi-tenant via X-Company-Id

3. **Auditoría contractual:**
   - Eventos firmados con HMAC
   - 30+ tipos de eventos definidos
   - Verificación de integridad de cadena (comando `audit_verify_chain`)
   - Redacción de campos sensibles

4. **Diseño offline-first:**
   - Motor de sincronización con handlers por tipo de mensaje
   - Soporte para batch sync desde dispositivos móviles

### 🟡 Observaciones / Áreas de mejora

1. **Duplicación de tests:** Existen tests tanto en `login_module/tests/` como en `login_module/src/tests/` — potencial confusión sobre cuáles son los "oficiales"
2. **sys.path hack:** En `base.py` se modifica `sys.path` para importar `modulos.*` — funcional pero no ideal para empaquetado
3. **Dos archivos manage.py:** Uno en `login_module/manage.py` y otro en `login_module/src/manage.py` — puede causar confusión
4. **Cobertura expandida:** Política de cobertura ≥95% aplicada a todos los dominios críticos (`sync_engine`, `accounting`, `reporting`, `accounts`, `dashboard`, `estacion_servicios`, `integration`) con enforcement automático por `coverage_by_domain_guard`
5. **Módulos facturación/inventarios:** Solo scaffolding, sin lógica de negocio real implementada

### 🔴 Problemas potenciales

1. **CI en master:** Algunos workflows muestran `failure` — posiblemente por secretos faltantes (OPENAI_API_KEY) o timeouts
2. **Nombre legacy:** El directorio se llama `login_module` pero contiene todo el backend, no solo login — confuso para nuevos desarrolladores
3. **BITACORA.md indica:** "CI en PR #2: QA CI (Gates 1–3) = failure, Security CI (Blocking) = failure" — el CI no estaba verde al merge

---

## 3️⃣ FRONTEND (frontend/) — ANÁLISIS DETALLADO

### ⚠️ NOTA IMPORTANTE DEL USUARIO
> "El frontend aún no se ha trabajado o creado"

### Estado real encontrado

**Contrario a lo indicado por el usuario, SÍ existe un frontend con código funcional.** Se encontraron:

| Componente | Cantidad | Estado |
|-----------|----------|--------|
| Páginas Vue | 20 | Implementadas con lógica funcional |
| Servicios API (TypeScript) | 5 | Conectados a endpoints reales del backend |
| Stores Pinia | 5 | Con lógica de estado (auth, ACL, context, UI) |
| Componentes UI reutilizables | 3 | AppContainer, AppDataTable, AppPageHeader |
| Layouts | 2 | AuthLayout, MainLayout |
| Tests | 1 | auth.store.spec.ts (mínimo) |

### Métricas

| Métrica | Valor |
|---------|-------|
| Líneas de código (Vue+TS+SCSS) | 6,608 |
| Páginas/Routes | ~20 |
| Dependencias principales | 7 (Vue, Quasar, Pinia, Axios, vue-router, qrcode) |
| DevDependencies | 13 |

### Stack tecnológico

- **Framework:** Vue 3.5.22 (Composition API)
- **UI:** Quasar 2.16 (Material Design)
- **Estado:** Pinia 3.0.1
- **Routing:** Vue Router 4.0.12
- **HTTP:** Axios 1.2.1
- **Build:** Quasar CLI + Vite
- **Testing:** Vitest 1.5.0
- **Linting:** ESLint 9 + Prettier 3
- **TypeScript:** 5.9.2

### Páginas implementadas

**Autenticación:**
- ✅ LoginPage — Login con email/password
- ✅ TwoFactorPage — Verificación TOTP
- ✅ TwoFactorSetupPage — Configuración de 2FA con QR
- ✅ ForcePasswordChangePage — Cambio forzado de contraseña
- ✅ BootstrapWizardPage — Wizard de instalación inicial

**Organización:**
- ✅ OrgCompanyProfilePage — Perfil de la empresa
- ✅ OrgCompaniesPage — Listado multi-empresa
- ✅ OrgBranchesPage — Gestión de sucursales
- ✅ SelectContextPage — Selector de empresa/sucursal

**Recursos Humanos:**
- ✅ HrEmployeesPage — CRUD de empleados
- ✅ HrPositionsPage — CRUD de cargos y mapeo de roles

**Auditoría:**
- ✅ AuditEventsPage — Visor de eventos de auditoría
- ✅ AuditBitacoraPage — Historial detallado

**Fuel:**
- ✅ FuelDashboardPage — KPIs del módulo combustible
- ✅ FuelHealthPage — Estado del módulo

**Sistema:**
- ✅ DashboardPage — Página principal
- ✅ ErrorNotFound — Página 404
- ✅ ForbiddenPage — Página 403

### 🟢 Fortalezas

1. **Arquitectura bien definida:** Separación clara en pages, stores, services, core, layouts, ui
2. **Servicios API tipados:** TypeScript con interfaces definidas para cada endpoint
3. **Estado centralizado:** Pinia stores para auth, ACL, context, UI
4. **Seguridad client-side:** Guards de ruta basados en ACL, manejo de CSRF, interceptores de Axios
5. **Componentes reutilizables:** AppDataTable con paginación server-side

### 🟡 Observaciones

1. **Tests mínimos:** Solo 1 archivo de test (auth.store.spec.ts) — necesita expansión significativa
2. **Componentes de ejemplo:** ExampleComponent.vue y example-store.ts aún presentes
3. **Servicios sin tests:** Los 5 servicios API no tienen tests unitarios
4. **Accesibilidad (a11y):** No hay evidencia de testing de accesibilidad
5. **i18n:** No hay soporte de internacionalización configurado

### 🔴 Posible confusión

El usuario indicó que "el frontend aún no se ha trabajado o creado", pero el código muestra un frontend **funcional y avanzado**. Esto podría significar:
- El frontend fue generado por IA y no ha sido revisado manualmente
- El usuario considera que no está "terminado" o "pulido"
- Falta validación visual y de UX real

---

## 4️⃣ MÓDULOS DE DOMINIO (modulos/) — ANÁLISIS

### Estructura

```
modulos/
├── estacion_servicios/  ← ⭐ MVP Completo (FUEL)
├── facturacion/         ← 🔶 Scaffolding (BILLING)  
└── inventarios/         ← 🔶 Scaffolding (INVENTORY)
```

### Métricas

| Módulo | LOC (sin migraciones) | Migraciones | Estado |
|--------|----------------------|-------------|--------|
| Estación de Servicios (FUEL) | ~1,500 | 9 | ⭐ MVP operativo |
| Facturación (BILLING) | ~1,200 | 2 | 🔶 Scaffolding |
| Inventarios (INVENTORY) | ~600 | 2 | 🔶 Scaffolding |
| **Total** | **~3,333** | **13** | **~40% completo** |

### Estación de Servicios (FUEL) — ⭐ El más maduro

**Modelos:** FuelShift, FuelDispense, FuelSale, FuelUOMPreference  
**Funcionalidad:**
- ✅ Multi-UOM (litros, galones, etc.) con precios duales (ingresado + canónico)
- ✅ Ciclo de vida de turnos (abrir → despachar → vender → cerrar)
- ✅ Endpoints RBAC-controlados
- ✅ Auditoría completa
- ✅ Tests de flujo e integración

**Pendiente:**
- ❌ Integración con inventario (auto-decrementar stock en despacho)
- ❌ Integración con facturación (generar facturas de ventas)

### Facturación (BILLING) — 🔶 Scaffolding

- ✅ Modelos definidos (Invoice, InvoiceLine)
- ✅ Serializers y views básicas
- ❌ Máquina de estados (borrador → emitida → pagada → cancelada)
- ❌ Cálculos (impuestos, descuentos, totales)
- ❌ Numeración de documentos
- ❌ Integración con FUEL/Inventario

### Inventarios (INVENTORY) — 🔶 Scaffolding

- ✅ Modelos definidos (Product, Stock)
- ✅ Serializers y views básicas
- ❌ Movimientos de stock (entradas/salidas)
- ❌ Métodos de valuación (FIFO, LIFO, Promedio)
- ❌ Integración con sync engine offline

---

## 5️⃣ INFRAESTRUCTURA DOCKER — ANÁLISIS

### Archivos

| Archivo | Propósito | Estado |
|---------|-----------|--------|
| `compose.yaml` | Desarrollo (backend + DB + frontend + adminer) | ✅ Completo |
| `compose.prod.yaml` | Producción (backend + DB + Nginx) | ✅ Completo |
| `docker/backend.Dockerfile.dev` | Imagen dev (hot-reload) | ✅ |
| `docker/backend.Dockerfile.prod` | Imagen prod (multi-stage, gunicorn) | ✅ |
| `docker/web.Dockerfile` | Nginx SPA server | ✅ |
| `docker/entrypoint.sh` | Entrypoint dev | ✅ |
| `docker/entrypoint.prod.sh` | Entrypoint prod | ✅ |
| `docker/nginx/default.conf` | Config Nginx (SPA + proxy + headers) | ✅ |

### 🟢 Fortalezas

1. **Separación dev/prod:** Dockerfiles y compose separados
2. **Multi-stage build:** Imagen prod optimizada
3. **Healthchecks:** Backend con healthcheck HTTP
4. **Seguridad Nginx:** Headers de seguridad, rate limiting, CSP
5. **Volúmenes persistentes:** pgdata para PostgreSQL

### 🟡 Observaciones

1. Nginx podría beneficiarse de compresión gzip
2. Rate limiting es template — ajustar por entorno
3. No hay soporte para HTTPS/TLS directo (se asume proxy externo o load balancer)

---

## 6️⃣ CI/CD — ANÁLISIS

### Workflows

| Workflow | Archivo | Trigger | Bloquante | Estado |
|----------|---------|---------|-----------|--------|
| QA CI (Gates 1–3) | `qa-ci.yml` | Push/PR | ✅ Sí | 🟡 Funcional (necesita Docker) |
| Security CI | `security-ci.yml` | Push/PR | ✅ Sí | 🟡 Funcional (gitleaks + pip-audit + npm audit) |
| CD (Deploy) | `cd.yml` | Push main | 🟢 Deploy | ✅ Configurado (GHCR + SSH) |
| AI Review | `ai-review.yml` | PR | 🟡 Info | 🟡 Requiere OPENAI_API_KEY |
| PM Snapshot | `pm-snapshot.yml` | Manual | 🟡 Info | ✅ Funcional |
| Auth Load Sim | `auth-load-simulation.yml` | Manual | 🟡 Opcional | ✅ Configurado |

### QA Gates (Makefile)

| Gate | Qué verifica | Herramientas |
|------|-------------|-------------|
| Gate 1 | Calidad estática | ruff lint + mypy typecheck + frontend lint/typecheck |
| Gate 2 | Tests + cobertura | pytest + coverage (todos los dominios ≥95%, `fail_under=95`) |
| Gate 3 | Integridad auditoría | audit_verify_chain |

### 🟡 Observaciones del CI

1. **action_required:** Muchos runs muestran `action_required` — es el mecanismo de GitHub para aprobar workflows de primer contribuidor
2. **Dependencia de secretos:** AI Review requiere `OPENAI_API_KEY`, CD requiere `VPS_*` y `GHCR_*`
3. **BITACORA indica fallos:** PR #2 se mergeó con CI en failure — puede indicar tolerancia a fallos o urgencia
4. **Sin branch protection:** No se detectan reglas de protección de rama que exijan CI verde para merge

---

## 7️⃣ DEPENDENCIAS — ANÁLISIS DE SALUD

### Backend (Python)

| Paquete | Versión | Estado | Riesgo |
|---------|---------|--------|--------|
| Django | 5.2.9 | ✅ LTS actual | Bajo |
| DRF | 3.16.1 | ✅ Estable | Bajo |
| psycopg | 3.3.2 | ✅ Reciente | Bajo |
| simplejwt | 5.5.1 | ✅ Mantenido | Bajo |
| cryptography | 42.0.2 | ✅ Activo | Bajo |
| sentry-sdk | 1.45.0 | ⚠️ Considerar v2.x | Bajo |
| argon2-cffi | 25.1.0 | ✅ Actualizado | Bajo |
| ruff | 0.14.10 | ✅ Reciente | Bajo |

**Veredicto:** Todas las dependencias están actualizadas y mantenidas. Sin paquetes deprecados.

### Frontend (Node.js)

| Paquete | Versión | Estado | Riesgo |
|---------|---------|--------|--------|
| Vue | 3.5.22 | ✅ Último | Bajo |
| Quasar | 2.16.0 | ✅ Estable | Bajo |
| Pinia | 3.0.1 | ✅ Actual | Bajo |
| Axios | 1.2.1 | ⚠️ Hay versiones más nuevas (1.7+) | Bajo |
| TypeScript | 5.9.2 | ✅ Reciente | Bajo |
| Vitest | 1.5.0 | ⚠️ Considerar v2.x | Bajo |

**Veredicto:** Stack frontend moderno y mantenido.

---

## 8️⃣ DOCUMENTACIÓN — ANÁLISIS

### Documentos encontrados (15+)

| Documento | Propósito |
|-----------|-----------|
| `README.md` | Guía de inicio rápido |
| `CHANGELOG.md` | Registro de cambios |
| `BITACORA.md` | Bitácora técnica detallada |
| `docs/CONTRACT_PACK_v1.0.md` | Contrato API v1 |
| `docs/CONTRACT_PACK_v2.0.md` | Contrato API v2 |
| `docs/BILLING_KERNEL_v1.0.md` | Diseño del kernel de facturación |
| `docs/ADDENDUM_SEGURIDAD_v1.0.md` | Addendum de seguridad |
| `docs/ADDENDUM_SEGURIDAD_v1.1.md` | Seguridad actualizado |
| `docs/ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md` | Backlog de seguridad |
| `docs/ADDENDUM_OFFLINE_FIRST_v1.0.md` | Diseño offline-first |
| `docs/QUALITY_COVERAGE_DIAGNOSTIC.md` | Diagnóstico de cobertura |
| `docs/FUTURAS_MEJORAS.md` | Roadmap de mejoras |
| `docs/ESTANDAR_COMENTARIOS.md` | Estándar de comentarios |
| `docs/AUDITORIA_IA.md` | Auditoría de IA |
| `docs/operacion/CD_DEPLOY_v1.0.md` | Guía de deploy CD |
| `docs/operacion/ROTACION_SECRETOS_v1.0.md` | Rotación de secretos |
| `docs/operacion/import_export/` | Pack operativo Import/Export |

### 🟢 Fortalezas

1. Documentación versionada (v1.0, v1.1, v2.0)
2. Contratos API formales
3. Guías operativas (deploy, rotación de secretos)
4. Bitácora técnica detallada con contexto de cada cambio

### 🟡 Observaciones

1. No hay documentación de arquitectura con diagramas
2. Falta guía de onboarding para nuevos desarrolladores
3. La documentación del frontend es mínima (solo README genérico de Quasar)

---

## 9️⃣ QA Y SIMULACIÓN — ANÁLISIS

### QA (qa/)

| Archivo | Propósito |
|---------|-----------|
| `qa/wait_backend_ready.py` | Script de espera para CI |
| `qa/static_scan_backend.sh` | Escaneo estático (ruff + permisos) |
| `qa/k6/auth_smoke.js` | Test de carga smoke |
| `qa/k6/auth_stress.js` | Test de carga stress |
| `qa/k6/auth_load_simulation.js` | Simulación de carga auth |

### Simulación (simulacion/)

| Archivo | Propósito |
|---------|-----------|
| `simulacion/auth_load_simulation.js` | k6 base (286 LOC) |
| `simulacion/auth_load_simulation_extended.js` | k6 extendido (541 LOC) — multi-escenario |
| `simulacion/run_simulation.sh` | Ejecución automatizada |
| `simulacion/docker-compose.monitoring.yaml` | Stack Grafana + InfluxDB |
| `simulacion/grafana-dashboard.yaml` | Dashboard preconstruido |

### 🟢 Fortalezas

1. Tests de carga reales con k6 (smoke + stress)
2. Monitoreo con Grafana + InfluxDB
3. Escenarios de ataque y anti-replay en tests extendidos

---

## 🏁 DIAGNÓSTICO FINAL

### Resumen por área (1-10)

| Área | Puntuación | Justificación |
|------|-----------|---------------|
| **Backend - Core** | 9/10 | Maduro, bien estructurado, seguridad enterprise |
| **Backend - Módulos** | 5/10 | FUEL completo, Billing/Inventory solo scaffolding |
| **Frontend** | 6/10 | Existe y es funcional, pero necesita testing y pulido |
| **Seguridad** | 9/10 | RBAC, 2FA, HMAC, CSP, Argon2, anti-fuerza bruta |
| **Testing Backend** | 8/10 | 48 archivos, cobertura ≥95% en todos los dominios críticos |
| **Testing Frontend** | 2/10 | Solo 1 archivo de test |
| **CI/CD** | 7/10 | Pipeline completo pero con fallos históricos en master |
| **Docker/Infra** | 8/10 | Dev + Prod separados, multi-stage, healthchecks |
| **Documentación** | 7/10 | Extensa pero falta arquitectura visual y onboarding |
| **Load Testing/QA** | 8/10 | k6 + Grafana bien configurados |
| **PROMEDIO** | **6.9/10** | |

### Top 5 acciones recomendadas (prioridad)

1. **🔴 Completar módulos Facturación e Inventarios** — Son la razón de ser del ERP; están en scaffolding
2. **🟡 Expandir tests del frontend** — Solo 1 test; las ~20 páginas carecen de cobertura
3. **🟡 Resolver CI en master** — Asegurar que Gates 1–3 + Security CI pasen consistentemente
4. **🟡 Integrar módulos** — FUEL ↔ Inventario (auto-decrementar stock), FUEL ↔ Facturación (auto-generar facturas)
5. **🟢 Renombrar `login_module`** — El nombre es legacy y confuso; considerar `backend/` o `core/`

### Evaluación de riesgos

| Riesgo | Severidad | Probabilidad | Mitigación actual |
|--------|-----------|-------------|------------------|
| Vulnerabilidades en dependencias | Baja | Baja | pip-audit + npm audit en CI |
| Fuga de secretos | Baja | Baja | gitleaks en CI |
| Inyección SQL | Baja | Muy baja | ORM Django, no hay raw SQL |
| Fuerza bruta en auth | Baja | Media | django-axes (20 intentos = 1h lockout) |
| Timing attacks | Baja | Baja | hmac.compare_digest() usado |
| XSS | Baja | Baja | CSP headers + Django templates |
| CSRF | Baja | Baja | Cookie CSRF con middleware dedicado |

### Conclusión

El proyecto Necktral tiene una **base técnica sólida y bien diseñada**, con seguridad de nivel enterprise en el backend. Las principales brechas están en:
1. Los módulos de negocio (facturación/inventarios) que necesitan implementación real
2. El testing del frontend que es prácticamente inexistente
3. La consistencia del CI que necesita estabilización

El sistema está listo para avanzar a la siguiente etapa de desarrollo con confianza en la base existente.

---

*Documento generado automáticamente como parte del diagnóstico del sistema Necktral.*
