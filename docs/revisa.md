# Context Card (canonical)

## 1) Project identity

* **Project name:** Necktral/Necktral
* **Mission:** ERP/CRM modular con backend Django/DRF, frontend Quasar y módulos de dominio desacoplados
* **Primary success metrics:** CI verde, contratos estables de API, reportes reproducibles, dashboard usable, ramas gobernadas
* **Current phase:** build / stabilize

## 2) Scope

### In-scope

* módulo de reportes contables
* lineamientos para dashboard
* orden de ramas y gobierno del repo
* reorganización hacia `backend/src/apps/modulos/*`

### Out-of-scope

* reescritura completa del backend
* cambio total de dominio contable
* migración masiva de carpetas en un solo paso

## 3) Constraints and non-negotiables

* **Quality bar:** no mezclar reporting formal con dashboard ejecutivo
* **Tooling/platform:** Django/DRF backend, frontend Quasar/Vue, GitHub Actions
* **Non-negotiable:** una sola rama troncal real, branch protection, CI como gate
* **Current repo reality:** hoy el repo sigue dividido entre `login_module/` como backend, `frontend/` como consola web y `modulos/` en raíz 

## 4) Current state

* El backend contable ya expone endpoints reales para:

  * `reports/trial-balance/`
  * `reports/general-ledger/`
  * `reports/pnl/`
  * `reports/balance-sheet/`
  * `reports/operational-reconciliation/`
  * consolidación contable 
* `views.py` concentra demasiadas responsabilidades: reportes, FX, intercompany, consolidación, periodos, journal drafts y reversals, todo en un solo módulo HTTP/orquestación 
* Ya existe export batch/CLI vía `export_gl_report.py`, con JSON/CSV para `trial_balance`, `general_ledger`, `pnl` y `balance_sheet` 
* El diagnóstico del repo describe backend maduro, frontend real pero con testing débil, y observa falta de branch protection y mezcla de ramas `master`, `feat/*`, `copilot/*`, `codex/*` 
* El roadmap técnico del repo prioriza seguridad, integridad, operación y reportes reproducibles, con CI determinista como principio de decisión 

## 5) Open questions

* ¿Vas a conservar `login_module/` durante transición o vas a abrir ya el namespace `backend/`?
* ¿La rama troncal definitiva será `master` o harás migración formal a `main`?

## 6) Next milestone

* **Milestone:** estabilizar reportes + abrir dashboard API + ordenar ramas
* **Definition of done:**

  * reportes desacoplados de `views.py`
  * dashboard con endpoints propios
  * branch strategy escrita y aplicada
  * PR rules y checks bloqueantes activos

---

# Decision Log Update

* **2026-03-19 — Decisión:** no rehacer reportes desde cero.
  **Razón:** ya existe base funcional suficiente: rutas, RBAC, paginación, export y reportes contables formales   

* **2026-03-19 — Decisión:** separar formalmente `reporting` de `dashboard`.
  **Razón:** hoy el módulo contable sirve bien como fuente formal, pero no como contrato frontend-first; además `views.py` ya está sobrecargado 

* **2026-03-19 — Decisión:** ordenar ramas antes de crecer más en features.
  **Razón:** el repo ya muestra mezcla de troncal, feature, análisis AI y release; el diagnóstico además marca falta de branch protection y CI inconsistente 

---

# Backlog Update

