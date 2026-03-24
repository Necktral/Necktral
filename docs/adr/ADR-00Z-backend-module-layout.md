# ADR-00Z: Layout Canonico de Backend por Kernels Internos y Verticales

- Fecha: 2026-03-19
- Estado: Aceptado

## Contexto

Se ejecuto una reestructura fisica para separar kernels internos del backend Django y verticales de negocio en raiz.

## Decision

1. Kernels internos Django:
   - `backend/src/apps/modulos/*`
2. Verticales de dominio:
   - `kernels/*`
3. Excepcion transicional aprobada:
   - `backend/src/apps/modulos/ventas_retail` alojara `RETAIL` aunque semánticamente sea vertical.
   - No se moveran fisicamente `Fuel`, `Billing`, `Inventory` ni `Procurement` en esta iniciativa.
   - La clasificacion kernel/vertical se congela por ownership e invariantes, no solo por carpeta.
4. Namespace interno canonical:
   - `apps.modulos.*` para kernels internos
   - `kernels.*` para verticales
5. Prefijo publico canonical:
   - `/api/backend/*`
6. Prefijos legacy controlados por deprecacion temporal:
   - `/api/auth|iam|org|accounting|billing|inventory|procurement|fuel|retail/*`

## Consecuencias

- Claridad de ownership por modulo.
- Menos acoplamiento entre infraestructura base y verticales.
- Migraciones/middleware quedan concentrados en backend interno sin mover verticales.
- `RETAIL` puede evolucionar como vertical POS serio en `modulos` sin forzar una migracion fisica del resto del arbol.

## Riesgos

- Regresion por imports viejos (`apps.<kernel>` o `modulos.*` legacy).
- Referencias residuales en scripts y docs.

## Controles

- `qa/architecture_boundaries_guard.py`
- `qa/repo_hygiene_guard.py`
- `qa/simulation_contract_guard.py`
