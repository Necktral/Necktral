# Análisis de Robustez Multiplataforma — Necktral ERP/CRM

> Versión 1.0 — 2026-05-27  
> Objetivo: Identificar fallos potenciales, cuellos de botella, inconsistencias, huecos y sugerencias para robustecer el sistema multiplataforma.

---

## Resumen Ejecutivo

| Área | Estado | Score Riesgo | Vector principal |
|------|--------|:------------:|:-----------------|
| Backup / Recuperación | 🔴 Inexistente | 10 | Volume sin snapshot, sin pg_dump, sin WAL archiving |
| Concurrencia (GL/Sync) | 🔴 Sin protección | 9 | 4 endpoints críticos sin `select_for_update` |
| Sync Engine (crypto) | 🔴 Clock skew 6h + secrets plaintext | 9 | Replay window + HMAC sin cifrar en DB |
| Test Coverage (views) | 🔴 Excluido de CI | 8 | `views.py` en `.coveragerc` exclude → regresiones invisibles |
| Billing/Inventory/Payments | 🔴 Solo scaffolding | 8 | Modelos sin lógica = sistema no monetizable |
| Token/Session Security | 🟠 Parcial | 6-7 | Race en rotation + chain infinita |
| Observabilidad | 🟠 Ciega en prod | 4-6 | Sin métricas exportables, sin alertas |
| Frontend multiplataforma | 🟠 Solo web, sin tests | 4 | 1 test, sin PWA, sin mobile |
| Autenticación/2FA | 🟡 Sólido | 3 | Funcional, detalles menores (CSP localhost) |
| CI/CD | 🟡 Maduro | 2 | Funcional, gap en coverage scope |

---

## 1. POSIBLES FALLOS (Failure Modes)

### 1.1 Fallos de Concurrencia

| ID | Componente | Fallo | Impacto | Mitigación actual | Recomendación |
|----|-----------|-------|---------|-------------------|---------------|
| F01 | `FiscalPeriodCloseView` | Race condition: dos cierres simultáneos del mismo período | Doble cierre, journal entries duplicados | `UniqueConstraint` en modelo | Agregar `select_for_update()` en el cierre + validación de estado atómico |
| F02 | `JournalDraftPostView` | Posting concurrente del mismo draft | Double-posting si no hay lock | Sin lock explícito visible | Agregar `select_for_update(nowait=True)` antes de transición de estado |
| F03 | `SyncBatchView` | Batches concurrentes del mismo device con secuencias solapadas | Gaps en `last_accepted_sequence` | `last_accepted_sequence` field existe | Implementar `select_for_update` en Device durante batch + validación secuencia estricta |
| F04 | `IntercompanyTransactionConfirmView` | Dos partes confirman simultáneamente | Estado inconsistente entre entidades | Sin evidencia de locking | Lock pesimista en transacción + FSM guard |
| F05 | `RefreshTokenSession` | Token rotation race (múltiples tabs) | Sesión invalidada innecesariamente | `replaced_by_jti` field | Implementar grace period (ventana de 30s para tokens rotados) |

### 1.2 Fallos de Integridad de Datos

| ID | Componente | Fallo | Impacto | Recomendación |
|----|-----------|-------|---------|---------------|
| F06 | `EconomicEvent.payload` | JSONField sin schema validation | Payloads malformados pasan a GL | Agregar JSON Schema validation por `event_type` en `clean()` |
| F07 | `AppliedCommand.result_ref` | JSONField sin tipado fuerte | Refs inconsistentes entre handlers | Definir TypedDict por `command_type` |
| F08 | `BillingDocument` (kernel) | Sin state machine enforced | Transiciones ilegales posibles | Implementar FSM con `django-fsm` o guards manuales |
| F09 | `StockBalance` (kernel) | Sin constraint de no-negativos | Stock negativo posible sin trigger DB | Agregar `CheckConstraint(condition=Q(quantity__gte=0))` |
| F10 | Audit chain | `prev_hash` en `AppliedCommand` es opcional (blank=True) | Cadena rota si primer comando no tiene prev_hash | Definir valor semilla ("genesis") para primer comando por device |

### 1.3 Fallos de Disponibilidad

| ID | Componente | Fallo | Impacto | Recomendación |
|----|-----------|-------|---------|---------------|
| F11 | PostgreSQL single-node | Punto único de fallo | Downtime total | Plan de réplica read-only + failover (Phase 2) |
| F12 | `AUTH_COOKIE_SECURE=False` default | Cookies no seguras en entornos mal configurados | Intercepción de tokens | Forzar `True` en prod.py (verificar) |
| F13 | Gunicorn workers fijo (4) | Saturación bajo carga | Timeout en auth/sync | Auto-scaling workers basado en CPU cores (`2*cores + 1`) |
| F14 | Sin circuit breaker en `integration` módulo | Cascading failure si servicio externo cae | Backend bloqueado | Implementar circuit breaker pattern (tenacity/pybreaker) |

---

## 2. CUELLOS DE BOTELLA (Bottlenecks)

### 2.1 Base de Datos

