# Retail POS v1.1 — Guía Operativa (Caja)

## Alcance

Esta guía cubre operación de mostrador para `Retail POS v1.1` en modo `online-first` con cola local de reintentos.

## Flujo base de venta

1. Confirmar `CashSession OPEN` en la sucursal.
2. Crear/usar ticket activo.
3. Agregar líneas por búsqueda o scanner.
4. Ejecutar `preview` y validar bloqueos.
5. Ejecutar `commit` (cash-first).
6. Verificar cierre en ticket + emisión documental.

## Scanner / barcode mode

- `Scanner ON` captura stream teclado (wedge) y agrega ítems por `barcode`.
- El scanner no secuestra escritura manual dentro de inputs editables.
- Mientras scanner está capturando, se suspenden shortcuts globales POS (excepto `Esc`).

## Cola local de reintentos

- Aplica a mutaciones: `checkout_commit`, `void`, `return`.
- Se encola solo en errores transitorios (red/timeout/5xx o `retryable=true`).
- No se encola en conflictos operativos `409` ni en validaciones de negocio no reintentables.
- Procesa FIFO en `online`, por botón manual `Flush cola`, y por intervalo periódico.

### Estados

- `PENDING`: pendiente de primer envío.
- `RETRYING`: con reintento programado (backoff).
- `FAILED`: requiere intervención operativa.
- `DONE`: completado, elegible para purge local.

## Recovery operativo

### Conflicto 409 de versión

- Recargar ticket.
- Reintentar operación con estado actualizado.

### Checkout en progreso

- Esperar confirmación del intento previo.
- Evitar disparar nuevo commit paralelo.

### Idempotency mismatch

- No reusar llave con payload distinto.
- Reintentar desde cola o generar nueva operación limpia.

### Sin caja abierta

- Abrir `CashSession` en sucursal.
- Reintentar `commit`/`return`.

## Observabilidad mínima

Se registran intentos POS con:

- `action`, `outcome`, `latency_ms`,
- `retryable`, `replayed`,
- `error_code`, `correlation_id`.

Esto permite diagnóstico rápido de fallas transitorias y replays idempotentes.
