# CODEX_OPERATING_BRIEF

## 0. Control del documento

Documento: `CODEX_OPERATING_BRIEF.md`
Proyecto: Necktral ERP/CRM/POS multiempresa
Estado: Protocolo operacional para Codex
Ultima actualizacion: 2026-05-27
Uso: orientar tareas Codex, handoffs, reviews y cortes tecnicos
Regla superior: este brief no reemplaza el Context Card ni autoriza implementaciones por si solo.

GitHub es evidencia tecnica, no objetivo. Codex ejecuta bajo direccion, no define roadmap ni producto.

## 1. Proposito

Este documento define como debe operar Codex dentro de Necktral. Su funcion es convertir el contexto rector en reglas practicas de ejecucion: que leer, como clasificar una tarea, cuando responder en modo ASK ONLY, cuando implementar, que validar, cuando detenerse y como reportar.

Relaciones:

- `NECKTRAL_CONTEXT_CARD.md` = memoria rectora de negocio, arquitectura, dominios y decisiones.
- `CODEX_OPERATING_BRIEF.md` = protocolo operativo para ejecutar tareas Codex sin drift.
- `NECKTRAL_MASTER_ROADMAP.md` = secuencia priorizada de objetivos, cuando exista.
- `NECKTRAL_DECISION_LOG.md` = registro de decisiones cerradas, cuando exista.

Este brief evita improvisacion. No convierte ningun roadmap en permiso para tocar codigo.

## 2. Lectura obligatoria

Antes de cualquier tarea Necktral, Codex debe leer o verificar:

1. `docs/project/NECKTRAL_CONTEXT_CARD.md`.
2. `docs/project/NECKTRAL_MASTER_ROADMAP.md`, si existe.
3. `docs/project/NECKTRAL_DECISION_LOG.md`, si existe.
4. El brief actual: `docs/project/CODEX_OPERATING_BRIEF.md`.
5. Archivos reales del repo relacionados con la tarea.
6. Tests existentes cercanos al dominio.
7. Migraciones existentes si el cambio toca modelos o persistencia.
8. Contratos de auditoria, outbox, eventos, API o reporting si aplica.

Si el documento rector y el codigo real no coinciden, el codigo real manda para diagnostico y el documento debe actualizarse o la discrepancia debe reportarse.

## 3. Regla GitHub

GitHub es evidencia tecnica, no objetivo del producto.

Codex puede usar ramas, commits, PRs, CI y logs como trazabilidad. No debe convertir abrir PR, cerrar issue o mover ramas en sustituto de resolver el problema real.

Un PR aceptable debe demostrar:

- scope claro;
- cambios permitidos;
- evidencia de lectura del repo;
- tests o razon explicita para no correrlos;
- impacto en datos/auditoria/eventos cuando aplique;
- ausencia de drift hacia dominios no autorizados.

## 4. Regla Codex

Codex ejecuta. No dirige roadmap.

Codex debe:

- inspeccionar antes de editar;
- separar hechos, hipotesis y decisiones;
- mantener cambios acotados por alcance, no por calidad;
- detenerse ante conflicto de dominio, datos o permisos;
- reportar estado real de branch, HEAD y worktree;
- proponer ASK ONLY antes de CODE cuando el dominio no este claro.

Codex no debe:

- inventar roadmap;
- inventar nomenclatura de negocio;
- decidir tratamiento fiscal;
- reemplazar al contador;
- imponer arquitectura no validada por el repo;
- abrir modulos dependientes sin corte base aprobado.

## 5. Modos de trabajo

### ASK ONLY / READ ONLY

Usar cuando la tarea pide auditoria, diagnostico, diseno, mapa, revision o decision.

Permitido:

- leer archivos;
- ejecutar busquedas;
- inspeccionar modelos, servicios, migraciones, tests y contratos;
- ejecutar comandos no mutantes;
- proponer arquitectura;
- clasificar riesgos;
- recomendar cortes.

Prohibido:

- editar archivos;
- crear migraciones;
- cambiar ramas de producto sin autorizacion;
- hacer commit;
- tocar frontend, Sync, backend o QA;
- implementar modelos, APIs, servicios o tests.

Salida esperada:

- repo state;
- archivos inspeccionados;
- hallazgos;
- riesgos C1/C2/C3;
- decision recomendada;
- prompt cerrado para Fixer Agent si aplica.

### CODE / FIXER

Usar solo cuando el corte esta aprobado y tiene archivos permitidos, archivos prohibidos, tests, QA y criterios de aceptacion.

Permitido:

- editar solo archivos autorizados;
- crear migraciones si el corte lo permite;
- agregar tests obligatorios;
- ejecutar QA definido;
- preparar commit/PR si se pidio.

Prohibido:

- ampliar scope;
- tocar dominios prohibidos;
- crear APIs no autorizadas;
- introducir backfill no aprobado;
- saltar tests por conveniencia;
- mezclar cambios no relacionados;
- usar SQLite como aprobacion fuerte de persistencia critica.