| Priority | Item                                                                 | Type         | Owner    | Effort | Risk | Dependency | Definition of done                            |
| -------: | -------------------------------------------------------------------- | ------------ | -------- | ------ | ---- | ---------- | --------------------------------------------- |
|        1 | Definir una sola rama troncal (`master` o `main`)                    | ops          | tú       | S      | H    | ninguna    | queda una sola rama protegida como trunk      |
|        2 | Crear `docs/engineering/branching_strategy.md`                       | docs         | tú       | S      | M    | item 1     | estrategia escrita, versionada y aplicada     |
|        3 | Extraer reportes de `views.py` a `reports/` + `api/views_reports.py` | refactor     | backend  | M      | H    | item 1     | `views.py` deja de concentrar lógica contable |
|        4 | Crear `api/views_dashboard.py` con endpoints dashboard               | feat         | backend  | M      | M    | item 3     | dashboard API separada y versionable          |
|        5 | Homogeneizar envelope de respuestas de reportes                      | fix          | backend  | M      | M    | item 3     | `meta/summary/results/pagination` consistente |
|        6 | Crear `frontend/src/modules/accounting/dashboard/`                   | feat         | frontend | M      | M    | item 4     | dashboard UI separado de páginas de reporte   |
|        7 | Agregar tests de contrato para reportes y dashboard API              | test         | backend  | M      | H    | items 3-5  | shape estable y CI bloqueante                 |
|        8 | Agregar CODEOWNERS + PR template + labels                            | ops          | tú       | S      | M    | item 1     | gobierno mínimo GitHub operativo              |
|        9 | Definir ADR de reorganización backend                                | docs         | tú       | S      | M    | item 3     | ruta de migración clara sin big bang          |
|       10 | Planificar transición `login_module/` -> `backend/`                  | research     | tú       | M      | H    | items 3,9  | plan por fases, sin romper imports            |
|       11 | Añadir caching selectivo para dashboard                              | feat         | backend  | M      | M    | item 4     | KPIs rápidos sin cachear GL fino              |
|       12 | Separar reportes formales vs monitoreo técnico                       | architecture | tú       | S      | M    | item 4     | no se mezcla dashboard negocio con Grafana    |

## Icebox

* migración completa de todos los módulos root `modulos/` al nuevo layout
* internacionalización frontend
* snapshot persistente de reportes ejecutivos
* jobs programados de agregación mensual

---

# Orientación técnica para reportes

## Dictamen

El módulo de reportes **sí está bien para continuar**, pero no está bien **para seguir creciendo dentro de `views.py`**.

## Lo correcto ahora

Extraer esta estructura lógica:

```text
backend/src/apps/modulos/accounting/
  api/
    urls.py
    views_reports.py
    views_dashboard.py
    serializers_reports.py
    serializers_dashboard.py
  reports/
    selectors.py
    services.py
    presenters.py
    exporters.py
    contracts.py
  dashboard/
    selectors.py
    services.py
    presenters.py
    cache_keys.py
  domain/
    models.py
    policies.py
```

Mientras no migres a `backend/`, replica eso dentro de:

```text
login_module/src/apps/accounting/
```

## Qué sacar de `views.py`

Saca primero:

* construcción de payloads
* normalización de filtros
* agregaciones de PnL / balance / reconciliation
* presentadores de salida
* export formatting

Deja en views solo:

* auth / permisos
* parseo HTTP
* invocación de caso de uso
* status code / envelope

## Mejora crítica

Hoy las respuestas no están totalmente uniformadas: algunos endpoints devuelven `count/limit/offset/results`, otros payload directo con `filters` + `report`, otros consolidación con `run_id` + `summary` .
Eso no bloquea, pero sí genera deuda para dashboard.

## Envelope recomendado

```json
{
  "meta": {
    "report_type": "trial_balance",
    "company_id": 1,
    "branch_id": 2,
    "currency": "NIO",
    "generated_at": "2026-03-19T00:00:00Z",
    "contract_version": "v1"
  },
  "summary": {},
  "results": [],
  "pagination": {
    "count": 0,
    "limit": 50,
    "offset": 0
  }
}
```

## Mejoras P0 en reportes

* crear `present_trial_balance`
* crear `present_general_ledger`
* crear `present_pnl`
* crear `present_balance_sheet`
* crear `present_operational_reconciliation`
* centralizar export en `reports/exporters.py`
* tests snapshot de payload
* tests de permisos RBAC
* tests de consistencia totals vs rows

---

# Orientación exacta para dashboard

## Regla

**Dashboard no debe consumir directamente reportes contables crudos como contrato principal.**

## Crea estos endpoints