| ID | Cuello | Evidencia | Impacto | Recomendación |
|----|--------|-----------|---------|---------------|
| B01 | `AuditEvent` sin particionamiento | Tabla crece ilimitadamente (append-only) | Queries lentos en audit trail | Particionar por `timestamp_server` (mensual) |
| B02 | `AppliedCommand` indexado por `received_at` | Volumen alto en sincronización masiva | Full table scan en reportes | Agregar índice compuesto `(company, command_type, received_at)` |
| B03 | `DeviceRequestNonce` sin cleanup | Anti-replay nonces se acumulan indefinidamente | Tabla crece sin límite | Implementar TTL cleanup (cron/management command) — retener solo 48h |
| B04 | `JournalEntry` + `JournalLine` joins | Reportes contables con muchas líneas | Tiempo de respuesta >2s en trial balance | Materializar saldos incrementales (trigger o batch) |
| B05 | CORS + 18 middlewares | Cada request pasa 18 capas | Overhead en latencia P99 | Audit: medir overhead real; considerar bypass para health/readiness |

### 2.2 Sincronización

| ID | Cuello | Evidencia | Impacto | Recomendación |
|----|--------|-----------|---------|---------------|
| B06 | Batch limit 100 commands | Dispositivos con acumulación >100 requieren múltiples requests | Latencia en reconexión tras offline largo | Implementar compresión + batch streaming (chunks progresivos) |
| B07 | Ed25519 verify por cada comando | CPU-bound en batches grandes | Throttle efectivo en sync heavy | Considerar firma por batch (no por comando) para v3 protocol |
| B08 | `transaction.atomic()` por batch completo | Un comando fallido puede bloquear toda la TX | Lock contention en tabla Device | Evaluar savepoints por comando individual |

### 2.3 Frontend

| ID | Cuello | Evidencia | Impacto | Recomendación |
|----|--------|-----------|---------|---------------|
| B09 | Sin service worker / PWA manifest | Offline-first solo en sync engine backend | Frontend no funciona offline | Implementar service worker con cache estratégico |
| B10 | Sin lazy loading de rutas | 20 pages cargadas potencialmente en bundle | TTI elevado en mobile | Implementar `defineAsyncComponent` + route-level code splitting |
| B11 | Axios sin retry automático | Requests fallidos requieren refresh manual | UX degradada en conexiones inestables | Agregar axios interceptor con retry exponential (3 intentos) |

---

## 3. INCONSISTENCIAS

### 3.1 Arquitecturales

| ID | Inconsistencia | Detalle | Impacto | Corrección |
|----|---------------|---------|---------|------------|
| C01 | Dual `manage.py` | Dos archivos manage.py (raíz + src/) | Confusión en desarrollo | Eliminar uno, documentar el canónico |
| C02 | Módulos vs Kernels duplicados | `apps.modulos.accounting` (vacío) + `apps.kernels.accounting` (real) | Confusión de imports | Eliminar módulos-stub o convertir en re-exports explícitos |
| C03 | Sync v1 vs v2 coexistencia | `apps.modulos.sync` (HMAC legacy) + `apps.modulos.sync_engine` (Ed25519) | Dos paths de autenticación device | Deprecar v1 con timeline, sunset header |
| C04 | `test/` duplicación | `login_module/tests/` vs `login_module/src/tests/` | Tests ejecutados selectivamente | Unificar en una sola ubicación |
| C05 | Naming inconsistente | `estacion_servicios` (español) vs `retail_pos` (inglés) | Confusión naming | Adoptar convención única (español canónico según docs) |

### 3.2 De Contratos

| ID | Inconsistencia | Detalle | Impacto | Corrección |
|----|---------------|---------|---------|------------|
| C06 | Error envelope parcial | `ApiErrorEnvelopeMiddleware` existe pero no todos los views lo usan | Respuestas de error heterogéneas | Auditar todas las views: asegurar que `build_error_envelope` se use universalmente |
| C07 | Throttle scopes incompletos | Solo `auth_login`, `auth_refresh`, `auth_logout`, `me_read`, `me_acl_read` | Endpoints de accounting/sync sin throttle específico | Agregar scopes: `sync_batch`, `accounting_report`, `billing_write` |
| C08 | Audit events sin catálogo cerrado | `write_event` acepta cualquier `event_type` string | Eventos no documentados se infiltran | Crear enum/registry de event_types válidos con validación |
| C09 | RBAC permission strings dispersas | `rbac_permission("sync_engine.enroll_device")` hardcoded | Sin catálogo centralizado | Crear archivo `permissions_registry.py` con todas las perms |

### 3.3 De Frontend-Backend

| ID | Inconsistencia | Detalle | Impacto | Corrección |
|----|---------------|---------|---------|------------|
| C10 | Headers custom sin validación FE | Backend requiere `X-Company-Id` pero FE puede omitirlo | 403 sin mensaje claro | Agregar interceptor axios que inyecte automáticamente |
| C11 | Versión API no versionada en URL | `/api/auth/*`, `/api/accounting/*` sin `/v1/` | Breaking changes sin aviso | Implementar versionado: `/api/v1/auth/*` (o header `Accept-Version`) |
| C12 | OpenAPI schema sin validación en FE | `drf-spectacular` genera schema pero FE no lo consume tipado | Drift entre contratos | Generar tipos TypeScript desde OpenAPI (openapi-typescript) |

