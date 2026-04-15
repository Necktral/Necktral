# Arquitectura SPA Modular

Objetivo: robustez funcional en frontend con dominios modulares, sin microfrontends, sobre Quasar y Vite.

## Capas y responsabilidades

- `app`: bootstrap, router, providers globales y wiring transversal.
- `shared`: base HTTP, contratos compartidos, utilidades y primitives de interfaz.
- `entities`: tipos de dominio, DTOs y mapeadores API hacia interfaz.
- `features`: casos de uso por dominio, efectos de red y coordinacion con stores.
- `widgets`: composicion de flujos de interfaz sin logica de negocio compleja.
- `pages`: contenedor y orquestacion; delega a `features` y `widgets`.

## Reglas de dependencia

- `pages -> widgets/features/entities/shared`.
- `widgets -> features/entities/shared`.
- `features -> entities/shared`.
- `entities -> shared`.
- `shared` no depende de capas de dominio.

## Politica de nomenclatura visible

- Se usan nombres completos en interfaz:
- `Recursos Humanos`, `Organizacion`, `Control de Acceso`, `Roles y Permisos`, `Identidad y Acceso`, `Combustible`.
- Siglas tecnicas permitidas solo en contexto tecnico:
- `API`, `HTTP`, `CI` y codigos de permisos (`hr.*`, `org.*`, `fuel.*`).

## Navegacion canonica y compatibilidad

- Rutas canonicamente legibles:
- `/recursos-humanos/empleados`
- `/recursos-humanos/puestos`
- `/organizacion/empresas`
- `/organizacion/perfil-empresa`
- `/organizacion/sucursales`
- `/combustible`
- `/combustible/salud`
- Rutas legacy (`/hr/*`, `/org/*`, `/fuel/*`) siguen activas como alias con redireccion interna.

## Sistema visual moderno y simetrico

- Tokens globales de color, tipografia, espaciado, radio y sombras en `src/css/app.scss`.
- Tipografia base no generica: `IBM Plex Sans` para texto y `Manrope` para jerarquia.
- Layout simetrico:
- cabecera de pagina en dos zonas balanceadas (contexto y acciones),
- contenedor centrado con escala uniforme,
- tarjetas y tablas con bordes, alturas y paddings consistentes.
- Animacion sobria:
- entrada de cabecera y tarjetas con `app-fade-up`.

## Contrato de errores HTTP

- Contrato base obligatorio: `ApiErrorEnvelope`.
- Normalizador unico: `src/shared/http/api-error.ts`.
- Legacy `detail` se mantiene como fallback de compatibilidad.

## Cliente API tipado (progresivo)

- Dominio piloto inicial: Recursos Humanos y Organizacion.
- Estrategia: incorporar cliente OpenAPI por dominio y retirar DTOs manuales por lotes.
- Regla: nuevos flujos consumen tipos de `entities` antes de llegar a componentes.

## Piloto modular implementado

- `pages/HrEmployeesPage.vue` funciona como contenedor.
- `features/hr/employees/useHrEmployeesFeature.ts` concentra estado y orquestacion del flujo.
- `widgets/hr/HrEmployeesTableWidget.vue` encapsula rendering y acciones de tabla.
- Resultado: patron replicable para paginas monoliticas del resto de dominios.

## CI frontend obligatorio

- `lint`
- `typecheck`
- `unit/component tests`
- `build` de produccion

La build de produccion se mantiene como gate bloqueante.

## Estrategia dual-shell (desktop y movil)

Regla base:

- Un solo frontend SPA y una sola logica de negocio backend.
- Dos shells de experiencia: `Workbench` (laptop/PC) y `Taskflow` (movil).
- Prohibido convertir movil en "desktop comprimido".

Referencia normativa obligatoria:

- `docs/operacion/CODEX_MASTER_PACK_v1.0.md` (source of truth operativo para ejecucion por slices en Codex: carril publico/privado, bootstrap unificado, dual-shell y secuencia oficial de modulos).
- `docs/operacion/DISENO_EMPRESARIAL_MULTIDISPOSITIVO_ERP_CRM_v1.0.md` (documento maestro enterprise para arquitectura funcional, criterios desktop/movil, seguridad, auditoria, navegacion, riesgos y backlog inicial).
- `docs/operacion/NORMA_GOBERNANZA_MULTIDISPOSITIVO_v1.0.md` (source of truth de reglas de producto, seguridad, trazabilidad y UX por dispositivo).
- `docs/operacion/INVENTARIO_MULTIDISPOSITIVO_v1.0.md` (diseno funcional ejecutable para inventarios Workbench/Taskflow).
- `docs/operacion/FACTURACION_MULTIDISPOSITIVO_v1.0.md` (diseno funcional ejecutable para facturacion internet-first con separacion Workbench/Taskflow).
- `docs/operacion/ESTACION_SERVICIOS_MULTIDISPOSITIVO_v1.0.md` (diseno operativo de estacion de servicios con flujo de apertura, operacion, incidencias y cierre por dispositivo).
- `docs/operacion/REPORTING_DASHBOARDS_MULTIDISPOSITIVO_v1.0.md` (diseno operativo de dashboards/reportes con lectura rapida movil, analisis profundo desktop y contrato de filtros/KPI consistente).
- `docs/operacion/CONTRATOS_FUNCIONALES_COMPARTIDOS_LAPTOP_MOVIL_v1.0.md` (contrato funcional transversal de modulos, acciones, permisos, contexto, contratos de request/trace y eventos auditables cross-device).
- `docs/operacion/BACKLOG_MULTIDISPOSITIVO_INVENTARIO_FACTURACION_ESTACION_REPORTING_DASHBOARD_v1.0.md` (backlog profesional de delivery priorizado por valor/riesgo/dependencias para inventarios, facturacion, estacion, reportes y dashboard).
- `docs/operacion/ARQUITECTURA_IMPLEMENTACION_MULTIDISPOSITIVO_v1.0.md` (propuesta tecnica de implementacion frontend/backend con dual-shell, stores por dominio, capa API y plan incremental no-breaking).
- `docs/operacion/PROMPTS_STACK_REAL.md` (plantilla operativa de prompts alineados al stack real para evitar respuestas genericas en nuevas sesiones).

