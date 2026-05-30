# Copilot Coding Agent — Funcionalidad y Uso

> Versión 1.0 — 2026-05-27

## ¿Qué es crear un agente?

Crear un **Copilot Coding Agent** (agente de codificación) significa asignar una tarea autónoma a un agente de IA que opera directamente sobre el repositorio. El agente trabaja en un entorno aislado (sandbox), realiza cambios de código, ejecuta pruebas y abre o actualiza un Pull Request sin intervención manual continua.

---

## Funcionalidades principales

| Capacidad | Descripción |
|-----------|-------------|
| **Resolución autónoma de issues** | Se asigna un issue de GitHub al agente y este implementa la solución completa. |
| **Exploración del código** | Lee, busca y analiza el repositorio para entender la arquitectura antes de modificar. |
| **Edición precisa de archivos** | Realiza cambios quirúrgicos (mínimos y focalizados) en los archivos relevantes. |
| **Ejecución de comandos** | Corre linters, builds, tests y scripts existentes para validar sus cambios. |
| **Creación de tests** | Genera pruebas unitarias/integración consistentes con la infraestructura existente. |
| **Gestión de Pull Requests** | Crea commits, actualiza la descripción del PR y reporta progreso con checklists. |
| **Investigación web** | Busca documentación externa cuando necesita información actualizada. |
| **Interacción con GitHub Actions** | Consulta workflows, logs de CI y resultados de jobs para diagnosticar fallos. |

---

## Flujo típico de trabajo

```
1. Se crea un issue o se asigna al agente
2. El agente clona el repositorio en un sandbox aislado
3. Explora la estructura y entiende el contexto
4. Planifica los cambios mínimos necesarios (checklist)
5. Implementa los cambios de forma incremental
6. Ejecuta linters/tests para validar
7. Hace commit y push al PR
8. Reporta progreso y solicita revisión
```

---

## Casos de uso en Necktral

- **Corrección de bugs**: El agente localiza el origen del error, implementa el fix y verifica con tests.
- **Nuevas funcionalidades**: Implementa features siguiendo la arquitectura existente (kernels, módulos, contratos).
- **Documentación**: Crea o actualiza docs técnicos y operacionales.
- **Refactoring**: Aplica cambios estructurales manteniendo compatibilidad.
- **Seguridad**: Corrige vulnerabilidades detectadas por CodeQL o auditorías.
- **CI/CD**: Diagnostica y repara fallos en workflows de GitHub Actions.

---

## Limitaciones

| Limitación | Detalle |
|------------|---------|
| No accede a secretos | No puede leer credenciales ni variables de entorno reales. |
| No despliega a producción | Solo modifica código y abre PRs; el deploy requiere aprobación humana. |
| Sandbox aislado | No persiste estado entre sesiones; cada tarea es independiente. |
| No modifica otros repos | Solo opera en el repositorio asignado. |
| Requiere revisión humana | Los cambios deben ser revisados y aprobados antes de merge. |

---

## Configuración en el repositorio

Para personalizar el entorno del agente, se puede crear un archivo `.github/copilot-setup-steps.yml` que define:

- Dependencias a preinstalar (apt, pip, npm, etc.)
- Variables de entorno del sandbox
- Comandos de setup previos a la ejecución

### Ejemplo básico

```yaml
# .github/copilot-setup-steps.yml
steps:
  - name: Instalar dependencias Python
    run: pip install -r requirements/dev.txt
  - name: Instalar dependencias frontend
    run: cd frontend && npm ci
```

---

## Relación con el flujo de desarrollo Necktral

El agente cloud opera como **Frente 1** de la estrategia de ejecución de 3 frentes (ver `docs/project/EXECUTION_FRONTS_STRATEGY.md`):

- **Frente 1 (Cloud Agent)**: Implementa lógica, bloques de código, contratos API y documentación.
- **Frente 2 (Codex Local)**: Ejecuta tests con PostgreSQL real y valida persistencia.
- **Frente 3 (Frontend)**: Conecta APIs certificadas — fase posterior.

El agente respeta las convenciones del repositorio:

- **Idioma**: Documentación y commits en español.
- **Arquitectura**: Sigue la topología de kernels y módulos definida en `docs/ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md`.
- **QA Gates**: Sus cambios pasan por los mismos CI/CD gates (`qa-ci.yml`, `security-ci.yml`).
- **Contratos**: Respeta los contratos operativos documentados en `docs/CONTRACT_PACK_*.md`.
- **Gobernanza**: Se adhiere a las reglas de `docs/operacion/CODEX_GOVERNANCE_HANDOFF_v1.0.md`.

---

## Seguridad

- El agente opera en un entorno efímero sin acceso a datos de producción.
- No puede introducir secretos en el código (verificado por `gitleaks` en CI).
- Los cambios pasan por CodeQL Security Scan antes de merge.
- El modelo de auditoría (`AuditEvent`) registra contexto de dispositivo/sesión, no del agente de IA.

---

## Referencias

- [GitHub Docs — Copilot Coding Agent](https://docs.github.com/en/copilot/using-github-copilot/using-copilot-coding-agent)
- [CONTRACT_PACK_v1.0.md](CONTRACT_PACK_v1.0.md)
- [CODEX_GOVERNANCE_HANDOFF_v1.0.md](operacion/CODEX_GOVERNANCE_HANDOFF_v1.0.md)