---

## 4. HUECOS (Gaps)

### 4.1 Funcionales

| ID | Hueco | Estado actual | Riesgo | Prioridad |
|----|-------|---------------|--------|-----------|
| G01 | **Billing kernel sin lógica** | Solo modelos (BillingSequence, BillingDocument, BillingLine) | No se puede facturar | 🔴 CRÍTICO |
| G02 | **Inventory kernel sin lógica** | Solo modelos (Warehouse, InventoryItem, StockBalance) | No hay control de stock | 🔴 CRÍTICO |
| G03 | **Payments kernel sin lógica** | Solo modelos (PaymentTransaction) | No se procesan pagos | 🔴 CRÍTICO |
| G04 | **CEC sin control plane** | Módulo existe pero sin validación cruzada | Sin reconciliación automática | 🟡 ALTO |
| G05 | **Outbox pattern no implementado** | `source_outbox_event_id` en EconomicEvent pero sin outbox real | Eventos perdidos entre módulos | 🟡 ALTO |
| G06 | **Mobile app inexistente** | Frontend es solo web (Quasar sin Capacitor/Cordova) | Sin operación móvil offline | 🟡 ALTO |
| G07 | **Reporting kernel limitado** | Solo vistas de consolidación | Sin exports PDF/Excel, sin scheduled reports | 🟡 MEDIO |
| G08 | **Multi-moneda parcial** | `FxRate` + revaluación existe, pero sin soporte en Billing/Inventory | Inconsistencia en documentos multi-currency | 🟡 MEDIO |

### 4.2 No-Funcionales

| ID | Hueco | Estado actual | Riesgo | Prioridad |
|----|-------|---------------|--------|-----------|
| G09 | **Sin health check endpoint dedicado** | Solo `HealthView` en accounting | Sin readiness/liveness para orquestador | 🟡 ALTO |
| G10 | **Sin métricas Prometheus** | `config.metrics.record_sync_batch` existe pero sin export | No hay dashboards operativos | 🟡 ALTO |
| G11 | **Sin rate limiting en sync batch** | Throttle solo en auth endpoints | Dispositivo comprometido puede saturar | 🟡 ALTO |
| G12 | **Sin backup automatizado** | `compose.prod.yaml` no incluye backup de pgdata | Pérdida de datos posible | 🔴 CRÍTICO |
| G13 | **Sin test E2E** | Backend 72 unit tests, Frontend 1 test | Sin validación de flujos completos | 🟡 ALTO |
| G14 | **Sin chaos testing** | No hay simulación de fallos | Comportamiento desconocido bajo stress | 🟡 MEDIO |
| G15 | **Sin API versioning** | Breaking changes afectan todos los clientes | Imposible evolucionar sin romper | 🟡 MEDIO |
| G16 | **Frontend sin tests** | Solo 1 archivo de test (vitest) | Regresiones no detectadas | 🟡 ALTO |

---

## 5. SUGERENCIAS PARA ROBUSTECER EL SISTEMA MULTIPLATAFORMA

### 5.1 Prioridad Inmediata (Sprint 1-2, semanas 1-4)

#### S01: Blindar concurrencia en operaciones críticas
```python
# accounting/views.py - FiscalPeriodCloseView
with transaction.atomic():
    period = FiscalPeriod.objects.select_for_update(nowait=True).get(pk=period_id)
    if period.status != FiscalPeriod.Status.OPEN:
        raise ValidationError("Period already closed")
    # ... close logic
```

#### S02: Agregar constraint de stock no-negativo
```python
# inventarios/models.py
class StockBalance(models.Model):
    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=Decimal("0")),
                name="ck_stock_balance_non_negative",
            ),
        ]
```

#### S03: Implementar cleanup de nonces expirados
```python
# sync_engine/management/commands/cleanup_expired_nonces.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.modulos.sync_engine.models import DeviceRequestNonce

class Command(BaseCommand):
    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=48)
        deleted, _ = DeviceRequestNonce.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f"Deleted {deleted} expired nonces")
```

#### S04: Agregar throttle a sync batch
```python
# settings/base.py
# Fragmento a agregar en REST_FRAMEWORK settings:
REST_FRAMEWORK = {
    # ... otras configuraciones existentes ...
    "DEFAULT_THROTTLE_RATES": {
        "sync_batch": "30/min",  # por device
        "accounting_report": "20/min",
    }
}
```

#### S05: Health check unificado
```python
# config/views.py
class SystemHealthView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        checks = {
            "database": self._check_db(),
            "redis": self._check_redis(),  # si aplica
            "disk": self._check_disk(),
        }
        status_code = 200 if all(checks.values()) else 503
        return Response({"status": "healthy" if status_code == 200 else "degraded", "checks": checks}, status=status_code)
```

### 5.2 Prioridad Alta (Sprint 3-4, semanas 5-8)

#### S06: Implementar FSM en Billing
```python
# Billing document lifecycle
STATES = {
    "DRAFT": ["VALIDATED"],
    "VALIDATED": ["POSTED", "CANCELLED"],
    "POSTED": ["VOIDED"],
    "VOIDED": [],
    "CANCELLED": [],
}

def transition(document, target_state):
    if target_state not in STATES.get(document.status, []):
        raise ValidationError(f"Cannot transition from {document.status} to {target_state}")
    document.status = target_state
```

