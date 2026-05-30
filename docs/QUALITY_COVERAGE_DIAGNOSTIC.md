# Diagnóstico de cobertura (Gate 2)

Fecha: 2026-02-01

## Resumen ejecutivo

La cobertura total reportada por Gate 2 es **85%**. La caída proviene de dos factores principales:

> **Nota de alcance (anti‑malinterpretación):**
> si el runner **respeta `.coveragerc`**, el reporte queda **filtrado a `src/apps/sync_engine`**
> y el **TOTAL** refleja **solo ese módulo** (no el backend completo).
> Si el runner **no** aplica el rcfile, el TOTAL sí es global.

1. **Cobertura aplicada a módulos fuera del objetivo** (migraciones, admin, urls, views, etc.).
2. **Ramas defensivas no ejercitadas** en `sync_engine` (errores, paths raros, verificación de firma y fallos de persistencia).

Con tests dirigidos y un ajuste mínimo del alcance de cobertura, el objetivo es alcanzar **95%–100%** sin degradar calidad.

---

## Evidencia (Gate 2)

- Total reportado: **85%**.
- Archivos con baja cobertura destacados en el reporte:
  - `src/apps/audit/writer.py` (31%)
  - `src/apps/sync_engine/admin.py` (29%)
  - `apps/modulos/estacion_servicios/migrations/0006_*` (50%)
  - `apps/modulos/estacion_servicios/migrations/0007_*` (35%)
  - `apps/kernels/inventarios/urls.py` (56%)
  - `src/apps/sync_engine/migrations/0001_initial.py` (63%)
  - `src/config/middleware/request_id.py` (58%)

---

## Hallazgos clave

### 1) Alcance de cobertura no está alineado con el objetivo

Existen archivos con **omisión esperada** que están siendo medidos en el reporte (migraciones, admin, urls, views). Esto **reduce artificialmente** el porcentaje total y genera ruido.

**Evidencia:** los patrones de omisión de `.coveragerc` incluyen `*/migrations/*`, `*/admin.py`, `*/urls.py`, `*/views.py`, pero esos archivos aparecen en el reporte.

**Impacto:** la cobertura reportada baja sin reflejar deuda real de tests.

---

### 2) Ramas defensivas en sync_engine sin tests

Las rutas típicas (casos felices) están bien cubiertas, pero hay **poca cobertura en rutas de error** y de integridad:

- Idempotencia con conflicto de `command_id` + payload distinto.
- Firma inválida o payload hash inválido.
- Rechazo por límites (payload size y batch limits).
- Persistencia: errores en `AppliedCommand` y resultados idempotentes.

**Impacto:** baja cobertura real en paths críticos de robustez.

---

## Causas raíz

1. **Desalineación del `rcfile` de coverage**: el reporte incluye archivos que deberían estar omitidos.
2. **Falta de tests para errores/ramas raras** en `sync_engine`.
3. **Módulos auxiliares sin tests intencionalmente** (admin, urls, views), que hoy cuentan contra el % global.

---

## Plan recomendado para llegar a 95%–100%

### A) Corrección de alcance (rápido, sin bajar calidad)

- Forzar uso de `.coveragerc` en el runner de Gate 2.
- Validar que el reporte **no** incluya migraciones/admin/urls/views.

**Resultado esperado:** incremento inmediato del porcentaje reportado sin cambiar lógica.

### B) Tests dirigidos a ramas críticas (alto valor)

Priorizar tests en:

- `sync_engine.services`: idempotencia, payload mismatch, firma inválida, límites de payload, error de persistencia.
- `sync_engine.signing`: inválidos de firma/base64.
- `sync_engine.handlers_inventory`: validaciones por scope y schema inválido.

**Resultado esperado:** cobertura real y robustez operativa.

---

## Riesgos si no se corrige

- El % se mantendrá artificialmente bajo por módulos no críticos.
- Ramas de error críticas seguirán sin testear, afectando resiliencia en producción.

---

## Estado actual

- Gate 2 y Gate 3 pasan.
- Cobertura global actual: **85%**.
- Objetivo solicitado: **95%–100%**.

---

## Siguiente paso recomendado

Autorizar el ajuste de cobertura para aplicar `.coveragerc` correctamente y añadir tests dirigidos en `sync_engine`.
