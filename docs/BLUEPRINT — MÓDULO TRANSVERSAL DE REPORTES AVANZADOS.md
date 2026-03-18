Lo basé en la constitución actual del repo: jerarquía de verdad y ownerships por kernel/módulo, contratos canónicos entre módulos, invariantes de reproducibilidad y el hecho de que el **motor de reportes formal** sigue siendo backlog explícito, mientras el backend F1–F12 ya está bastante avanzado en staging    

````md
# BLUEPRINT — MÓDULO TRANSVERSAL DE REPORTES AVANZADOS

**Proyecto:** Necktral ERP/CRM  
**Versión:** v1.0  
**Fecha base:** 2026-03-15  
**Estado:** Blueprint técnico propuesto para implementación  
**Audiencia:** Codex, arquitectura, backend, seguridad, QA, operación  

---

# 1. Propósito

Definir el blueprint técnico del **módulo transversal `reportes`** para Necktral, con capacidad de:

- reportar hechos operativos de todos los kernels y módulos core;
- reportar auditoría contractual y evidencia de integridad;
- reportar observabilidad técnica y logs estructurados;
- producir salidas reproducibles e institucionales;
- exportar de forma segura bajo RBAC, scope y auditoría;
- quedar preparado para módulos futuros sin reescritura semántica;
- servir como base oficial para Dashboard, exportaciones, investigación operativa, revisión técnica y control interno.

El módulo **no** debe ser un “Excel endpoint”, ni un conjunto de consultas SQL ad hoc, ni una UI de dashboard encubierta.

---

# 2. Posicionamiento arquitectónico

## 2.1 Naturaleza del módulo

`reportes` **DEBE** implementarse como **módulo transversal institucional**, no como kernel de verdad primaria.

Razón:
- los kernels ya poseen la verdad operativa y financiera;
- CEC actúa como control plane;
- Shadow Ledger es proyección previa al GL formal;
- el motor de reportes debe consumir, congelar, reproducir y exportar, pero **no** apropiarse de ownership de negocio.

## 2.2 Dependencia correcta

La dependencia correcta del sistema debe ser:

