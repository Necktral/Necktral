# Verificación “Retail POS v1 avanzado” y hardening QA CI en Necktral/Necktral

## Alcance y estado real en el repo

La evidencia disponible apunta a que el trabajo descrito **sí existe implementado** en la **rama de la PR #16** (head SHA **274b0cceb950d8d521bcf819f70cae159b577e68**), pero **todavía no está aplicado en `master`**, porque la PR está **abierta** y aparece **no mergeada** (state=`open`, merged=`false`). fileciteturn2file0L1-L1

En esa misma PR se reporta un volumen de cambio alto (**741 archivos cambiados**, **40 commits**, ~**48,982** adiciones / **7,085** borrados), lo que confirma que no es literalmente un “commit único” aunque el head commit sea ese SHA. fileciteturn2file0L1-L1

## Retail POS v1 avanzado en backend

### Módulo vertical `ventas_retail` creado y registrado

El módulo **existe como app completa** bajo `backend/src/apps/modulos/ventas_retail` y está registrado en `INSTALLED_APPS` como `apps.modulos.ventas_retail.apps.VentasRetailConfig`, lo cual es condición necesaria para que corran migraciones y admin. fileciteturn50file0L1-L1 fileciteturn4file0L1-L1

Además, el backend expone URLs del módulo **en el namespace canónico** `api/backend/retail/` y también un alias legacy `api/retail/`, lo que confirma el “wiring” de exposición. fileciteturn35file0L1-L1

### Modelos, migraciones y administración

La capa de datos está implementada con modelos como `RetailTicket`, `RetailSale`, `RetailReturn`, `RetailBranchConfig`, etc., incluyendo campos de control operacional (versionado, estados de pago, “holds”, compensación, idempotencia) y **referencias explícitas a kernels** (por ejemplo `kernels.facturacion.models.BillingDocument` y `kernels.inventarios.models.InventoryItem/Warehouse`). fileciteturn12file0L1-L1

Existe migración inicial `0001_initial.py` (generada en fecha 2026-03-23) con dependencias a facturación, IAM, inventarios y payments, que valida que el módulo está “aterrizado” en base de datos. fileciteturn16file0L1-L1

En `admin.py` se registran los modelos principales para inspección/operación desde Django Admin. fileciteturn53file0L1-L1

### Servicios y patrón de “consumir kernels”

El módulo implementa un **servicio de dominio** con lógica de POS: abrir ticket, agregar/quitar líneas, preview de checkout, commit, void, devoluciones, compensaciones y reintentos. fileciteturn51file0L1-L1

Lo importante a nivel de arquitectura (y alineado con tu decisión de “FUEL no es kernel, consume kernels”) es que `ventas_retail` **consume kernels** de forma directa y explícita:

- Facturación: usa `kernels.facturacion.services.create_draft`, `issue_doc`, `void_doc` y entidades como `BillingDocument`/`DocType`. fileciteturn51file0L1-L1  
- Inventarios: usa `kernels.inventarios.services.post_issue`, `post_receive` y entidades como `InventoryItem`, `StockMovement`, `Warehouse`. fileciteturn51file0L1-L1  
- Payments/Cash: crea/captura/refunde intentos y registra movimientos de caja vía servicios de `apps.modulos.payments`. fileciteturn51file0L1-L1

También hay un enfoque robusto de **idempotencia** y anticorrupción operacional usando `RetailCommandExecution` con `request_hash`, control de “replay”, conflictos 409 y estados “in progress”. fileciteturn51file0L1-L1

Finalmente, existe el **comando de compensación** `run_retail_compensation_cycle`, que ejecuta el ciclo de recovery y devuelve un payload JSON con métricas del ciclo. fileciteturn15file0L1-L1

### Serializers, vistas, URLs y RBAC

Hay serializers DRF dedicados (inputs de create ticket, line mutations, hold, checkout preview/commit, void, return, retry compensation). fileciteturn52file0L1-L1

Las URLs del módulo exponen endpoints de salud, bootstrap, búsqueda de catálogo, tickets (CRUD parcial y recientes), holds, checkout preview/commit, void, returns y retry de compensación. fileciteturn13file0L1-L1

Las vistas declaran permisos RBAC como `retail.pos.use`, `retail.catalog.read`, `retail.ticket.checkout`, `retail.ticket.void`, `retail.return.create`, etc., mostrando que Retail está gobernado por ACL y no por simple autenticación. fileciteturn14file0L1-L1

## POS Retail en frontend y wiring de navegación

### Ruta, labels y menú

En el router se incorpora la ruta `UI_ROUTE_PATHS.retailPos` y se carga la página `src/modules/retail/pos/pages/RetailPosPage.vue` con permiso requerido `retail.pos.use`. fileciteturn23file0L1-L1