#### S07: Generar tipos TypeScript desde OpenAPI
```javascript
// package.json scripts
{
  "generate:api": "openapi-typescript http://localhost:8000/api/schema/ -o src/api/types.ts"
}
```

#### S08: Implementar Service Worker para PWA
```typescript
// frontend/src-pwa/custom-service-worker.ts
import { precacheAndRoute } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { NetworkFirst, CacheFirst } from 'workbox-strategies';

precacheAndRoute(self.__WB_MANIFEST);

// API calls: network-first with fallback
registerRoute(
  ({url}) => url.pathname.startsWith('/api/'),
  new NetworkFirst({ cacheName: 'api-cache', networkTimeoutSeconds: 5 })
);
```

#### S09: Retry interceptor en Axios
```typescript
// frontend/src/boot/axios.ts
import axios from 'axios';

const MAX_RETRIES = 3;
axios.interceptors.response.use(null, async (error) => {
  const config = error.config;
  if (!config || config._retryCount >= MAX_RETRIES) return Promise.reject(error);
  if (error.response?.status >= 500 || !error.response) {
    config._retryCount = (config._retryCount || 0) + 1;
    const delay = Math.pow(2, config._retryCount) * 1000;
    await new Promise(r => setTimeout(r, delay));
    return axios(config);
  }
  return Promise.reject(error);
});
```

#### S10: Backup automatizado en producción
```yaml
# compose.prod.yaml - agregar servicio
  db-backup:
    image: prodrigestivill/postgres-backup-local:16
    environment:
      POSTGRES_HOST: db
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      SCHEDULE: "@daily"
      BACKUP_KEEP_DAYS: 30
    volumes:
      - ./backups:/backups
    depends_on:
      db:
        condition: service_healthy
```

### 5.3 Prioridad Media (Sprint 5-8, semanas 9-16)

#### S11: Capacitor para app móvil nativa
```bash
# Quasar ya soporta Capacitor
quasar mode add capacitor
# Agregar plugins offline
npm install @capacitor/filesystem @capacitor/network @capacitor/preferences
```

#### S12: Event registry cerrado
```python
# audit/event_registry.py
from enum import StrEnum

class AuditEventType(StrEnum):
    # Auth
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    TWO_FACTOR_SETUP = "TWO_FACTOR_SETUP"
    TWO_FACTOR_VERIFIED = "TWO_FACTOR_VERIFIED"
    # Sync
    SYNC_BATCH_RECEIVED = "SYNC_BATCH_RECEIVED"
    SYNC_COMMAND_APPLIED = "SYNC_COMMAND_APPLIED"
    SYNC_AUTH_REJECTED = "SYNC_AUTH_REJECTED"
    DEVICE_ENROLLED = "DEVICE_ENROLLED"
    DEVICE_REVOKED = "DEVICE_REVOKED"
    # Accounting
    JOURNAL_POSTED = "JOURNAL_POSTED"
    PERIOD_CLOSED = "PERIOD_CLOSED"
    FX_REVALUATION = "FX_REVALUATION"
    # ... catálogo completo

def validate_event_type(event_type: str) -> None:
    if event_type not in AuditEventType.__members__.values():
        raise ValueError(f"Unknown event type: {event_type}")
```

#### S13: Permissions registry centralizado
```python
# common/permissions_registry.py
"""Catálogo centralizado de permisos RBAC del sistema."""

PERMISSIONS = {
    # Sync Engine
    "sync_engine.create_enrollment_challenge": "Crear challenge de enrollment de dispositivo",
    "sync_engine.enroll_device": "Enrollar dispositivo con challenge",
    "sync_engine.revoke_device": "Revocar dispositivo",
    "sync_engine.list_devices": "Listar dispositivos",
    # Accounting
    "accounting.post_journal": "Postear asiento contable",
    "accounting.close_period": "Cerrar período fiscal",
    "accounting.reverse_entry": "Reversar asiento",
    # Billing
    "billing.create_document": "Crear documento fiscal",
    "billing.void_document": "Anular documento fiscal",
    # ...
}
```

#### S14: Prometheus metrics export
```python
# config/metrics.py - ampliar
from prometheus_client import Counter, Histogram, generate_latest

sync_batch_total = Counter("necktral_sync_batch_total", "Total sync batches", ["status"])
sync_batch_duration = Histogram("necktral_sync_batch_duration_seconds", "Batch processing time")
api_request_duration = Histogram("necktral_api_request_duration_seconds", "API latency", ["method", "endpoint"])

# Exponer en /metrics (solo internal)
class MetricsView(APIView):
    permission_classes = [AllowAny]  # Proteger por IP/network policy
    def get(self, request):
        return HttpResponse(generate_latest(), content_type="text/plain")
```

---

## 6. MATRIZ DE RIESGOS CONSOLIDADA

> **Metodología de scoring**: Cada riesgo se evalúa con CVSS adaptado para aplicaciones ERP. El score combina: Explotabilidad (¿qué tan fácil es que ocurra sin intervención?), Alcance (¿cuántos subsistemas se ven afectados?), Recuperabilidad (¿se puede revertir o el daño es permanente?). Escala 1-10, donde ≥8 es CRÍTICO, 5-7 SEVERO, 3-4 MODERADO.

