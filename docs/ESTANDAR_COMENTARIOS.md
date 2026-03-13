# Estándar de comentarios (precedente)

Este documento define **cómo** y **dónde** comentar código en este repositorio.
La meta es que los comentarios sirvan como **contrato vivo** del sistema (seguridad, contexto, invariantes, auditoría), sin duplicar lo obvio.

## Principios

1. **En español** y con términos del dominio (empresa/sucursal, RBAC, auditoría, sync, etc.).
2. **Descriptivo, no redundante**: no explicar lo que el código ya dice; explicar lo que el código **no puede decir** fácilmente.
3. **Cerca del punto crítico**: el comentario debe vivir en el lugar donde la decisión se aplica.
4. **Contrato + motivo + consecuencias**: cuando el código impone una regla, documentar:
   - qué se espera (contrato),
   - por qué existe la regla,
   - qué pasa si no se cumple.
5. **Seguridad/consistencia primero**: priorizar comentarios en validaciones, autorización, multiempresa, firma/cripto, idempotencia, auditoría.

## Dónde comentar (prioridad)

- **Middlewares/Auth**: headers requeridos, inyección de contexto, reglas de “data scope”, errores esperados.
- **RBAC**: scopes, permisos efectivos, por qué se marca metadata en request para auditoría.
- **Auditoría**: qué se firma/hashea, partición de cadena, propiedades de integridad.
- **Sync/offline**: mensaje firmado, canonicalización, idempotencia, semántica de estados (APPLIED/DUPLICATE/REJECTED).
- **Services de dominio**: invariantes transaccionales y semántica de campos (ej. litros canónicos vs volumen ingresado).
- **Serializers/DTOs**: contrato API y normalización (por ejemplo, precisiones/rounding).

## Formatos recomendados

### 1) Comentario “Contrato del endpoint/servicio” (bloque corto)

Usar cuando el método tiene un contrato no trivial.

Ejemplo:

- Contrato:
  - Entrada aceptada: …
  - Normalización: …
- Invariantes:
  - …
- Auditoría:
  - …

### 2) Comentario “Regla fuerte” (una sola línea)

Usar cuando hay una condición que evita un bug de seguridad o data corruption.

Ejemplo: “Regla fuerte: no permitir X porque …”

### 3) Docstring de función/clase (cuando aplica)

Debe responder:

- Qué hace
- Qué asume (precondiciones)
- Qué garantiza (postcondiciones)

## Anti-patrones (evitar)

- Comentar cada línea.
- Comentarios que repiten nombres de variables.
- Comentarios desactualizables (números mágicos sin explicar motivo).

## Checklist antes de merge

- ¿El comentario explica una decisión, no una obviedad?
- ¿Está en español y es legible?
- ¿Está cerca del código que implementa la regla?
- ¿Aclara seguridad/consistencia/auditoría si corresponde?

## Política mínima auditable (módulos críticos)

Para validaciones de release se aplica una auditoría reproducible (`qa/repo_comment_audit.py`) con estos mínimos:

1. **Repositorio actualizado (criterio operativo):**
   - La rama local debe estar en sync con `origin/<rama>` (sin cambios locales y sin ahead/behind).
   - La brecha contra `upstream/master` se reporta como informativa.
2. **Docstrings obligatorias en superficies públicas críticas:**
   - Vistas/servicios/comandos públicos definidos como críticos por la auditoría.
   - Deben documentar contrato, precondiciones e invariantes relevantes.
3. **Comentarios obligatorios en reglas no obvias:**
   - Gates, idempotencia, reconciliación y decisiones de consistencia/auditoría.
4. **Exclusiones de cómputo:**
   - `node_modules`, `dist`, `.quasar`, artefactos generados y migraciones.
