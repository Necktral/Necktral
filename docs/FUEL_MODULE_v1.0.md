# Módulo Fuel (Estación de Servicios) v1.0

Versión: v1.0  
Fecha: 2026-03-07  
Estado: **Norma operativa (viva)**

## ¿Qué es el módulo Fuel?

El módulo **Fuel** (`modulos.estacion_servicios`) gestiona la operación diaria de una estación de servicios (gasolinera). Cubre el ciclo completo: apertura de turno → registro de despachos de combustible → emisión de ventas → cierre de turno y reportes.

Es un módulo de dominio multi-empresa/multi-sucursal que se integra con los módulos de inventarios y facturación, y emite eventos al bus de auditoría contractual.

## Ruta base

```
/api/fuel/
```

## Conceptos principales

| Concepto | Descripción |
|---|---|
| **Turno** (`FuelShift`) | Periodo operativo de una sucursal. Solo puede haber un turno abierto por sucursal a la vez. |
| **Despacho** (`FuelDispense`) | Registro de combustible entregado (litros, precio, placa, bomba, etc.). Base de cualquier venta. |
| **Venta** (`FuelSale`) | Documento comercial asociado a un despacho: tipo (pública / interna / empleado), método de pago, cliente. |
| **Producto** | `DIESEL` o `GASOLINE`. |
| **UoM de volumen** | `LITER` (litros) o `GALLON` (galón US). El sistema normaliza todo a litros canónicos internamente. |
| **UoM de precio** | `PER_LITER` o `PER_GALLON`. Ídem, se normaliza a precio/litro para reportes. |

## Flujo operativo estándar

```
1. POST /api/fuel/shifts/open/                 → abre turno (status OPEN)
2. POST /api/fuel/dispenses/                   → registra despacho (vinculado al turno)
3. POST /api/fuel/sales/                       → crea venta sobre el despacho
4. POST /api/fuel/sales/<id>/cancel/           → anula venta (status CANCELLED)
5. POST /api/fuel/shifts/<id>/close/           → cierra turno (status CLOSED)
6. GET  /api/fuel/reports/shift-close/<id>/    → reporte de cierre de turno
7. GET  /api/fuel/reports/daily-close/?date=   → reporte de cierre diario
```

## Endpoints

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| `GET` | `/api/fuel/health/` | público | Health check del módulo |
| `POST` | `/api/fuel/shifts/open/` | `fuel.shift.open` | Abrir turno |
| `GET` | `/api/fuel/shifts/` | `fuel.shift.read` | Listar turnos |
| `GET` | `/api/fuel/shifts/<id>/` | `fuel.shift.read` | Detalle de turno |
| `POST` | `/api/fuel/shifts/<id>/close/` | `fuel.shift.close` | Cerrar turno |
| `GET` | `/api/fuel/dispenses/` | `fuel.dispense.read` | Listar despachos |
| `POST` | `/api/fuel/dispenses/` | `fuel.dispense.create` | Registrar despacho |
| `GET` | `/api/fuel/dispenses/<id>/` | `fuel.dispense.read` | Detalle de despacho |
| `GET` | `/api/fuel/sales/` | `fuel.sale.read` | Listar ventas |
| `POST` | `/api/fuel/sales/` | `fuel.sale.create` | Crear venta |
| `GET` | `/api/fuel/sales/<id>/` | `fuel.sale.read` | Detalle de venta |
| `POST` | `/api/fuel/sales/<id>/cancel/` | `fuel.sale.void` | Anular venta |
| `GET/PUT` | `/api/fuel/uom-preferences/` | `fuel.uom_preferences.manage` | Preferencias de UoM por usuario/sucursal |
| `GET` | `/api/fuel/reports/shift-close/<id>/` | `fuel.reports.view` | Reporte de cierre de turno |
| `GET` | `/api/fuel/reports/daily-close/` | `fuel.reports.view` | Reporte de cierre diario |

## RBAC — Roles y permisos

### Roles predefinidos

| Rol | Descripción |
|---|---|
| `fuel_manager` | Acceso completo al módulo |
| `fuel_supervisor` | Igual que manager (alias operativo) |
| `fuel_cashier` | Operación diaria: turno, despachos y ventas |
| `fuel_auditor` | Solo lectura de todo el módulo |

### Permisos disponibles

```
fuel.shift.open         fuel.shift.close        fuel.shift.read
fuel.dispense.create    fuel.dispense.read      fuel.dispense.void
fuel.sale.create        fuel.sale.read          fuel.sale.void
fuel.price.read         fuel.price.update
fuel.tank.read          fuel.tank.receive       fuel.tank.adjust
fuel.reconcile.view     fuel.reconcile.post
fuel.outbox.read        fuel.outbox.reprocess
fuel.reports.view       fuel.reports.export
fuel.config.read
fuel.uom_preferences.manage
```

## Auditoría contractual

- `module = FUEL`
- **event_type** permitidos:

| Event type | Cuándo |
|---|---|
| `FUEL_SHIFT_OPENED` | Apertura de turno |
| `FUEL_SHIFT_CLOSED` | Cierre de turno |
| `FUEL_DISPENSE_RECORDED` | Registro de despacho |
| `FUEL_DISPENSE_VOIDED` | Anulación de despacho |
| `FUEL_SALE_CREATED` | Creación de venta |
| `FUEL_SALE_VOIDED` | Anulación de venta |
| `FUEL_PRICE_SET` | Actualización de precio |
| `FUEL_TANK_RECEIPT_POSTED` | Recepción de combustible en tanque |
| `FUEL_TANK_ADJUSTMENT_POSTED` | Ajuste de tanque |
| `FUEL_RECONCILIATION_POSTED` | Conciliación posteada |
| `FUEL_INTERCOMPANY_OUTBOX_ENQUEUED` | Intercompany encolado |
| `FUEL_INTERCOMPANY_OUTBOX_APPLIED` | Intercompany aplicado |
| `FUEL_INTERCOMPANY_OUTBOX_FAILED` | Intercompany fallido |

- **reason_code**: `FUEL_OK`
- **subject_type**: `FUEL_SHIFT`, `FUEL_DISPENSE`, `FUEL_SALE`, `FUEL_TANK`, `FUEL_PRICE`, `FUEL_OUTBOX`, `FUEL_LIQUIDATION`

## Integración con otros módulos

| Módulo | Integración |
|---|---|
| **Inventarios** | Al cerrar una venta, se crea un `StockMovement` de salida (consumo). Al anular, se genera movimiento de reversa. Los tanques se modelan como almacén `code="FUEL"`. |
| **Facturación** | `FuelSale` tiene `billing_doc` FK preparado para integración con `BillingDocument`. |
| **RBAC** | Todos los endpoints usan el sistema de permisos `rbac_permission(...)`. |
| **Auditoría** | Todos los eventos se emiten via `write_event(...)` al bus de auditoría. |

## Decisiones de diseño

- **Litros canónicos:** toda la aritmética interna usa litros. `volume_entered` + `volume_uom` preservan lo que el operador capturó.
- **Precio canónico por litro:** igual para precio. `unit_price_entered` + `unit_price_uom` preservan el dato operativo.
- **Un solo turno abierto por sucursal:** constraint de base de datos (`UNIQUE` parcial con `status=OPEN`).
- **UoM configurable:** el operador puede operar en litros o galones; el sistema convierte y persiste ambos valores.
