# EXECUTION_FRONTS_STRATEGY

## 0. Control del documento

Documento: `EXECUTION_FRONTS_STRATEGY.md`
Proyecto: Necktral ERP/CRM/POS multiempresa
Estado: Estrategia operativa vigente
Ultima actualizacion: 2026-05-30
Uso: definir division de trabajo entre plataformas de ejecucion
Regla superior: este documento complementa el Context Card, el Operating Brief y el Master Roadmap.

## 1. Estrategia de 3 frentes

La ejecucion de Necktral se divide en 3 frentes paralelos con responsabilidades distintas y no solapadas.

```text
┌─────────────────────────────────────────────────────────────────────┐
│                    NECKTRAL - 3 FRENTES DE EJECUCION                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  FRENTE 1: CLOUD (Copilot Coding Agent)                            │
│  ─────────────────────────────────────                             │
│  • Logica de negocio                                               │
│  • Bloques de codigo (kernels, servicios, modelos)                 │
│  • Contratos y APIs backend                                        │
│  • Documentacion tecnica                                           │
│  • CI/CD y configuracion de calidad                                │
│                                                                     │
│  FRENTE 2: LOCAL (Codex)                                           │
│  ─────────────────────────────────────                             │
│  • Tests locales (pytest, PostgreSQL real)                         │
│  • Validacion de persistencia critica                              │
│  • QA Gates con DB real                                            │
│  • Migraciones con rehearsal                                       │
│  • Verificacion de integridad end-to-end                           │
│                                                                     │
│  FRENTE 3: FRONTEND (solo APIs)                                    │
│  ─────────────────────────────────────                             │
│  • Consumo de APIs backend                                         │
│  • Integracion con contratos definidos en Frente 1                 │
│  • Fase posterior — no se ejecuta hasta que Frentes 1 y 2 validen  │
│  • Scope: conectar frontend existente con endpoints certificados   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. Frente 1 — Cloud (Copilot Coding Agent)

Plataforma: GitHub Copilot Coding Agent (sandbox remoto)
Responsable: agente cloud autonomo bajo direccion

### Alcance

- Implementar logica de negocio en kernels y modulos.
- Crear y actualizar bloques de codigo: modelos, servicios, serializers, views, URLs.
- Definir contratos de API (endpoints, permisos, payloads, responses).
- Crear y reparar documentacion tecnica y operativa.
- Configurar CI/CD, coverage, linters y gates de calidad.
- Preparar tests unitarios y de contrato (sin DB real).

### No es responsabilidad del Frente 1

- Ejecutar tests con PostgreSQL real (eso es Frente 2).
- Implementar UI/UX (eso es Frente 3).
- Aprobar persistencia critica sin evidencia de Frente 2.

### Entregables tipicos

- PRs con codigo implementado y documentacion.
- Bloques de logica listos para test.
- Contratos API definidos y documentados.
- Configuracion de gates y thresholds.

## 3. Frente 2 — Local (Codex)

Plataforma: entorno local con Docker, PostgreSQL real y acceso completo
Responsable: Codex operando bajo CODEX_OPERATING_BRIEF

### Alcance

- Ejecutar tests locales (`pytest`, `coverage`, `mypy`, `ruff`).
- Validar persistencia critica con PostgreSQL real.
- Ejecutar QA Gates completos (`make qa-ci-fresh`).
- Probar migraciones con rehearsal en DB efimera.
- Verificar integridad de auditoria, idempotencia y contratos.
- Ejecutar tests end-to-end de backend.

### No es responsabilidad del Frente 2

- Implementar logica nueva desde cero (eso es Frente 1).
- Construir o modificar frontend (eso es Frente 3).
- Definir arquitectura o roadmap (eso es gobernanza).

### Entregables tipicos

- Evidencia de QA passing (reportes en `qa/reports/`).
- Aprobacion de cortes C1 con PostgreSQL real.
- Reporte de regresiones o fallos.
- Feedback tecnico hacia Frente 1 para correccion.

## 4. Frente 3 — Frontend (solo APIs)

Plataforma: frontend existente (Vue 3 + Quasar)
Responsable: fase posterior, dependiente de Frentes 1 y 2

### Alcance

- Conectar el frontend con APIs ya certificadas.
- Consumir endpoints definidos en Frente 1 y validados en Frente 2.
- Solo integracion API — no se implementan flujos UI nuevos sin backend certificado.

### Condiciones de entrada

El Frente 3 solo se activa cuando:

1. El endpoint backend existe y esta documentado (Frente 1).
2. El endpoint pasa tests y coverage en entorno local (Frente 2).
3. El contrato API es estable (no hay cambios breaking pendientes).

### No es responsabilidad del Frente 3

- Crear logica de negocio (eso es Frente 1).
- Validar datos o persistencia (eso es Frente 2).
- Definir nuevos endpoints o modelos.

### Entregables tipicos

- Integracion de paginas con endpoints reales.
- Llamadas API correctas con manejo de errores.
- Tests de frontend contra contratos estables.

## 5. Flujo de trabajo entre frentes

```text
Frente 1 (Cloud)          Frente 2 (Local)          Frente 3 (Frontend)
─────────────────         ─────────────────         ─────────────────────
Implementa logica    →    Ejecuta tests        →    Conecta APIs
Define contratos     →    Valida con PG real   →    Consume endpoints
Crea PRs             →    Aprueba/rechaza      →    Integra UI
Documenta            →    Reporta evidencia    →    (fase posterior)
```

### Regla de dependencia

```text
Frente 1 → Frente 2 → Frente 3
(produce)   (valida)   (consume)
```

No se avanza al siguiente frente sin aprobacion del anterior.

## 6. Clasificacion de tareas por frente

| Tipo de tarea | Frente responsable |
|---------------|-------------------|
| Nuevo modelo/servicio | Frente 1 (Cloud) |
| Nuevo endpoint API | Frente 1 (Cloud) |
| Documentacion tecnica | Frente 1 (Cloud) |
| CI/CD y coverage config | Frente 1 (Cloud) |
| Tests con PostgreSQL real | Frente 2 (Local) |
| QA Gates completos | Frente 2 (Local) |
| Migration rehearsal | Frente 2 (Local) |
| Aprobacion C1 persistencia | Frente 2 (Local) |
| Conectar pagina a API | Frente 3 (Frontend) |
| Consumir endpoint existente | Frente 3 (Frontend) |
| Tests frontend contra API | Frente 3 (Frontend) |

## 7. Gates entre frentes

### Gate 1→2: de Cloud a Local

- Codigo implementado y commiteado.
- Documentacion de contrato API actualizada.
- Tests unitarios incluidos (pueden fallar sin DB real, es esperado).
- PR abierto o branch disponible.

### Gate 2→3: de Local a Frontend

- Tests passing con PostgreSQL real.
- Coverage ≥95% en dominio afectado.
- Contrato API estable (no hay cambios breaking planeados).
- Evidencia de QA en `qa/reports/`.

## 8. Estado actual

- Frente 1 (Cloud): **ACTIVO** — implementando logica y bloques de codigo.
- Frente 2 (Local): **ACTIVO** — ejecutando tests y validacion local.
- Frente 3 (Frontend): **EN ESPERA** — se activa cuando APIs esten certificadas.

## 9. Relacion con documentos rectores

| Documento | Relacion |
|-----------|----------|
| `NECKTRAL_CONTEXT_CARD.md` | Define que construir |
| `NECKTRAL_MASTER_ROADMAP.md` | Define en que orden |
| `CODEX_OPERATING_BRIEF.md` | Define como opera Codex (Frente 2) |
| `COPILOT_CODING_AGENT.md` | Define como opera el agente cloud (Frente 1) |
| `EXECUTION_FRONTS_STRATEGY.md` | Define la division de trabajo entre los 3 frentes |