### 🔴 NIVEL CRÍTICO — Score ≥ 8 (pérdida de datos o compromiso del sistema)

| #  | ID      | Riesgo | Descripción técnica del vector | Score | Explotabilidad | Alcance | Recuperabilidad |
|:--:|:-------:|:-------|:-------------------------------|:-----:|:--------------:|:-------:|:---------------:|
| 1  | G12 | **Sin backup automatizado** | `compose.prod.yaml` monta `pgdata` como volume sin snapshot. Un `docker volume rm` accidental, corrupción de disco o ransomware = pérdida total. No existe `pg_dump` scheduled ni WAL archiving. | **10** | Pasiva (ocurre sin atacante) | Total — todos los datos | Irrecuperable |
| 2  | F01 | **Race condition en cierre fiscal** | `FiscalPeriodCloseView` ejecuta `period.status = 'closed'` + `save()` sin `select_for_update`. Dos requests simultáneos pueden cerrar el mismo período generando journal entries duplicados. El `UniqueConstraint` del modelo NO protege la ventana entre read y write. | **9** | Media (requiere concurrencia natural en multi-usuario) | Contabilidad completa — GL corrupto | Requiere rollback manual de entries |
| 3  | F03 | **Sync batch sin lock en Device** | `SyncBatchView` lee `device.last_accepted_sequence`, procesa N comandos, y escribe el nuevo sequence. Sin `select_for_update` en Device, dos batches paralelos del mismo dispositivo pueden producir gaps o sobreescritura de sequence. | **9** | Alta (dispositivo con cola larga reconectándose) | Integridad de sync — comandos perdidos silenciosamente | Datos del dispositivo irreconciliables |
| 4  | SEC-01 | **Clock skew de 6 horas en sync** | `SYNC_MAX_DEVICE_CLOCK_SKEW_SECONDS = 6*3600`. Un atacante que captura un request firmado tiene 6 horas para replay. El nonce anti-replay solo protege si el nonce original fue registrado, pero nonces sin cleanup (B03) + ventana de 6h = superficie de ataque masiva. | **9** | Alta (sniffing + replay trivial en ventana de 6h) | Autenticación de dispositivos | No hay rollback — comandos ejecutados son permanentes |
| 5  | SEC-02 | **HMAC secrets en plaintext (sync v1)** | `DeviceEnrollment.hmac_secret` almacena el secreto en Base64 (encoding, NO cifrado). Compromiso de DB = compromiso de TODOS los dispositivos legacy. No hay KDF, no hay envelope encryption. | **8** | Requiere acceso a DB (SQLi, backup leak, insider) | Todos los dispositivos sync v1 | Requiere re-enrollment de toda la flota |
| 6  | F02 | **Double-posting de journal draft** | `JournalDraftPostView` transiciona `draft → posted` sin lock. Posting concurrente del mismo draft genera asientos contables duplicados en el GL. No hay idempotency key en la operación. | **8** | Media (click doble en UI, retry automático) | General Ledger — balances incorrectos | Requiere reversión contable manual |
| 7  | G01-G03 | **Kernels sin lógica de negocio** | `billing`, `inventarios`, `payments` tienen modelos pero CERO lógica (sin FSM, sin validaciones, sin workflows). El sistema acepta operaciones pero no las procesa — se acumulan como datos muertos sin efecto contable. | **8** | Cierta (es el estado actual) | Facturación + Stock + Pagos = core del ERP | No aplica — funcionalidad inexistente |
| 8  | SEC-03 | **views.py excluido de coverage** | `.coveragerc` excluye `*/views.py`. Los endpoints son la superficie de ataque principal y NO tienen cobertura de tests verificada en CI. Cualquier regresión en auth/permissions pasa desapercibida. | **8** | Pasiva (bugs no detectados) | Seguridad de toda la API | Depende de detección manual |

### 🟠 NIVEL SEVERO — Score 5-7 (degradación de servicio o brecha de seguridad parcial)