### Navegacion por dispositivo

- Desktop: navegacion lateral completa, stack/tabs de trabajo y deep links para analisis/auditoria.
- Movil: entrada por cola de tareas, flujo guiado de 3-5 pasos y minimo salto entre modulos en transaccion activa.
- Ambos: validacion obligatoria de sesion, permiso y contexto (`company`, `branch`) antes de ejecutar.

### Densidad de informacion

- Desktop: tablas densas, comparativos, historial y contexto expandido.
- Movil: resumen operativo, estado actual, excepcion relevante y siguiente accion.

### Formularios y acciones

- Desktop: formularios completos, edicion avanzada y operaciones masivas.
- Movil: formularios por pasos, defaults inteligentes y validacion inmediata.
- Confirmaciones: operacion normal con confirmacion simple; operacion critica con step-up auth, confirmacion explicita y motivo.

### Tablas, filtros y busqueda

- Desktop: filtros compuestos, columnas configurables, bulk actions y export.
- Movil: listas resumidas, filtros rapidos predefinidos y busqueda contextual.
- Regla: el backend define semantica de filtros/resultados; la UI define forma de interaccion.

### Matriz canonica `modulo -> permisos minimos -> shell`

Esta matriz se aplica por interseccion: `allowed_modules` (bootstrap) + permiso ACL por ruta/accion.

| Modulo | Permiso minimo de lectura | Shell habilitado |
|---|---|---|
| `dashboard` | contexto valido (sin permiso explicito extra) | `desktop`, `mobile` |
| `organization` | `org.company.read` | `desktop` |
| `human_resources` | `hr.employee.read` | `desktop` |
| `audit` | `audit.read` | `desktop` |
| `fuel` | `fuel.shift.read` | `desktop`, `mobile` |
| `retail_pos` | `retail.pos.ticket.read` | `desktop`, `mobile` |
| `inventory` | `inventory.balance.read` | `desktop`, `mobile` |
| `analytics`/`reporting` | `report.dashboard.read` | `desktop` |
| `synchronization` | `sync.device.enroll` o `sync.device.revoke` | `desktop`, `mobile` |

Reglas:

- `shell_mode` lo define servidor en bootstrap; frontend no compite con una politica paralela.
- La visibilidad de menu no reemplaza autorizacion backend; las rutas siguen protegidas por ACL.
- La activacion de inventarios/facturacion/estacion se agrega en esta matriz al habilitar cada slice funcional.

### Slice 4 Inventarios: acciones canonicas

- `read`: `GET /api/inventory/warehouses/`, `GET /api/inventory/items/`, `GET /api/inventory/balances/`, `GET /api/inventory/movements/`.
- `capture`: payload de movimiento (`type`, `qty`, `unit_cost` cuando aplica, `note`).
- `commit`: `POST /api/inventory/movements/receive/` o `POST /api/inventory/movements/issue/` con `idempotency_key` generado en cliente.
- `adjust` y `transfer`: fuera de alcance funcional del Slice 4 en SPA.

## Contratos tecnicos UX/API (aditivos, no-breaking)

- Metadata de comando:
- `company_id`, `branch_id`, `command_id`, `source_device`, `channel`, `device_class`.
- Trazabilidad de respuesta:
- bloque `trace` con `request_id`, `audit_event_id`, `channel`, `source_device`.
- Errores:
- envelope unico cross-device con codigo, causa y accion sugerida.
- Idempotencia:
- obligatoria para comandos mutables de alta frecuencia en movil.

## Politica de conectividad movil

- En esta fase: base `online-first + retry` con habilitacion offline por modulo.
- Inventarios (Slice 4.1): `capture/commit` offline (`receive/issue`) con cola local + sincronizacion diferida por `/api/sync/batch/`.
- Lectura (`read`) de inventarios se mantiene online-first.
- Reintento seguro con idempotencia y recuperacion de sesion/contexto.
- Estados recuperables obligatorios: sesion expirada, contexto invalido, permiso denegado y timeout/red intermitente.

## Anti-patrones bloqueantes

- Duplicar reglas de negocio en frontend por shell.
- Divergir semantica entre endpoints desktop y movil.
- Basar seguridad solo en ocultar botones.
- Permitir comandos sin contexto explicito.
- Mezclar analitica pesada y comandos transaccionales en un mismo flujo.
- No emitir correlacion `request_id` + auditoria en operaciones criticas.