```text
Kernels / módulos core / control plane / logs / métricas
            ↓
      apps/reportes
            ↓
Dashboard / exports / auditoría operativa / investigación / BI institucional
````

## 2.3 Regla de oro

`reportes` **DEBE** consumir verdad y derivados gobernados; **NO DEBE** crear una verdad competidora.

---

# 3. Alineación con la constitución vigente del repo

Este blueprint se diseña para respetar las reglas ya vigentes del sistema:

1. **Una sola verdad operativa y una sola verdad financiera final.**
2. **CEC no crea verdad primaria.**
3. **Los contratos entre módulos deben usar envelope canónico, dedupe y replay seguro.**
4. **Los cierres y reportes institucionales deben ser reproducibles.**
5. **Excel y exportes son entregables derivados, nunca fuente primaria.**
6. **Los endpoints deben operar con scope multiempresa/branch y RBAC por método.**
7. **Todo write crítico deja auditoría contractual.**
8. **La etapa actual del backend es aditiva y sin breaking changes.**

---

# 4. Objetivos del módulo

## 4.1 Objetivos funcionales

El módulo debe permitir:

* ejecutar reportes parametrizados por scope, periodo, familia y versión;
* consultar trazabilidad completa por entidad, evento, actor, request o correlación;
* unificar reportes operativos, de control, técnicos e institucionales bajo un API coherente;
* emitir snapshots reproducibles;
* exportar a formatos institucionales con watermarks y huella de auditoría;
* soportar queries de “qué pasó”, “quién lo hizo”, “cuándo cambió”, “qué falló”, “qué quedó bloqueado”, “qué salió del rango”, “qué fue consolidado”, “qué quedó pendiente”;
* servir como backend para Dashboard, pero sin depender de Dashboard.

## 4.2 Objetivos no funcionales

El módulo debe:

* respetar multiempresa y branch scope;
* separar semánticamente verdad operativa, auditoría, observabilidad y reportes certificados;
* ser reproducible cuando la familia del reporte lo requiera;
* ser auditable tanto en lectura como exportación;
* soportar onboarding de módulos futuros por contrato, no por hacks;
* evitar lecturas arbitrarias sobre tablas vivas desde UI.

---

# 5. No objetivos y prohibiciones

## 5.1 No objetivos

El módulo `reportes` **NO** existe para:

* reemplazar kernels;
* postear contabilidad;
* corregir cierres;
* mutar stock;
* reemitir documentos fiscales;
* reemplazar observabilidad/Sentry/monitoreo operativo como sistema fuente;
* reemplazar Dashboard como experiencia visual.

## 5.2 Prohibiciones expresas

`reportes` **MUST NOT**:

1. escribir verdad operativa en Billing, Inventory, Payments o Accounting;
2. renumerar documentos;
3. recalcular GL formal por fuera de Accounting;
4. corregir auditoría contractual;
5. leer tablas ad hoc de módulos futuros sin contrato de entrada;
6. mezclar en la misma definición datos `observability` con `certified_financial` sin etiqueta explícita;
7. permitir exportaciones fuera de scope o sin trazabilidad.

---

# 6. Principio central: cuatro carriles de verdad

El módulo debe implementar cuatro carriles internos, separados en semántica y gobierno.

## 6.1 Carril A — Operational Reporting

Fuente:

* Billing
* Inventory
* Payments/Cash
* verticales operativos
* procurement / retail / services / fuel / futuros

Uso:

* movimientos
* trazabilidad por entidad
* actividad de operación
* estados de negocio
* históricos operativos

Truth level:

* `operational`

## 6.2 Carril B — Audit / Control Reporting

Fuente:

* auditoría contractual
* CEC
* manifests
* excepciones
* evidencia hashada
* acciones administrativas

Uso:

* integridad
* cumplimiento
* investigación interna
* revisiones de control
* exportes regulatorios / internos

Truth level:

* `audit_control`

## 6.3 Carril C — Observability Reporting

Fuente:

* request logs
* error logs
* métricas técnicas
* Sentry
* CSP reports
* sync anomalies
* health / retries
* colas / workers

Uso:

* salud del sistema
* error budgets
* latencias
* seguridad operativa
* debugging institucional

Truth level:

* `observability`

## 6.4 Carril D — Certified Reporting

Fuente:

* Accounting (GL formal)
* Shadow Ledger validado
* CEC packaged close runs
* consolidación / intercompany
* snapshots y manifests certificados

Uso:

* cierres
* conciliaciones
* reportes institucionales
* estados financieros / comparativos internos
* salidas que exigen reproducibilidad fuerte

Truth level:

* `certified_financial`

## 6.5 Regla de mezcla

Un reporte puede combinar carriles **solo** si:

* declara explícitamente sus `source_types`;
* declara `truth_level` dominante;
* versiona su fórmula/definición;
* etiqueta visual y contractualmente qué campos son certificados y cuáles no.

---

# 7. Modelo de fuentes (ingesta por contrato)

Ningún módulo futuro debe integrarse a `reportes` por lectura SQL improvisada.

Toda fuente debe entrar por contrato.

## 7.1 Source types permitidos

```text
DOMAIN_EVENTS
AUDIT_EVENTS
SYSTEM_LOGS
METRICS
SYNC_EVENTS
SECURITY_EVENTS
CERTIFIED_SNAPSHOTS
READ_MODELS
```

## 7.2 Contratos de entrada propuestos

### A. `EventFeedContract`

Para módulos que publican eventos canónicos.

Campos mínimos:

* `feed_code`
* `producer_module`
* `event_types`
* `schema_version`
* `scope_fields`
* `correlation_fields`
* `retention_class`
* `supports_replay`

### B. `AuditFeedContract`

Para auditoría contractual.

Campos mínimos:

* `feed_code`
* `partition_strategy`
* `event_catalog_version`
* `subject_catalog_version`
* `reason_catalog_version`
* `integrity_mode`
* `contains_pii`

### C. `LogFeedContract`

Para logs estructurados y observabilidad.

Campos mínimos:

* `feed_code`
* `logger_name`
* `severity_levels`
* `request_id_support`
* `scope_support`
* `redaction_policy`
* `sampling_policy`

### D. `MetricFeedContract`

Para series o snapshots técnicos.

Campos mínimos:

* `feed_code`
* `metric_name`
* `metric_type`
* `labels`
* `aggregation_window`
* `resolution`
* `retention_policy`

### E. `SnapshotFeedContract`

Para salidas reproducibles o certificadas.

Campos mínimos:

* `feed_code`
* `snapshot_type`
* `producer_module`
* `as_of_policy`
* `manifest_support`
* `hash_support`
* `reproducibility_mode`

---

# 8. Modelo semántico del módulo

## 8.1 Entidades principales

### 8.1.1 `ReportDefinition`

Define qué es un reporte.

Campos propuestos:

* `report_code`
* `report_family`
* `title`
* `description`
* `owner_domain`
* `status`
* `truth_level`
* `source_types`
* `input_contracts`
* `filter_contract`
* `output_schema`
* `freshness_class`
* `reproducibility_mode`
* `export_policy`
* `retention_policy`
* `classification`
* `supports_async_snapshot` *(reservado; no implica background job obligatorio en esta fase)*
* `supports_future_modules`
* `version`
* `deprecated_at`
* `replacement_report_code`

### 8.1.2 `ReportExecution`

Representa una ejecución concreta.

Campos propuestos:

* `execution_id`
* `report_code`
* `report_version`
* `requested_by`
* `requested_at`
* `effective_scope`
* `params_hash`
* `as_of`
* `time_window`
* `source_manifest`
* `output_manifest_hash`
* `status`
* `duration_ms`
* `row_count`
* `warnings`
* `error_envelope`

### 8.1.3 `ReportSnapshot`

Representa el resultado persistido/reproducible cuando aplica.

Campos propuestos:

* `snapshot_id`
* `execution_id`
* `snapshot_type`
* `as_of`
* `scope_hash`
* `formula_version`
* `input_manifest_hash`
* `output_manifest_hash`
* `storage_ref`
* `is_certified`
* `expires_at`

### 8.1.4 `ReportExport`

Representa una exportación institucional.

Campos propuestos:

* `export_id`
* `execution_id`
* `format`
* `template_version`
* `watermark_text`
* `exported_by`
* `exported_at`
* `download_scope`
* `retention_until`
* `audit_event_ref`
* `storage_ref`

### 8.1.5 `ReportReadAudit`

Audita lectura y exportación de información sensible.

Campos propuestos:

* `read_audit_id`
* `actor_user_id`
* `report_code`
* `execution_id`
* `scope`
* `sensitivity_level`
* `reason`
* `request_id`
* `ip_server_seen`
* `user_agent`
* `occurred_at`

### 8.1.6 `SourceRegistry`

Catálogo de fuentes integrables.

Campos propuestos:

* `source_code`
* `source_type`
* `producer_module`
* `contract_version`
* `truth_level`
* `supports_scope`
* `supports_request_id`
* `supports_correlation`
* `supports_replay`
* `pii_policy`
* `retention_policy`
* `status`

### 8.1.7 `DatasetVersion`

Congela una definición de dataset usada por reportes complejos.

Campos propuestos:

* `dataset_code`
* `dataset_version`
* `source_registry_refs`
* `shape_contract`
* `join_contract`
* `privacy_contract`
* `quality_contract`

---

# 9. Familias de reportes

## 9.1 Familia `TRACE`

Trazabilidad detallada por entidad/evento/actor.

Ejemplos:

* historial de documento
* historial de movement
* historial de cash session
* historial por `request_id`
* historial por `correlation_id`

## 9.2 Familia `AUDIT`

Reportes de auditoría contractual y control.

Ejemplos:

* eventos por actor
* cambios críticos por módulo
* integridad de cadena
* exportes realizados
* accesos a reportes sensibles

## 9.3 Familia `OPS`

Reportes operativos y de flujo de negocio.

Ejemplos:

* movimientos por día/sucursal
* ventas emitidas/anuladas
* ajustes de inventario
* cierres de caja
* transferencias

## 9.4 Familia `OBS`

Reportes técnicos/observabilidad.

Ejemplos:

* 401/403/5xx por endpoint
* latencia por endpoint
* errores por módulo
* eventos CSP
* errores sync por reason_code
* colas con retry

## 9.5 Familia `CONTROL`

Reportes de CEC y control de cierre.

Ejemplos:

* exceptions blocking
* manifest mismatches
* gate state transitions
* close runs por estado

## 9.6 Familia `FIN`

Reportes institucionales/certificados.

Ejemplos:

* conciliación operacional-contable
* cierres por periodo
* consolidación intercompany
* reportes financieros internos certificados

## 9.7 Familia `SEC`

Reportes de seguridad operativa.

Ejemplos:

* intentos fallidos de auth
* rotaciones de secretos
* revocaciones de sesión
* hallazgos de seguridad operacional

---

# 10. Clasificación por reproducibilidad

Todo reporte debe declarar uno de estos modos:

## 10.1 `LIVE`

Lee datos actuales y devuelve estado presente.

Uso:

* observabilidad
* activity feeds
* health
* colas

No exige misma salida histórica si las fuentes cambian.

## 10.2 `SNAPSHOT`

Genera un resultado congelado con `as_of` y manifiesto.

Uso:

* cierres
* exportes institucionales
* comparativos

Debe poder repetirse con mismo input.

## 10.3 `CERTIFIED`

Requiere:

* `input_manifest_hash`
* `formula_version`
* `scope`
* control de exportación
* bitácora de acceso

Uso:

* reportes de cierre
* conciliaciones finales
* estados institucionales

---

# 11. Scope, RBAC y seguridad

## 11.1 Scope obligatorio

Todo endpoint de `reportes` debe operar con contexto efectivo:

* `company`
* `branch` si aplica
* lectura intercompany solo bajo grant explícito y solo donde el contrato lo permita

## 11.2 Permisos por método y familia

Propuesta mínima:

* `reports.definition.read`
* `reports.run`
* `reports.snapshot.read`
* `reports.export`
* `reports.audit.read`
* `reports.observability.read`
* `reports.financial.read`
* `reports.admin`

Permisos específicos adicionales por familia/canal:

* `reports.control.read`
* `reports.security.read`
* `reports.trace.read`

## 11.3 Sensibilidad

Cada reporte debe declarar:

* `sensitivity_level = low | medium | high | restricted`
* si contiene PII
* si requiere reason obligatoria al consultarse/exportarse

## 11.4 Watermark y redacción

Exportes sensibles deben soportar:

* watermark con usuario + timestamp + scope + request_id
* redacción selectiva de campos sensibles
* formatos limitados por policy

## 11.5 Auditoría de lectura/exportación

Toda ejecución/exportación de reportes `high` o `restricted` debe generar `ReportReadAudit` y evento contractual equivalente.

---

# 12. Reglas de integridad y calidad

## 12.1 Reglas universales

1. Todo reporte debe declarar `truth_level`.
2. Todo reporte debe declarar `source_types`.
3. Todo reporte debe declarar `scope behavior`.
4. Todo reporte debe declarar `freshness_class`.
5. Todo reporte debe declarar `reproducibility_mode`.
6. Todo reporte debe declarar `owner_domain`.
7. Todo reporte debe declarar `output_schema`.

## 12.2 Reglas de calidad por ejecución

Cada ejecución debe devolver metadatos mínimos:

* `request_id`
* `execution_id`
* `effective_scope`
* `report_version`
* `source_manifest` o indicador de no-aplica
* `freshness`
* `warnings`

## 12.3 Reglas de mezcla entre carriles

No se permite:

* mezclar logs técnicos crudos con balances certificados sin separación;
* mezclar `observability` con `certified_financial` en una tabla plana sin etiquetado;
* mezclar `audit_control` con `operational` sin distinguir fuente.

## 12.4 Regla de trazabilidad

Siempre que exista:

* `request_id`
* `correlation_id`
* `causation_id`
* `subject_id`
* `source_module`

el reporte debe poder exponerlos o filtrarlos, salvo redacción explícita.

---

# 13. Arquitectura lógica interna

## 13.1 Capas internas

### A. `registry`

Gestiona `ReportDefinition`, `SourceRegistry`, `DatasetVersion`.

### B. `ingestion`

Conectores/adaptadores a feeds de dominio, auditoría, logs y métricas.

### C. `normalization`

Convierte entradas heterogéneas a envelopes internos coherentes.

### D. `datasets`

Construye datasets reutilizables y versiones de shape/join.

### E. `execution`

Evalúa filtros, aplica políticas de scope y produce el resultado.

### F. `snapshots`

Persistencia de snapshots/manifests cuando aplica.

### G. `exports`

Renderizado y entrega segura.

### H. `read_audit`

Traza acceso y exportación.

### I. `retention`

Aplica expiración y archivado según policy.

---

# 14. Estructura propuesta de repositorio

Respetando la convención del repo, se propone backend-only en esta fase.

```text
backend/src/apps/reportes/
  __init__.py
  apps.py
  urls.py

  api/
    views.py
    serializers.py
    filters.py
    permissions.py

  registry/
    models.py
    services.py
    validators.py
    selectors.py

  ingestion/
    base.py
    event_feeds.py
    audit_feeds.py
    log_feeds.py
    metric_feeds.py
    snapshot_feeds.py

  normalization/
    contracts.py
    mappers.py
    envelopes.py

  datasets/
    models.py
    builders.py
    joins.py
    quality.py

  execution/
    services.py
    planners.py
    runners.py
    freshness.py
    scope.py

  snapshots/
    models.py
    services.py
    hashing.py

  exports/
    services.py
    renderers.py
    watermark.py
    storage.py

  read_audit/
    models.py
    writer.py

  retention/
    policies.py
    cleanup.py

  management/commands/
    reportes_rebuild_snapshot.py
    reportes_verify_snapshot.py
    reportes_export_manifest.py
    reportes_cleanup_expired.py

  tests/
    test_registry.py
    test_scope.py
    test_execution.py
    test_snapshots.py
    test_exports.py
    test_read_audit.py
    test_observability_reports.py
    test_audit_reports.py