| #  | ID      | Riesgo | Descripción técnica del vector | Score | Explotabilidad | Alcance | Recuperabilidad |
|:--:|:-------:|:-------|:-------------------------------|:-----:|:--------------:|:-------:|:---------------:|
| 9  | SEC-04 | **Adminer expuesto sin auth** | `compose.yaml` perfil `tools` expone Adminer en `:8080` sin credenciales propias. Si se activa en prod (perfil mal configurado), la DB queda expuesta con acceso completo. | **7** | Requiere perfil tools activo | Base de datos completa | Revocar acceso — pero datos ya expuestos |
| 10 | F05 | **Token rotation race multi-tab** | `RefreshTokenSession` rota token en cada refresh. Tab A refresca → invalida token de Tab B → Tab B intenta refrescar con token inválido → logout forzado. No hay grace period para tokens recién rotados. | **7** | Alta (cualquier usuario con >1 tab) | Sesión del usuario | Auto-recuperable con re-login |
| 11 | B03 | **Nonces sin TTL ni cleanup** | `DeviceRequestNonce` es append-only sin índice temporal ni job de limpieza. En producción con N dispositivos sincronizando M requests/día = tabla crece indefinidamente. A 1M+ rows, las queries de anti-replay degradan la latencia del sync. | **7** | Pasiva (crece por uso normal) | Performance de sync — escala temporal | Truncar tabla + agregar TTL |
| 12 | SEC-05 | **CSP con localhost en connect-src** | `CSP_CONNECT_SRC` incluye `http://localhost:*` — artefacto de desarrollo. Si llega a prod, permite exfiltración de datos a localhost (XSS + port scanning interno). | **6** | Requiere XSS previo | Depende del contexto del XSS | Cambio de configuración |
| 13 | B05 | **18 middlewares en pipeline** | Cada request HTTP atraviesa 18 capas de middleware (CORS, CSP, CSRF, Auth, Org, Audit, etc.). Endpoints de alta frecuencia como sync y health no tienen bypass. P99 latency incluye overhead innecesario. | **6** | Pasiva (diseño actual) | Latencia global de la API | Refactor de middleware ordering |
| 14 | G11 | **Sync batch sin throttle dedicado** | `SyncBatchView` no tiene throttle scope propio. Un dispositivo comprometido o con bug puede enviar batches en loop saturando workers de Gunicorn (4 fijos) y bloqueando auth para otros usuarios. | **6** | Media (dispositivo comprometido o código buggy) | Disponibilidad del backend | Kill del proceso + throttle |
| 15 | F09 | **Stock negativo permitido** | `StockBalance` no tiene `CheckConstraint(quantity__gte=0)`. La ausencia de constraint DB permite que bugs en lógica futura generen stock negativo sin que la DB lo rechace. | **6** | Requiere bug en código futuro | Integridad de inventario | Corrección de datos + constraint |
| 16 | SEC-06 | **Refresh token sin límite de cadena** | `ROTATE_REFRESH_TOKENS=True` pero sin `max_chain_length`. Un atacante con un refresh token puede generar cadena infinita de tokens válidos. La revocación por `replaced_by_jti` solo invalida el inmediato anterior, no toda la cadena. | **6** | Requiere token robado | Sesión del usuario comprometido | Revocar todas las sesiones del user |
| 17 | F04 | **Intercompany confirm sin lock** | `IntercompanyTransactionConfirmView` permite que ambas partes confirmen simultáneamente sin lock pesimista. Estado final inconsistente si ambas transiciones ocurren en la misma ventana de tiempo. | **5** | Baja (requiere timing preciso entre empresas) | Transacción intercompany específica | Reconciliación manual |
| 18 | B04 | **Trial balance sin materialización** | `JournalEntry + JournalLine` JOIN para calcular saldos en cada request. Con volumen de 10K+ asientos, el trial balance supera 2s de latencia sin índices compuestos ni vistas materializadas. | **5** | Pasiva (crece con volumen) | UX de reportes contables | Materializar saldos incrementales |
| 19 | C06 | **Error envelope parcial** | `ApiErrorEnvelopeMiddleware` existe pero no todas las views devuelven errores a través del envelope. Algunas views lanzan DRF exceptions directamente → el frontend recibe formatos de error heterogéneos → handling de errores frágil. | **5** | Cierta (es el estado actual) | Confiabilidad del manejo de errores en FE | Auditar y unificar todas las views |

### 🟡 NIVEL MODERADO — Score 3-4 (deuda técnica con impacto operativo)

| #  | ID      | Riesgo | Descripción técnica del vector | Score | Explotabilidad | Alcance | Recuperabilidad |
|:--:|:-------:|:-------|:-------------------------------|:-----:|:--------------:|:-------:|:---------------:|
| 20 | G16 | **Frontend sin test coverage** | 1 archivo de test (vitest) para toda la aplicación Quasar. Regresiones en auth flow, routing, stores, y servicios no son detectadas. El CI no puede bloquear merges con bugs de UI. | **4** | Pasiva | Calidad del frontend | Crear suite de tests |
| 21 | C01-C04 | **Duplicación estructural** | Dual `manage.py`, módulos stub vs kernels reales, `test/` en dos ubicaciones, sync v1/v2 coexistiendo. Aumenta la carga cognitiva, genera bugs por import incorrecto, dificulta onboarding. | **4** | Pasiva | Mantenibilidad | Cleanup + docs |
| 22 | G10 | **Sin métricas exportables** | `config.metrics.record_sync_batch` registra internamente pero sin export Prometheus/StatsD. Imposible crear dashboards, alertas, o detectar anomalías en producción. Operación ciega. | **4** | Pasiva | Observabilidad operativa | Agregar exporter |
| 23 | C12 | **Drift de tipos FE↔BE** | `drf-spectacular` genera OpenAPI schema pero el frontend no consume tipos generados. Los DTOs en TypeScript se mantienen manualmente → desincronización silenciosa cuando el backend cambia un field. | **4** | Alta (ocurre en cada refactor) | Integridad de datos en UI | Pipeline de generación de tipos |
| 24 | B06 | **Batch limit 100 insuficiente** | `SYNC_MAX_COMMANDS_PER_BATCH=100`. Dispositivo offline 1 semana con 50 ops/día = 350 comandos = 4 roundtrips mínimos. En conexiones inestables (campo), cada roundtrip puede fallar y reiniciar. | **4** | Baja (requiere offline prolongado) | Reconexión de dispositivos | Streaming/chunking adaptativo |
| 25 | G06 | **Sin mobile nativo** | Frontend Quasar sin Capacitor/Cordova. No hay acceso a hardware nativo (cámara para scanner, NFC, push notifications nativas, biometric auth). Limita casos de uso en campo. | **3** | N/A (feature gap) | Experiencia móvil | Capacitor integration |
| 26 | SEC-07 | **`granted_by` nullable en AdminGrant** | `AdminGrant.granted_by` puede ser NULL. Imposible auditar quién otorgó privilegios de admin. Rompe chain of custody para compliance. | **3** | Pasiva | Auditoría de privilegios | Hacer field non-nullable + migration |
| 27 | C11 | **API sin versionado** | Todos los endpoints en `/api/` sin prefijo de versión. Cualquier breaking change afecta a todos los clientes simultáneamente. Imposible deprecar gracefully. | **3** | Pasiva (afecta en siguiente breaking change) | Evolución del API | Implementar `/api/v1/` |

