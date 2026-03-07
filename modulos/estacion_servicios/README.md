# Módulo Fuel — Estación de Servicios

Módulo de dominio para la gestión operativa de estaciones de servicios (gasolineras).

## Responsabilidad

Gestiona el ciclo completo de operación: apertura de turno → despachos de combustible → ventas → cierre de turno → reportes.

## Ruta API

```
/api/fuel/
```

## Documentación completa

Ver [`docs/FUEL_MODULE_v1.0.md`](../../docs/FUEL_MODULE_v1.0.md).

## Modelos principales

- `FuelShift` — turno operativo (un único turno abierto por sucursal a la vez)
- `FuelDispense` — despacho de combustible (litros, precio, bomba, placa)
- `FuelSale` — venta sobre un despacho (tipo, método de pago, cliente)
- `FuelUoMPreference` — preferencia de unidad de medida por usuario/sucursal

## Integración

- **Inventarios:** movimientos de stock al crear/anular ventas.
- **Facturación:** FK preparado para `BillingDocument`.
- **RBAC:** permisos `fuel.*`.
- **Auditoría:** eventos `FUEL_*` emitidos al bus de auditoría.