En términos de UI/UX de “exponer Retail”, el label de negocio `retail` está definido como **“Ventas”**, y la ruta canónica se define como `'/ventas'` (con legacy `'/retail'`). fileciteturn36file0L1-L1

En el layout principal se agrega el bloque de navegación “Ventas” y el ítem “POS retail”, condicionado por permisos (`canRetailUse`) y con shortcut Alt+7 a `/ventas`. fileciteturn49file0L1-L1

### Página POS, experiencia táctica/teclado y flujo operativo

La página `RetailPosPage.vue` implementa el “POS operativo” con layout en dos paneles (catálogo + ticket/totales) y acciones típicas: tickets recientes, nuevo ticket, checkout y devolución por línea. fileciteturn24file0L1-L1

Se ve explícitamente la postura “Retail sobre kernels” en el subtítulo del header: **Billing + Inventory + Payments/Cash**. fileciteturn24file0L1-L1

También se implementa bloqueo operativo por caja: si no hay `CashSession OPEN`, Retail avisa que no se puede vender. fileciteturn24file0L1-L1

### Servicios, stores y tests de shortcuts/checkout

El módulo tiene un cliente API con tipado fuerte y mapeo de errores (`RetailApiError`) y endpoints hacia `/backend/retail/...` (bootstrap, catálogo, tickets, checkout preview/commit, void, returns). fileciteturn33file0L1-L1

El store de checkout (`useRetailCheckoutStore`) implementa idempotency keys con prefijos (`retail-checkout`, `retail-void`, `retail-return`), mapea errores 409 operativamente (ej. conflicto de versión), y mantiene estado `preview/lastCommit/lastReturn`. fileciteturn34file0L1-L1

Los atajos de teclado están definidos en el composable `useRetailShortcuts` (F2, F4, F6, F8, Ctrl+Backspace, +/-, Enter, Escape). fileciteturn25file0L1-L1  
Y **sí existen tests**:  
- Test directo del mapeo de shortcuts (`useRetailShortcuts.spec.ts`). fileciteturn47file0L1-L1  
- Test del store de checkout validando idempotency prefix y el mensaje ante `TICKET_VERSION_CONFLICT` (409). fileciteturn48file0L1-L1

## Hardening QA CI Gates 1–3 y bundle budget sin relajar umbrales

### Workflow en jobs separados y artefactos

El workflow `QA CI (Gates 1–3)` está dividido en jobs: `preflight`, `frontend-budget`, `backend-tests`, `audit-integrity`, con `upload-artifact` por job y publicación a `GITHUB_STEP_SUMMARY`. fileciteturn37file0L1-L1

### Runner granular + manifest extendido

El runner `qa/run_qa_ci.sh` está reestructurado en pasos granulares (`setup`, `preflight`, `frontend_quality`, `frontend_bundle_budget`, `gate2_tests`, `gate2_coverage`, `gate2_reports_contracts`, `gate3_audit`), registra duración por step, y captura `failed_gate`/`failed_step`. fileciteturn39file0L1-L1

El `emit_run_manifest.py` genera `run_manifest.json` incluyendo: `run_status`, `failed_gate`, `failed_step`, `gates`, `steps` (lista), `step_statuses` (map), `durations` (map) y `artifacts` con freshness/mtime. fileciteturn40file0L1-L1

En Makefile se agregan targets explícitos para separar calidad frontend y bundle budget (`qa-frontend-quality`, `qa-frontend-bundle-budget`), y se mantiene `qa-ci-fresh` para DB limpia. fileciteturn38file0L1-L1

### Bundle budget hard-fail y optimización real del payload

El script `check-dashboard-v3-bundle-budget.mjs` define umbrales de **700KB** para el route chunk y **500KB** para chunks de analytics, genera reportes `frontend_bundle_budget.json/.md` y hace `process.exit(1)` si falla (hard-fail real, sin relajar budgets). fileciteturn45file0L1-L1

En el análisis documentado de Dashboard v3 se describe el problema (importaciones estáticas de ECharts y AG Grid forzando un chunk enorme) y el resultado final post-optimización:  
- `analytics-aggrid-*.js` **488.13 KB** vs budget 500 KB PASS  
- `dashboard-v3-route-*.js` **280.36 KB** vs budget 700 KB PASS fileciteturn43file0L1-L1

En el componente `DataGridPanel.vue` se ve que se reduce el footprint al registrar módulos mínimos (`ClientSideRowModelModule`) y usar CSS “no font”, ayudando a que el chunk sea más controlable. fileciteturn44file0L1-L1

Además, `frontend/package.json` incluye el script `bundle:budget:dashboard-v3` apuntando al checker, lo cual cierra el loop para CI. fileciteturn46file0L1-L1

