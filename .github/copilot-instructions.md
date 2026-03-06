---
applyTo: "**"
---

## Politica de trabajo (Espanol + IA de ultima generacion)

### 1) Idioma y comunicacion

- Toda la comunicacion del proyecto (issues, PRs, commits, documentacion y discusiones tecnicas) sera en espanol.
- Si se cita material externo en otro idioma, se agrega un resumen en espanol.

### 2) Principios de ingenieria (calidad y evidencia)

- No se aceptan cambios basados en suposiciones: antes de proponer o modificar, se debe revisar el codigo real del repositorio y confirmar rutas/archivos/implementacion.
- Cada cambio debe declarar:
  - objetivo,
  - alcance,
  - riesgo,
  - impacto (seguridad, rendimiento, compatibilidad),
  - y criterios de aceptacion verificables.

### 3) Estandar de verificacion (tests + regresion)

- Ningun cambio se considera terminado sin verificacion:
  - pruebas unitarias y/o integracion segun corresponda,
  - y, cuando aplique, pruebas de permisos/seguridad (RBAC, multitenancy, auditoria).
- Se prohibe "arreglar rompiendo": si un cambio reduce cobertura o introduce deuda, debe justificarse y planificarse su cierre.
- Analisis avanzado (ejemplos):
  - `pytest -vv --durations=0`
  - `pytest -q --disable-warnings`
  - `pytest path/a/test_file.py::test_case`

### 4) Seguridad y cumplimiento (por defecto)

- Prohibido registrar secretos o credenciales en el repositorio (incluye ejemplos inseguros).
- Toda funcionalidad nueva debe respetar "secure-by-default":
  - autenticacion y autorizacion explicitas,
  - validacion de entrada,
  - minimos privilegios,
  - auditoria en operaciones sensibles,
  - y control de abuso (rate limiting) cuando aplique.

### 5) Documentacion viva

- La documentacion es parte del deliverable:
  - README, guias operativas, diagramas y decisiones tecnicas relevantes (ADR) deben mantenerse actualizados.
- Cambios que alteren contratos (API, roles/permisos, flujo de datos) requieren actualizacion documental en el mismo PR.

### 6) Colaboracion con IA (uso responsable y trazable)

- ChatGPT se usa como asistente: propone, explica y acelera; la autoridad final es el repositorio y las pruebas.
- Toda salida de IA debe ser revisada por un humano antes de fusionar.
- Cuando la IA sugiera cambios, se exige trazabilidad:
  - referencia al archivo/funcion afectada,
  - motivo del cambio,
  - y verificacion asociada (tests, comprobacion manual o metricas).

### 7) Disciplina de cambios (PRs y commits)

- PRs pequenos y revisables; preferir cambios incrementales con impacto controlado.
- Mensajes de commit claros y descriptivos (que y por que), evitando mensajes genericos.

Trabajamos con ChatGPT de forma justa.

### 8) Registro de decisiones (ADR) y trazabilidad operativa

- Toda decision arquitectonica o de seguridad relevante se registra como ADR breve (fecha, contexto, decision, consecuencias).
- Se prefiere evidencia cuantificable cuando sea posible (logs, metricas, benchmarks, resultados de tests).

### 9) Estabilidad futura

- Verificar rendimiento y estabilidad en cambios con impacto de datos o flujos criticos.
- Confirmar compatibilidad entre modulos cuando se alteren contratos o permisos compartidos.
- Evitar acoplamientos ocultos: documentar dependencias y efectos colaterales.
- Analisis avanzado (ejemplos):
  - `pytest -vv --durations=0`
  - `pytest -q --disable-warnings`
  - `pytest path/a/test_file.py::test_case`

Checklist breve para integracion y estabilidad (para PRs):

- Identificar modulos y contratos afectados.
- Ejecutar pruebas relevantes y capturar evidencia (salida o metricas).
- Revisar regresiones de rendimiento con duraciones de tests.
- Validar compatibilidad entre modulos (RBAC, auditoria, datos compartidos).
- Documentar efectos colaterales y acciones de mitigacion.