---

## 7. DEPENDENCIAS ENTRE RIESGOS (Grafo de Impacto)

```
SEC-01 (clock skew 6h) ──→ amplifica ──→ B03 (nonces sin cleanup)
                         └─→ habilita ──→ replay en ventana de 6h

F01 (race cierre fiscal) ──→ corrompe ──→ B04 (trial balance lento con datos duplicados)
F02 (double-posting)     ──→ corrompe ──→ B04

G12 (sin backup) ──→ convierte en irrecuperable ──→ TODOS los riesgos de integridad (F01-F09)

SEC-03 (views sin coverage) ──→ oculta ──→ regresiones en auth/RBAC → SEC-06 no detectado

G01-G03 (kernels vacíos) ──→ bloquea ──→ monetización del sistema (billing, pagos)
                          └─→ invalida ──→ CEC control plane (G04) — no hay datos que reconciliar
```

> **Conclusión del grafo**: G12 (backup) es el multiplicador de daño. Cualquier bug de integridad pasa de "recuperable" a "catastrófico" sin backup. SEC-01 + B03 forman un vector de ataque compuesto que debe resolverse en conjunto.

---

## 8. PLAN DE ACCIÓN

> **Nota**: No se trabaja con estimaciones de esfuerzo. Lo que se propone, se ejecuta completo.

### Bloque A — Supervivencia (ejecutar primero, sin excepción)

| # | Acción | Archivo(s) afectado(s) | Validación |
|:-:|:-------|:-----------------------|:-----------|
| 1 | Backup automatizado: `pg_dump` + WAL archiving + retention policy | `compose.prod.yaml`, nuevo `scripts/backup.sh` | Restore exitoso en entorno limpio |
| 2 | `select_for_update(nowait=True)` en `FiscalPeriodCloseView` | `apps/kernels/accounting/views.py` | Test concurrente con `threading` confirma que segundo request falla con 423 |
| 3 | `select_for_update` en `SyncBatchView` sobre Device | `apps/modulos/sync_engine/views.py` | Test de batch paralelo demuestra rechazo correcto |
| 4 | `select_for_update` en `JournalDraftPostView` | `apps/kernels/accounting/views.py` | Test double-post retorna 409 |
| 5 | Reducir clock skew a 300s (5 min) | `config/settings/base.py` | Tests de sync con timestamp fuera de ventana fallan |
| 6 | Cifrar HMAC secrets con Fernet (encryption at rest) o migrar flota a v2 | `apps/modulos/sync/models.py` | Secrets no legibles en raw DB dump |

### Bloque B — Integridad y Seguridad

| # | Acción | Archivo(s) afectado(s) | Validación |
|:-:|:-------|:-----------------------|:-----------|
| 7 | `CheckConstraint(condition=Q(quantity__gte=0))` en StockBalance | `apps/kernels/inventarios/models.py` | `IntegrityError` al intentar stock negativo |
| 8 | Incluir `views.py` en coverage (eliminar exclusión) | `.coveragerc` | CI reporta coverage de endpoints |
| 9 | Nonce cleanup: management command + `cron` en Docker (retener 48h max) | `apps/modulos/sync_engine/management/commands/` | Table size estable tras 48h de operación |
| 10 | Grace period 30s en token rotation | `apps/modulos/accounts/views.py` | Test multi-tab no genera logout spurio |
| 11 | Throttle scope `sync_batch: 30/min` por device | `config/settings/base.py`, `sync_engine/views.py` | Device en loop recibe 429 |
| 12 | Eliminar `localhost` de `CSP_CONNECT_SRC` en prod | `config/settings/prod.py` | CSP header en response no contiene localhost |
| 13 | `granted_by` non-nullable + data migration | `apps/modulos/iam/models.py` | Migration falla si hay grants sin grantor |
| 14 | Refresh token chain limit (max 50 rotaciones) | `apps/modulos/accounts/views.py` | Token con chain_length=51 rechazado |

### Bloque C — Consistencia y Observabilidad

