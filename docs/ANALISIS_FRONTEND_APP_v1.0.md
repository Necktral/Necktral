# ANÁLISIS PROFUNDO: FRONTEND Y "APP" — v1.0

Fecha: 2026-06-02
Rama: `claude/frontend-app-analysis-3kYAB`
Alcance: estado real del frontend web y de la "app" móvil, comparado con la documentación de diseño.

---

## 0. Veredicto sobre la premisa "frontend y app no se han trabajado"

No coincide con el repositorio. El **frontend web sí existe y es sustancial**; ya hay un
diagnóstico interno previo (`docs/DIAGNOSTICO_SISTEMA_2026-03.md`) que registra esa misma
creencia y la refuta con evidencia.

Matiz correcto:

- El **frontend web** está en estado *scaffolding avanzado / funcional*, no terminado.
- La **"app móvil" como app no existe**: no hay app nativa ni PWA. Lo que se llama "móvil"
  es la **misma SPA web** con un modo de presentación (`Taskflow`) que hoy es casi cosmético.

El trabajo está hecho en la web de escritorio; el hueco real está en la parte de "app".

---

## 1. Métricas reales

| Capa | Tamaño | Estado |
|---|---|---|
| Backend (Django/DRF) | ~83.800 LOC, 483 `.py`, 42 commits | ✅ Maduro |
| Frontend (Vue/Quasar) | ~11.137 LOC, 35 `.vue` + 39 `.ts`, 12 commits | 🔶 Avanzado pero parcial |
| App móvil nativa/PWA | 0 LOC (sin `src-pwa`/`src-capacitor`/`src-cordova`/`src-electron`) | ❌ No iniciada |

El frontend tiene 25 páginas reales, 8 stores Pinia, 11 services, 6 suites de tests y un UI kit propio.

Páginas con peso real: `HrEmployeesPage.vue` (1031), `BillingDocumentsPage.vue` (753),
`PosTerminalPage.vue` (660, con cola offline), `AuditBitacoraPage.vue` (552),
`AuditEventsPage.vue` (438), `HrPositionsPage.vue`, `OrgBranchesPage.vue`, `OrgCompaniesPage.vue` (300+).

---

## 2. Arquitectura del frontend

Stack: Vue 3.5 + Quasar 2.16 + Pinia 3 + vue-router 4 + Vite + TypeScript estricto + Vitest.

Arquitectura por capas (Feature-Sliced) declarada en `frontend/src/ARCHITECTURE_SPA_MODULAR.md`:

```
app → pages → widgets → features → entities → shared
```

Incoherencia principal: la arquitectura está **declarada pero apenas implementada**. Solo
**un dominio** sigue el patrón completo:

- `pages/HrEmployeesPage.vue` (contenedor)
- `features/hr/employees/useHrEmployeesFeature.ts` (orquestación)
- `widgets/hr/HrEmployeesTableWidget.vue` (render)

El resto de páginas son monolíticas. `entities/`, `features/`, `widgets/` están casi vacías (solo READMEs).

Bien resuelto:

- Autenticación JWT + 2FA + cambio forzado de contraseña.
- Contexto multi-empresa (`X-Company-Id`/`X-Branch-Id`) por headers.
- Guardas de ruta por permiso ACL + módulos habilitados (`routes.ts`).
- Bootstrap de sesión unificado (`stores/session-bootstrap.store.ts`) contra `/auth/bootstrap/session/`.
- Contrato de errores HTTP normalizado (`shared/http/api-error.ts`).
- Rutas canónicas en español con alias legacy.

---

## 3. La "App" móvil: qué es y qué no es

### Documentación (extensa)
~25 documentos en `docs/operacion/` describen una estrategia **dual-shell**:
`Workbench` (escritorio denso/analítico) y `Taskflow` (móvil, cola de tareas, flujos 3-5 pasos),
con diseños funcionales para inventario, facturación, estación de servicio, reporting, idempotencia, etc.

### Implementación real (3 cosas)
1. Detección de dispositivo en `session-bootstrap.store.ts` (sugiere `device_class`; el backend
   decide `shell_mode`).
2. Un badge "Taskflow móvil" vs "Workbench desktop" (`MainLayout.vue`).
3. Ocultar secciones de menú cuando `isMobileShell` (oculta Organización, RR.HH., Auditoría, Analytics).

No existe:
- App nativa (sin Capacitor/Cordova).
- PWA (`pwa: false` en `quasar.config.ts`; sin service worker, manifest, instalable, push).
- Flujos guiados / cola de tareas `Taskflow`.
- Layout móvil propio (es el mismo `MainLayout` con drawer recortado).

En la práctica: **"móvil" = la web de escritorio con menos opciones en el menú** — el anti-patrón
"desktop comprimido" que la propia norma prohíbe.

Nota: `services/retail-pos-offline-queue.ts` es una cola de la SPA, no offline real de PWA.
La arquitectura lo admite: "online-first + retry. Sin offline amplio".

---

## 4. Gaps críticos

| # | Gap | Impacto |
|---|---|---|
| 1 | No hay app empaquetable (PWA/nativa) | "App" es un nombre, no un artefacto instalable |
| 2 | `Taskflow` no implementado más allá de badge/menú | La UX móvil prometida no existe |
| 3 | Sin layout móvil dedicado | UX móvil hereda densidad de escritorio |
| 4 | Arquitectura modular a medias (solo HR) | Deuda: patrón "oficial" incumplido en 24 páginas |
| 5 | Brecha doc↔código enorme | Riesgo de "documentation theater" |
| 6 | `router mode: 'hash'` | URLs con `#`; peor deep-link/SEO/compartir |

---

## 5. Riesgos transversales

- Desbalance backend/frontend ~7.5:1 en LOC: hay capacidad de negocio sin interfaz.
- Verificación pendiente: `node_modules` no instalado → no se pudo correr lint/typecheck/build/test
  para certificar que el frontend compila hoy (gate de build de producción exigido por la arquitectura).
- Riesgo de "diseño sobre implementación": documentación normativa muy superior al código que la respalda.

---

## 6. Recomendaciones priorizadas

Inmediato:
1. `cd frontend && npm install && npm run typecheck && npm run lint && npm run test && npm run build`.
2. Actualizar README (desactualizado respecto a billing/POS/sync ya implementados).

Corto plazo:
3. Decidir qué es "la app": PWA instalable vs. solo web responsiva (decisión de producto).
4. Si PWA: activar `pwa: true`, generar `src-pwa`, manifest, service worker, iconos.
5. Implementar de verdad `Taskflow`: `MobileLayout.vue` con cola de tareas y flujos por pasos.

Medio plazo:
6. Terminar la migración modular (replicar patrón HR) o bajar la ambición del documento de arquitectura.
7. Construir UI de los módulos backend sin frontend (inventario, estación de servicio completa).

---

Generado como parte del análisis de la rama `claude/frontend-app-analysis-3kYAB`. Sin cambios de código.
