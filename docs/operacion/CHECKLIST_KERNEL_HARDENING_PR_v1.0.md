# Checklist de PR — Kernel Hardening v1.0

Version: v1.0  
Fecha: 2026-03-17  
Estado: Activo

Usar esta lista en todo PR de hardening backend-first.

## Contrato

- [ ] El PR declara qué kernel o bloque endurece.
- [ ] El ownership del dominio no cambia.
- [ ] El contrato o ADR relevante fue actualizado o referenciado.
- [ ] No se introduce Reportes ni Dashboard fuera de orden.

## Enforcement

- [ ] El cambio refuerza invariantes, scope, permisos, auditoría o envelope.
- [ ] No crea bypass silencioso.
- [ ] No introduce dual-write ni mutación indebida entre kernels.

## Tests

- [ ] Hay pruebas unitarias o de integración para el comportamiento endurecido.
- [ ] Hay prueba de regresión para el gap real que motivó el PR.
- [ ] Si aplica, se verifican `required_scope`, auditoría, outbox/inbox o determinismo.

## Evidencia mínima

- [ ] Se documenta comando de verificación ejecutado.
- [ ] Si aplica, se adjunta referencia a gate/runner/artefacto.
- [ ] El impacto sobre compat legacy queda explícito.

## Rollback

- [ ] El PR explica si el cambio es reversible sin migración.
- [ ] Si hay migración o constraint nueva, el rollback está descrito.
- [ ] Si toca contratos, el cambio de compatibilidad quedó explícito.