## Observaciones críticas y oportunidades de mejora

### Riesgos/ajustes recomendados en la entrega (por tamaño y gobernanza)

El tamaño de la PR (741 archivos / 40 commits) eleva el riesgo de revisión, regresiones y conflictos en merge. fileciteturn2file0L1-L1  
Oportunidad concreta: **partir el delivery en PRs apiladas** (stacked) o al menos “merge plan” con checkpoints: (1) CI hardening, (2) optimización bundle + budgets, (3) Retail backend, (4) Retail frontend. Con esto, cada PR tiene blast radius pequeño y reviews más confiables.

### Consolidación conceptual: “kernels para ser consumidos”

El diseño actual ya materializa tu intención: `ventas_retail` **no es kernel**, sino un módulo vertical que **consume kernels** (`facturacion`, `inventarios`) y módulos (`payments`) con una capa de dominio propia (idempotencia, compensación, estados retail). fileciteturn51file0L1-L1 fileciteturn12file0L1-L1

Si quieres llevar esto a un nivel todavía más “enterprise” sin reescribir, la mejora típica es introducir una capa de **puertos/adaptadores** (interfaces internas) para que Retail no dependa directamente de implementaciones de kernels, sino de contratos (ej. `BillingPort`, `InventoryPort`, `CashPort`). Eso no es “mínimo”, pero sí reduce acoplamiento y permite swap de implementación (por ejemplo, cuando la parte fiscal cambie de NOOP a proveedor real).

### Mejoras de producto POS (Retail v1 → v1.1 “de batalla”)

Con lo implementado, ya hay una base sólida (tickets, holds, checkout, devolución, RBAC, atajos). fileciteturn24file0L1-L1 fileciteturn14file0L1-L1  
Las oportunidades que más impacto generan en retail real (sin inflar arquitectura) son:

Integración de “entrada rápida” para lector/escáner: el backend ya soporta `catalog/search` con `barcode` además de `q`. fileciteturn14file0L1-L1  
En frontend, conviene agregar “barcode focus mode” que capture un stream de teclado (escáner emula teclado) y auto-ejecute búsqueda/selección.

Estrategia offline/latencia: el modelo de idempotencia está fuerte (tanto backend con `RetailCommandExecution` como frontend generando idempotency keys). fileciteturn51file0L1-L1 fileciteturn34file0L1-L1  
La mejora natural es un “queue” local (IndexedDB) para reintentar commits si se cae red, evitando dobles cobros gracias a idempotencia.

Cierre fiscal y compliance: hoy se crea factura/nota de crédito con `is_fiscal=False` y con series por sucursal. fileciteturn51file0L1-L1  
Si el objetivo es Nicaragua (y tu PDF sugiere ese foco), el upgrade de nivel empresarial es: definir “modo fiscal” por sucursal (`RetailBranchConfig`) y hacer que BillingDocument mantenga evidencia y estado fiscal consistente en POS (ya hay UI chip `RetailFiscalStatusChip`). fileciteturn24file0L1-L1 fileciteturn12file0L1-L1

### QA CI: siguientes saltos de madurez

El hardening actual ya está bien planteado: jobs separados, runner granular, manifest rico, y budgets hard-fail. fileciteturn37file0L1-L1 fileciteturn40file0L1-L1 fileciteturn45file0L1-L1  
Oportunidades “elite” para el siguiente paso:

- **Política de cache** (npm + docker layers) por job, para bajar tiempos sin degradar determinismo. Esto no cambia lógica, solo ergonomía y costo CI.
- **Path filters**: si solo cambia backend, saltar `frontend-budget`; si solo cambia frontend, evitar levantar DB completa (esto requiere refinar el pipeline y es una decisión con trade-offs).
- **Quality gates por módulo**: dado que `ventas_retail` ya es un vertical, puedes instrumentar un “coverage threshold” por dominio (Retail) igual que ya existen thresholds por dominio en Makefile (`QA_DOMAIN_THRESHOLDS`). fileciteturn38file0L1-L1

## Conclusión verificable

El paquete “Retail POS v1 avanzado + hardening Gates 1–3 + bundle budget hard-fail” **sí está implementado** y se observa en backend (módulo `ventas_retail` completo, wired en Django settings/urls), en frontend (ruta `/ventas`, menú, POS page, servicios/stores, tests), y en CI (workflow por jobs, runner granular, manifest extendido, budget scripts/umbral). fileciteturn35file0L1-L1 fileciteturn23file0L1-L1 fileciteturn37file0L1-L1 fileciteturn45file0L1-L1

Lo único que **no** puede considerarse “aplicado en el proyecto mainline” todavía es el merge a `master`, porque la PR #16 figura **abierta/no mergeada** en este momento. fileciteturn2file0L1-L1