| # | Acción | Archivo(s) afectado(s) | Validación |
|:-:|:-------|:-----------------------|:-----------|
| 15 | Unificar error envelope en TODAS las views | `apps/modulos/common/middleware.py` + views | Ningún endpoint devuelve error fuera del envelope |
| 16 | Event type registry cerrado con Enum | `apps/modulos/audit/registry.py` (nuevo) | `write_event` con type no registrado → `ValueError` |
| 17 | Permissions registry centralizado | `apps/modulos/rbac/registry.py` (nuevo) | Import de permission no registrada → error en startup |
| 18 | Prometheus exporter básico (request latency, sync throughput, error rate) | `config/metrics.py` + `/metrics` endpoint | Grafana puede scrape y mostrar dashboard |
| 19 | Eliminar duplicaciones: manage.py único, módulos-stub eliminados, sync v1 deprecated con sunset header | Raíz del proyecto + imports | CI verde, no hay imports rotos |
| 20 | Health check unificado (`/api/health/`) con DB + Redis + disk checks | `apps/modulos/common/views.py` (nuevo) | Kubernetes readiness probe funciona |

### Bloque D — Multiplataforma y Completitud

| # | Acción | Archivo(s) afectado(s) | Validación |
|:-:|:-------|:-----------------------|:-----------|
| 21 | Service worker PWA con cache estratégico (stale-while-revalidate) | `frontend/src-pwa/` | App funciona offline (cache hit en Network tab) |
| 22 | Axios retry interceptor (3 reintentos, backoff exponencial) | `frontend/src/boot/axios.ts` | Request fallido se reintenta y eventualmente resuelve |
| 23 | Generación automática de tipos TS desde OpenAPI | `frontend/scripts/generate-types.ts` (nuevo) | Types match API schema, CI falla si hay drift |
| 24 | Lazy loading de rutas (code splitting) | `frontend/src/router/routes.ts` | Bundle analyzer muestra chunks por ruta |
| 25 | Capacitor setup para builds nativos (Android/iOS) | `frontend/capacitor.config.ts` (nuevo) | Build APK exitoso |
| 26 | Suite de tests frontend (mínimo: auth flow, sync, stores) | `frontend/src/**/*.spec.ts` | ≥30 tests pasando en CI |
| 27 | Tests E2E con Playwright (flujos críticos: login→sync→posting) | `e2e/` (nuevo) | Playwright en CI valida happy path completo |

### Bloque E — Kernels Funcionales

| # | Acción | Archivo(s) afectado(s) | Validación |
|:-:|:-------|:-----------------------|:-----------|
| 28 | Billing kernel: FSM (draft→validated→posted→cancelled), tax calc, numeración fiscal | `apps/kernels/facturacion/` | Factura transiciona estados correctamente, tax calculado, número secuencial |
| 29 | Inventory kernel: movements, FIFO/avg valuation, stock alerts | `apps/kernels/inventarios/` | Movimiento de stock actualiza balance, valuación correcta |
| 30 | Payments kernel: transaction lifecycle, reconciliación con billing | `apps/kernels/payments/` | Pago contra factura reduce saldo pendiente |
| 31 | Outbox pattern: tabla de eventos pendientes + worker que publica | `apps/modulos/common/outbox.py` (nuevo) | Evento emitido llega a consumidor, retry en fallo |
| 32 | CEC control plane: reconciliación automática billing↔accounting↔payments | `apps/modulos/cec/` | Discrepancia detectada genera alerta |

---

## 9. MÉTRICAS DE ÉXITO

| Métrica | Estado actual | Objetivo post-ejecución |
|:--------|:-------------|:-----------------------:|
| **Backup recovery** | No existe | Restore exitoso verificado semanalmente |
| **Race conditions protegidas** | 0 de 4 endpoints | 4 de 4 con `select_for_update` |
| **Test coverage backend (incl. views)** | ~85% (views excluidas) | ≥92% con views incluidas |
| **Test coverage frontend** | ~0% (1 archivo) | ≥60% (stores + services + flows) |
| **Sync clock skew** | 6 horas | 5 minutos |
| **Nonce table growth** | Ilimitada | Capped a 48h de retención |
| **P99 latency (sync batch)** | Sin medición | <400ms con throttle |
| **Error format consistency** | Parcial (~60% envelope) | 100% envelope |
| **Secrets en DB** | Plaintext Base64 | Cifrados con Fernet o migrados a v2 |
| **Mobile capability** | Solo web | PWA + APK funcional |
| **Kernel functionality** | Solo modelos | FSM + validaciones + workflows completos |
| **E2E test coverage** | 0 flujos | ≥5 flujos críticos automatizados |

---

## Referencias

- [ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md](ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md)
- [CONTRACT_PACK_v2.0.md](CONTRACT_PACK_v2.0.md)
- [ADDENDUM_SEGURIDAD_v1.1.md](ADDENDUM_SEGURIDAD_v1.1.md)
- [ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md](ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md)
- [QUALITY_COVERAGE_DIAGNOSTIC.md](QUALITY_COVERAGE_DIAGNOSTIC.md)
- [DIAGNOSTICO_SISTEMA_2026-03.md](DIAGNOSTICO_SISTEMA_2026-03.md)