```

Notas:

* Nombres propuestos; Codex puede ajustarlos a la estructura real del repo, pero sin violar ownership ni convenciones.
* `reportes` debe vivir en `apps/` porque es transversal.

---

# 15. API propuesta

## 15.1 Definitions

### `GET /api/reportes/definitions/`

Lista reportes visibles por rol/scope.

Filtros sugeridos:

* `family`
* `truth_level`
* `source_type`
* `sensitivity_level`
* `status`

### `GET /api/reportes/definitions/{report_code}/`

Devuelve definición completa visible al actor.

## 15.2 Ejecutar

### `POST /api/reportes/run/`

Ejecuta un reporte.

Payload sugerido:

```json
{
  "report_code": "AUDIT_EVENTS_BY_SCOPE",
  "params": {
    "since": "2026-03-01T00:00:00Z",
    "until": "2026-03-15T23:59:59Z",
    "branch_id": 2,
    "actor_user_id": 18
  },
  "as_of": null,
  "format": "json"
}
```

Respuesta mínima sugerida:

```json
{
  "execution_id": "...",
  "report_code": "AUDIT_EVENTS_BY_SCOPE",
  "report_version": "1.0.0",
  "truth_level": "audit_control",
  "effective_scope": {"company_id": 1, "branch_id": 2},
  "freshness": {"class": "live", "generated_at": "..."},
  "source_manifest": {...},
  "results": [...],
  "warnings": []
}
```

## 15.3 Snapshots

### `POST /api/reportes/snapshots/`

Genera snapshot para reportes `SNAPSHOT` o `CERTIFIED`.

### `GET /api/reportes/snapshots/{snapshot_id}/`

Consulta metadatos de snapshot.

### `GET /api/reportes/snapshots/{snapshot_id}/content/`

Obtiene el contenido si el rol lo permite.

## 15.4 Exports

### `POST /api/reportes/exports/`

Solicita exportación segura.

Parámetros sugeridos:

* `execution_id`
* `format = csv | xlsx | pdf | jsonl`
* `template_version`
* `reason`

### `GET /api/reportes/exports/{export_id}/`

Consulta estado y metadatos.

## 15.5 Read audit

### `GET /api/reportes/read-audit/`

Solo perfiles autorizados.

## 15.6 Health / registry

### `GET /api/reportes/health/`

Expone salud básica del módulo.

### `GET /api/reportes/sources/`

Lista fuentes registradas visibles al actor.

---

# 16. Envelope de error

El módulo debe respetar el envelope contractual vigente del repo.

Toda respuesta de error debe incluir:

* `code`
* `http_status`
* `message`
* `details`
* `retryable`
* `request_id`
* `timestamp`

Códigos propuestos adicionales del módulo:

* `REPORT_NOT_FOUND`
* `REPORT_FORBIDDEN`
* `REPORT_INVALID_SCOPE`
* `REPORT_INVALID_PARAMS`
* `REPORT_UNSUPPORTED_SOURCE`
* `REPORT_SNAPSHOT_REQUIRED`
* `REPORT_EXPORT_FORBIDDEN`
* `REPORT_REPRODUCIBILITY_VIOLATION`
* `REPORT_DATA_CLASSIFICATION_CONFLICT`

---

# 17. Normalización interna propuesta

Para evitar que cada fuente tenga shape propio hasta UI, el módulo debe normalizar envelopes.

## 17.1 `NormalizedRecord`

Campos propuestos:

* `record_type`
* `source_type`
* `source_module`
* `truth_level`
* `occurred_at`
* `scope`
* `actor`
* `entity_type`
* `entity_id`
* `severity`
* `request_id`
* `correlation_id`
* `causation_id`
* `event_type`
* `reason_code`
* `payload`
* `metadata`

## 17.2 Reglas de normalización

* Nunca perder `request_id` si existe.
* Nunca perder scope si existe.
* Mantener `event_type` original y opcionalmente `normalized_event_class`.
* Redactar PII según policy antes de persistir snapshot/export si aplica.

---

# 18. Integración con módulos existentes

## 18.1 IAM / RBAC / contexto

Uso:

* enforcement de scope
* catálogo de permisos
* reason obligatoria en lecturas sensibles

## 18.2 Audit

Uso:

* reportes de auditoría
* read audit
* export audit
* integridad y severidad

## 18.3 Sync / Event Backbone

Uso:

* trazabilidad de comandos
* errores `SYNC_*`
* actividad por dispositivo
* anomalías/replay

## 18.4 Billing

Uso:

* historial documental
* emisión/anulación
* exportes por estado y actor
* trazabilidad por documento

## 18.5 Inventory

Uso:

* ledger/balances reportables
* movimientos por item/warehouse/branch
* ajustes/transferencias

## 18.6 Payments & Cash

Uso:

* cash sessions
* diferencias
* cobros/capturas/refunds
* conciliación operativa

## 18.7 Accounting

Uso:

* conciliaciones
* close runs relacionados
* reportes certificados
* snapshots financieros

## 18.8 CEC

Uso:

* exceptions
* manifests
* gates
* packaged closures

## 18.9 Seguridad / observabilidad

Uso:

* logs estructurados
* errores/sentry
* CSP/security reports
* métricas de endpoint

---

# 19. Integración con módulos futuros

Todo módulo futuro debe poder integrarse sin tocar el core semántico de `reportes`.

## 19.1 Requisito de onboarding

Cada módulo futuro debe aportar al menos uno de:

* `EventFeedContract`
* `AuditFeedContract`
* `LogFeedContract`
* `MetricFeedContract`
* `SnapshotFeedContract`

## 19.2 Checklist de onboarding

1. declarar `source_code`
2. declarar `source_type`
3. declarar `truth_level`
4. declarar `scope_fields`
5. declarar `retention_policy`
6. declarar `pii_policy`
7. agregar tests de integración
8. agregar documentación

## 19.3 Regla de compatibilidad

Un módulo nuevo **NO DEBE** requerir que `reportes` lea tablas privadas sin contrato.

---

# 20. Reproducibilidad y manifests

## 20.1 Cuándo es obligatoria

Es obligatoria para:

* cierres
* conciliaciones finales
* consolidación
* exportes institucionales sensibles
* reportes declarados `CERTIFIED`

## 20.2 Componentes del manifiesto

Cada ejecución certificada debe incluir:

* `report_code`
* `report_version`
* `formula_version`
* `effective_scope`
* `as_of`
* `time_window`
* `source_manifest_hash`
* `dataset_version`
* `output_manifest_hash`
* `generated_at`
* `generated_by`

## 20.3 Regla de repetición

Mismo:

* `report_code`
* `version`
* `scope`
* `as_of`
* `input_manifest`

=> debe producir mismo `output_manifest_hash`, salvo que el reporte esté declarado `LIVE`.

---

# 21. Exportación segura

## 21.1 Formatos

Propuestos:

* `csv`
* `xlsx`
* `pdf`
* `json`
* `jsonl`

## 21.2 Reglas

* Todo export debe quedar auditado.
* El formato permitido depende de `export_policy`.
* `pdf/xlsx` sensibles deben incorporar watermark.
* `csv/jsonl` pueden estar prohibidos en reportes `restricted`.

## 21.3 Metadatos visibles en export

* usuario
* fecha/hora UTC
* scope
* request_id
* versión del reporte
* clasificación del reporte

---

# 22. Retención y clasificación

## 22.1 Clases de retención sugeridas

* `ephemeral`
* `short_term`
* `operational_archive`
* `compliance_archive`
* `financial_archive`

## 22.2 Regla

La retención se define por `ReportDefinition` y por `SourceRegistry`, y la más estricta gana.

## 22.3 PII

Si una fuente contiene PII:

* debe declararlo;
* debe aplicar redacción/mascarado cuando el rol no lo habilita;
* exportes deben respetar la policy más restrictiva.

---

# 23. Observabilidad interna del propio módulo

`reportes` también debe observarse a sí mismo.

Métricas mínimas sugeridas:

* `reportes_run_total`
* `reportes_run_error_total`
* `reportes_export_total`
* `reportes_export_forbidden_total`
* `reportes_snapshot_total`
* `reportes_execution_p95_ms`
* `reportes_read_audit_total`
* `reportes_data_classification_conflicts_total`

Logs mínimos:

* inicio/fin de ejecución
* source resolution
* warning de mezcla de truth levels
* export policy denials
* reproducibility violations

---

# 24. QA y gates

## 24.1 Gates mínimos de integración

El módulo solo se considera integrado cuando:

1. aplica scope y RBAC;
2. audita lecturas/exportes sensibles;
3. respeta envelope de error;
4. tiene tests de reproducibilidad donde aplica;
5. tiene tests de clasificación por `truth_level`;
6. tiene tests de export policy;
7. tiene tests de mezcla prohibida;
8. no introduce breaking changes a contratos existentes.

## 24.2 Test suite mínima

* unit: definiciones, validadores, clasificación, policy
* integration: ejecución por familia, scope, permisos
* contract: feeds, error envelope, exportes, snapshots
* regression: reproducibilidad, manifests, redacción PII
* perf básica: listados paginados, filtros y exportes razonables

---

# 25. Estrategia de implementación por fases

## Fase 1 — Constitución del módulo

Implementar:

* `SourceRegistry`
* `ReportDefinition`
* `ReportExecution`
* `ReportExport`
* `ReportReadAudit`
* API base `/definitions`, `/run`, `/exports`

Cobertura inicial:

* una familia `AUDIT`
* una familia `OBS`
* una familia `TRACE`

## Fase 2 — Integración con auditoría y observabilidad

Integrar:

* auditoría contractual
* request logs
* métricas básicas
* errores y security/CSP reports

Objetivo:

* entregar valor inmediato sin depender de Dashboard

## Fase 3 — Trazabilidad operativa

Integrar:

* Billing
* Inventory
* Payments/Cash
* Sync

Objetivo:

* reportes por entidad, request, actor, correlación

## Fase 4 — Reportes institucionales reproducibles

Integrar:

* Accounting
* CEC
* snapshots/manifests
* exportación segura certificada

## Fase 5 — Onboarding de módulos futuros

Crear:

* plantilla de `FeedContract`
* documentación de onboarding
* tests de compatibilidad para nuevos módulos

---

# 26. PR slicing sugerido para Codex

## PR-01

Scaffold `apps/reportes` + registry + definitions.

## PR-02

Execution core + error envelope + scope + permissions.

## PR-03

Read audit + export policy base.

## PR-04

Audit reporting family v1.

## PR-05

Observability reporting family v1.

## PR-06

Trace reporting family v1 (Billing/Inventory/Sync).

## PR-07

Snapshots/manifests v1.

## PR-08

Certified reports v1 (Accounting/CEC).

## PR-09

Onboarding contracts for future modules.

---

# 27. Riesgos principales

1. Construir `reportes` como mezcla caótica de queries por módulo.
2. No separar carriles semánticos.
3. Exportar sin auditar lectura.
4. Mezclar datos `LIVE` con `CERTIFIED` sin etiqueta.
5. Permitir acceso cross-company por defecto.
6. Tratar logs técnicos como hechos financieros.
7. Acoplar el módulo a Dashboard.
8. Permitir módulos futuros sin contrato de fuente.

---

# 28. Decisiones a congelar antes de codificar demasiado

1. Nombres oficiales de familias de reportes.
2. Catálogo mínimo de permisos `reports.*`.
3. Clases oficiales de `truth_level`.
4. Source types oficiales.
5. Política de snapshots certificados.
6. Política de watermark y exportación.
7. Política de redacción PII.
8. Retención por clase de reporte.
9. Taxonomía mínima de errores del módulo.
10. Contrato de onboarding para módulos futuros.

---

# 29. Checklist de aceptación ejecutiva

Un `apps/reportes` v1 se considera correcto si:

* existe como módulo transversal en backend;
* registra reportes por contrato;
* puede ejecutar al menos una familia `AUDIT`, `OBS`, `TRACE`;
* respeta scope y RBAC;
* audita exportes y lecturas sensibles;
* soporta snapshots para al menos un reporte reproducible;
* expone una API coherente;
* no rompe ownership de kernels;
* queda listo para que Dashboard lo consuma después.

---

# 30. Instrucciones explícitas para Codex

## 30.1 Lo que sí puede hacer

* crear `apps/reportes`;
* proponer modelos/serializers/services/tests coherentes con este blueprint;
* reutilizar contratos vigentes del repo (scope, RBAC, auditoría, envelope de error, request_id);
* implementar por PRs pequeños y aditivos;
* dejar notas ADR/documentación cuando congele un contrato.

## 30.2 Lo que no puede hacer

* inventar ownerships nuevos en kernels;
* mover verdad primaria fuera de Billing/Inventory/Payments/Accounting;
* meter Dashboard dentro de `reportes`;
* saltarse auditoría para exportes/lecturas sensibles;
* introducir breaking changes a contratos existentes sin documento y migración;
* asumir que todos los módulos actuales ya están maduros: debe tratar Billing/Inventory/Payments con integración gradual.

## 30.3 Orden recomendado de implementación

1. registry + definitions
2. run + scope + RBAC
3. read audit + exports
4. audit reporting
5. observability reporting
6. trace reporting
7. snapshots/manifests
8. certified reporting
9. onboarding future modules

---

# 31. Conclusión

El módulo `reportes` debe construirse como **fabric institucional de reporting** del sistema, no como una colección accidental de listados.

Su forma correcta es:

* transversal,
* contractual,
* multi-carril,
* reproducible cuando corresponde,
* auditable siempre,
* future-ready por diseño.

Este blueprint deja a `reportes` listo para:

* servir a operación,
* servir a auditoría,
* servir a investigación técnica,
* servir a control interno,
* servir a reportes institucionales,
* y ser la base formal que Dashboard consumirá después.

```

Este blueprint está alineado con la topología objetivo y ownerships del sistema, con los contratos transversales de scope/RBAC/auditoría/error envelope, y con el roadmap que todavía deja pendiente el motor de reportes formal como siguiente capa antes del dashboard :contentReference[oaicite:4]{index=4} :contentReference[oaicite:5]{index=5} :contentReference[oaicite:6]{index=6}
```