```text
/api/accounting/dashboard/executive-summary/
/api/accounting/dashboard/revenue-vs-expense/
/api/accounting/dashboard/cash-position/
/api/accounting/dashboard/reconciliation-health/
/api/accounting/dashboard/branch-performance/
/api/accounting/dashboard/monthly-trends/
```

## Qué debe mostrar dashboard

### Executive summary

* ingresos
* gastos
* utilidad neta
* cash position
* periodos abiertos
* alertas de conciliación
* variación vs periodo anterior

### Reconciliation health

* conciliadas
* pendientes
* disputadas
* mismatch total
* aging buckets

### Branch performance

* ventas por sucursal
* margen por sucursal
* desviaciones
* ranking

## Dónde guardar frontend

```text
frontend/src/modules/accounting/dashboard/
  pages/
  components/
  services/
  stores/
  types/
```

## Separación UX

* **Dashboard:** KPI, tendencias, semáforos, resumen ejecutivo
* **Reportes:** detalle formal, export, auditoría, drill-down

No mezclar ambas cosas en una sola pantalla.

---

# Orientación para ramas y orden en GitHub

## Estado actual

En el inventario live de ramas vi mezcla de:

* `main`
* `master`
* `release/...`
* `feat/...`
* `docs/...`
* `copilot/...`
* `codex/...`

Eso es operable, pero no limpio.

## Modelo recomendado

```text
master                 -> troncal estable actual
release/*              -> preparación de release
feat/*                 -> nuevas funcionalidades
fix/*                  -> correcciones normales
hotfix/*               -> incidentes urgentes
docs/*                 -> documentación
chore/*                -> mantenimiento
spike/*                -> exploración corta
```

## Regla dura

Las ramas:

* `copilot/*`
* `codex/*`

deben ser **efímeras**, no persistentes.
Si algo sirve, se reempaqueta en:

* `feat/*`
* `fix/*`
* `docs/*`

y luego se elimina la rama AI.

## Branch names para este trabajo

* `feat/accounting-reporting-refactor`
* `feat/accounting-dashboard-api`
* `feat/accounting-dashboard-ui`
* `docs/reporting-dashboard-architecture`
* `chore/repo-branch-governance`

## GitHub governance mínimo

Guardar y activar:

```text
.github/CODEOWNERS
.github/pull_request_template.md
.github/ISSUE_TEMPLATE/
docs/engineering/branching_strategy.md
docs/adr/ADR-00X-reporting-vs-dashboard.md
docs/adr/ADR-00Y-branching-model.md
docs/adr/ADR-00Z-backend-module-layout.md
```

## Branch protection

Aplica a la troncal:

* PR obligatorio
* 1 o 2 reviews mínimos
* checks obligatorios
* branch up to date
* sin force push
* squash merge o rebase merge consistente

El diagnóstico del repo ya marca que hoy no se detecta branch protection fuerte y que hubo CI inestable en `master` .

---

# Dónde guardar cada cosa en GitHub

## Backend contable

Hoy:

```text
login_module/src/apps/accounting/
```

Meta objetivo:

```text
backend/src/apps/modulos/accounting/
```

## Frontend dashboard

```text
frontend/src/modules/accounting/dashboard/
```

## Dashboard técnico / monitoreo

```text
simulacion/dashboards/
```

## Documentación de arquitectura

```text
docs/engineering/branching_strategy.md
docs/engineering/backend_module_reorg.md
docs/arquitectura/reporting_dashboard_architecture.md
docs/adr/
```

---

# Juicio técnico final

No estás en un punto para “reinventar reportes”.
Estás en un punto para:

1. **desacoplar reportes de `views.py`**,
2. **abrir dashboard API como capa separada**,
3. **gobernar ramas y PRs**,
4. **migrar a `backend/src/apps/modulos/*` por fases, no por big bang**.

La base existe y es suficiente: el repo ya tiene backend maduro, frontend real, módulo contable funcional y export CLI    .
El cuello de botella real ahora es **estructura y gobierno**, no ausencia de capacidad.

Siguiente movimiento recomendado: arrancar por `feat/accounting-reporting-refactor` y tocar primero `views.py`, `urls.py` y el nuevo paquete `reports/`.