Salida esperada:

- cambios realizados;
- decisiones tecnicas;
- QA ejecutado;
- errores o bloqueos;
- riesgos restantes;
- estado listo/no listo para review.

### REVIEWER

Usar despues de un Fixer Agent o cuando ya existe un diff.

Debe revisar:

- scope;
- contratos;
- migraciones;
- auditoria;
- tests;
- QA;
- riesgos;
- compatibilidad;
- drift de dominio.

Decisiones permitidas:

- `APPROVE`
- `REQUEST_CHANGES`
- `CONDITIONALLY_ACCEPTED_BLOCKED_BY_ENVIRONMENT`
- `REVERT_RECOMMENDED`

## 6. Verificacion de repo y worktree

Antes de toda tarea:

```bash
git status -sb
git branch --show-current
git rev-parse HEAD
git diff --name-only
git ls-files --others --exclude-standard
```

Reglas:

- Si el worktree esta sucio, identificar si los cambios pertenecen al objetivo.
- Si hay cambios ajenos, no stagear ni revertir sin permiso.
- Si la tarea es docs-only, el diff debe limitarse a docs autorizados.
- Si la tarea toca modelos, revisar migraciones existentes antes de editar.
- Si la tarea toca dinero, stock, cartera, nomina o cierre, PostgreSQL real es gate fuerte.

## 7. Clasificacion C1 / C2 / C3

### C1 - Critico

Cambios que pueden romper dinero, datos, seguridad, auditoria, cierre, stock, cartera, nomina, permisos o integridad multiempresa.

Ejemplos:

- Payments, Accounting, CEC, Inventory, Billing fiscal.
- CxC, CxP, creditos, cartera, intereses, mora.
- Migraciones con datos existentes.
- Auditoria, outbox, idempotencia, Shadow Ledger.
- IAM, RBAC, scope company/branch.
- Sync, offline, seguridad y secretos.

Requiere:

- Auditor Agent previo si el dominio no esta claro;
- tests especificos;
- PostgreSQL real cuando haya persistencia;
- Reviewer Agent;
- no merge sin gates.

### C2 - Alto

Cambios de dominio relevante con impacto acotado pero recuperable.

Ejemplos:

- HR operacional sin nomina;
- Party master data;
- admin interno;
- reportes no contables;
- docs rectores que guian trabajo futuro.

Requiere:

- scope cerrado;
- tests cercanos si hay codigo;
- revision de blast radius;
- reporte de riesgos.

### C3 - Bajo

Cambios sin impacto runtime o con riesgo limitado.

Ejemplos:

- docs-only;
- comentarios;
- runbooks;
- ajustes de formato sin cambio de comportamiento.

Requiere:

- `git diff --check`;
- scope limpio;
- no backend tests salvo que el cambio lo justifique.

## 8. Invariantes para tareas C1

Toda tarea C1 debe declarar si aplica:

- `AuditEvent`;
- `OutboxEvent`;
- `EconomicEvent`;
- `JournalDraft`;
- idempotencia;
- scope `company`, `branch`, finca o `cost_center`;
- evidencia;
- CEC;
- revision contador;
- rollback;
- permisos/RBAC;
- compatibilidad API;
- migracion y reversibilidad razonable.

Si alguno no aplica, debe decirse explicitamente. Omitirlo sin explicacion es falla de review.

## 9. Stop conditions

Codex debe detenerse y reportar si:

- aparece un archivo fuera de scope;
- falta contexto de negocio para decidir;
- el repo no esta limpio y los cambios no fueron declarados;
- se requiere migracion no autorizada;
- se requiere frontend no autorizado;
- se requiere Sync no autorizado;
- se rompen contratos API, eventos, audit chain o reporting;
- una tarea toca dinero, stock, contabilidad, cartera, nomina o cierre sin tests;
- Codex necesita decidir negocio, fiscalidad o tratamiento contable;
- hay conflicto entre Context Card, roadmap, decision log y codigo real;
- PostgreSQL real no esta disponible para cambio de persistencia critica;
- la unica forma de compilar exige tocar dominios prohibidos;
- el usuario pidio ASK ONLY y el trabajo requiere modificar archivos.

En stop condition, no improvisar. Reportar causa, evidencia y decision requerida.

## 10. Prohibiciones permanentes

Codex no debe:

- crear roadmap nuevo sin decision explicita;
- inventar nombres de dominio cuando ya exista nomenclatura;
- convertir PR, issue o branch en objetivo principal;
- implementar CxC/CxP/Creditos sin Party/Counterparty aprobado;
- usar OrgUnit como Party;
- meter toda operacion en Accounting;
- hacer que CEC corrija datos primarios;
- saltar a microservicios sin senales objetivas;
- tocar Sync, frontend o migraciones sin autorizacion;
- mezclar ramas, worktrees o cambios de chats distintos;
- crear backfills destructivos sin plan aprobado;
- declarar aprobado un cambio persistente solo con SQLite;
- tocar settlement `TRANSFER` salvo regresion autorizada.

