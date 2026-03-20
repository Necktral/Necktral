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
3. Namespace interno canonical:
   - `apps.modulos.*` para kernels internos
   - `kernels.*` para verticales
4. Prefijo publico canonical:
   - `/api/backend/*`
5. Prefijos legacy controlados por deprecacion temporal:
   - `/api/auth|iam|org|accounting|billing|inventory|procurement|fuel/*`

## Consecuencias

- Claridad de ownership por modulo.
- Menos acoplamiento entre infraestructura base y verticales.
- Migraciones/middleware quedan concentrados en backend interno sin mover verticales.

## Riesgos

- Regresion por imports viejos (`apps.<kernel>` o `modulos.*` legacy).
- Referencias residuales en scripts y docs.

## Controles

- `qa/architecture_boundaries_guard.py`
- `qa/repo_hygiene_guard.py`
- `qa/simulation_contract_guard.py`

