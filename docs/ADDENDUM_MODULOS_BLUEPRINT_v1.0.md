# Blueprint obligatorio para modulos nuevos (v1.0)

## Objetivo

Asegurar que todo modulo nuevo sea seguro por defecto, auditable y consistente con RBAC y contexto organizacional.

## Reglas no negociables

1. **Autenticacion y permisos**
   - Toda API nueva usa `IsAuthenticated` y `rbac_permission("...")`.
   - Las vistas deben definir permisos por metodo cuando aplique.

2. **Scope organizacional**
   - Toda vista con acceso a datos usa `ScopedQuerysetMixin` o filtra por `request.company`/`request.branch`.
   - No se permiten consultas sin contexto salvo endpoints explicitamente exentos.

3. **Auditoria contractual**
   - Cada endpoint de escritura emite evento con `event_type` y `reason_code`.
   - Los payloads de auditoria deben evitar secretos y usar snapshots reducidos.

4. **Throttling y paginacion**
   - Todo endpoint define `throttle_scope`.
   - Listados deben paginar con los helpers comunes.

5. **Provision y seeds**
   - Recursos base (secuencias, bodegas, items o catálogos) se provisionan de forma explicita.
   - No se permite autocreacion silenciosa en operaciones de negocio.

6. **Pruebas minimas**
   - 403 sin permiso.
   - Bloqueo cross-company.
   - Bloqueo por `must_change_password`.
   - Evento de auditoria emitido.

## Referencias

- [backend/src/apps/common/permissions.py](../backend/src/apps/common/permissions.py)
- [backend/src/apps/common/mixins.py](../backend/src/apps/common/mixins.py)
- [backend/src/apps/audit/writer.py](../backend/src/apps/audit/writer.py)