## 11. Formato de reporte

Todo cierre de tarea debe responder:

```text
A) Estado del repo
- branch
- HEAD
- worktree
- archivos modificados

B) Documentos leidos
- Context Card
- Roadmap / Decision Log si existen
- archivos reales del repo

C) Objetivo de producto
- que problema resuelve
- que queda fuera

D) Archivos inspeccionados
- rutas relevantes

E) Hallazgos
- hechos confirmados
- hipotesis
- brechas

F) Riesgos C1/C2/C3
- clasificacion
- mitigacion

G) Decision
- ASK ONLY / CODE / REVIEWER
- APPROVE / REQUEST_CHANGES si aplica

H) Archivos cambiados si aplica
- lista cerrada

I) Validacion
- comandos ejecutados
- resultado
- tests no ejecutados y motivo

J) Listo/no listo para commit
- estado final
- bloqueos
```

## 12. Plantilla para tarea ASK ONLY

```text
PROYECTO:
Necktral / ERP-CRM-POS Nicaragua

MODO:
ASK ONLY / READ ONLY

OBJETIVO:
[diagnosticar, auditar o proponer decision]

LECTURA OBLIGATORIA:
- docs/project/NECKTRAL_CONTEXT_CARD.md
- docs/project/CODEX_OPERATING_BRIEF.md
- [archivos del dominio]

BUSCAR:
[rg patterns requeridos]

RESPONDER:
A) Estado del repo
B) Documentos y archivos inspeccionados
C) Hallazgos
D) Riesgos C1/C2/C3
E) Decision recomendada
F) Prompt cerrado para Fixer Agent si aplica

RESTRICCIONES:
- no implementar
- no migraciones
- no commit
- no tocar dominios fuera de alcance
```

## 13. Plantilla para tarea CODE

```text
PROYECTO:
Necktral / ERP-CRM-POS Nicaragua

MODO:
CODE / FIXER

OBJETIVO:
[corte implementable cerrado]

ARCHIVOS PERMITIDOS:
- [rutas exactas]

ARCHIVOS PROHIBIDOS:
- [dominios fuera de alcance]

INVARIANTES:
- AuditEvent: [si/no + motivo]
- OutboxEvent: [si/no + motivo]
- EconomicEvent: [si/no + motivo]
- JournalDraft: [si/no + motivo]
- idempotencia: [si/no + clave]
- scope: [company/branch/finca/cost_center]
- evidencia: [si/no]
- CEC: [si/no]
- revision contador: [si/no]

CAMBIOS ESPERADOS:
- [lista cerrada]

TESTS:
- [tests obligatorios]

QA:
- [comandos exactos]

CRITERIOS DE ACEPTACION:
- [condiciones cerradas]

NON-GOALS:
- [lo que no se implementa]

STOP CONDITIONS:
- [condiciones especificas del corte]
```

## 14. Plantilla para Reviewer Agent

```text
PROYECTO:
Necktral / ERP-CRM-POS Nicaragua

MODO:
REVIEWER / READ ONLY

OBJETIVO:
Revisar el diff del corte [nombre].

GATES:
- scope
- modelo/datos
- migracion
- servicios/transacciones
- auditoria/eventos
- API si aplica
- permisos si aplica
- tests
- QA PostgreSQL si aplica
- no-goals

DECISION:
APPROVE / REQUEST_CHANGES / CONDITIONALLY_ACCEPTED_BLOCKED_BY_ENVIRONMENT / REVERT_RECOMMENDED

RESPONDER:
A) Checkpoint
B) Resultado de review
C) Hallazgos por gate
D) Riesgos C1/C2/C3
E) Cambios exigidos si aplica
F) Decision sobre siguiente corte
```

## 15. Uso con documentos rectores

Orden recomendado de documentos:

1. `NECKTRAL_CONTEXT_CARD.md` para entender el negocio y arquitectura.
2. `CODEX_OPERATING_BRIEF.md` para ejecutar sin drift.
3. `NECKTRAL_MASTER_ROADMAP.md` para priorizar, cuando exista.
4. `NECKTRAL_DECISION_LOG.md` para no reabrir decisiones, cuando exista.

Si falta roadmap o decision log, Codex debe decirlo y no inventarlo.

## 16. Cierre

Este brief es operativo. Debe mantenerse corto en comparacion con el Context Card, pero suficientemente estricto para evitar drift, scope creep, cambios sin review y ejecucion sin evidencia.

Todo corte futuro debe poder responder:

```text
Que se va a hacer.
Por que corresponde al roadmap.
Que archivos puede tocar.
Que invariantes protege.
Que tests lo prueban.
Que no esta permitido hacer.
Cuando debe detenerse.
```
