# NECKTRAL_DECISION_LOG

## 0. Control del documento

Documento: `NECKTRAL_DECISION_LOG.md`
Proyecto: Necktral ERP/CRM/POS multiempresa
Estado: Registro rector vivo
Ultima actualizacion: 2026-05-27
Uso: registrar decisiones de producto, arquitectura, gobernanza y ejecucion Codex
Regla superior: este Decision Log no autoriza implementaciones por si solo; registra decisiones que deben guiar cortes futuros.

Fuentes rectoras:

- `docs/project/NECKTRAL_CONTEXT_CARD.md`
- `docs/project/CODEX_OPERATING_BRIEF.md`
- `docs/project/NECKTRAL_MASTER_ROADMAP.md`

GitHub es evidencia tecnica, no objetivo. Codex ejecuta bajo direccion, no dirige roadmap.

## 1. Proposito

Este documento evita que Necktral reabra decisiones ya tomadas o cambie direccion por saturacion de chats. Debe registrar decisiones cerradas, decisiones pendientes y condiciones para cambiar una decision.

El Decision Log responde:

- que se decidio;
- por que se decidio;
- que evidencia lo respalda;
- que queda bloqueado o permitido;
- que no se debe interpretar como permiso automatico;
- cuando debe revisarse.

## 2. Formato estandar de decision

Cada decision nueva debe usar esta plantilla:

```text
## DL-YYYYMMDD-NNN - Titulo

Estado:
Propuesta | Aprobada | Reemplazada | Rechazada | Pendiente

Fecha:
YYYY-MM-DD

Decision:
[texto breve]

Contexto:
[hechos, PRs, QA, repo, negocio]

Razon:
[por que es la decision correcta]

Impacto:
- datos
- auditoria
- Shadow Ledger
- CEC
- contador
- Codex

Permite:
[que queda permitido]

Bloquea:
[que queda prohibido o pendiente]

Evidencia:
[PR, commit, documento, QA, reunion]

Revisar si:
[condiciones de cambio]
```

## 3. Decisiones aprobadas

## DL-20260527-001 - Paquete rector de documentos en master

Estado: Aprobada

Fecha: 2026-05-27

Decision: Necktral debe mantener un paquete rector persistido en `docs/project/` compuesto por Context Card, Codex Operating Brief y Master Roadmap.

Contexto: PR #95 fue reconstruido desde `origin/master` y mergeado como docs-only. El PR #92 quedo reemplazado porque su rama estaba contaminada contra `master` con cambios backend Party/Counterparty.

Razon: El proyecto necesita memoria operacional, protocolo Codex y roadmap de plataforma para evitar drift entre chats, ramas y frentes.

Impacto:

- Datos: ninguno runtime.
- Auditoria: fija reglas de gobernanza para cambios C1.
- Shadow Ledger: fija que cambios economicos futuros declaren impacto.
- CEC: fija que cierre/evidencia sean parte del roadmap.
- Contador: fija que Necktral produce evidencia y paquetes, no contabilidad formal.
- Codex: exige leer documentos rectores antes de nuevos cortes.

Permite:

- Usar los documentos rectores como fuente de direccion.
- Crear futuros documentos complementarios como ADR, Risk Register y Backlog Register.

Bloquea:

- Iniciar cortes amplios sin leer documentos rectores.
- Tratar GitHub como objetivo del producto.

Evidencia:

- PR #95 mergeado.
- Commit `2f658893 docs(project): add Necktral operating system docs`.
- Merge commit `e2fa3f82`.

Revisar si: el roadmap cambia por decision formal o el codigo real contradice el contexto rector.

## DL-20260527-002 - GitHub es evidencia, no objetivo

Estado: Aprobada

Fecha: 2026-05-27

Decision: PRs, issues, commits y checks son evidencia tecnica. No son el objetivo central de Necktral.

Contexto: El trabajo previo mostro riesgo de confundir cierre de PR con avance real de producto.

Razon: El objetivo es construir una plataforma operacional robusta. GitHub ayuda a probar trazabilidad, no reemplaza decisiones de negocio ni arquitectura.

Impacto:

- Codex debe reportar PR/commit como evidencia.
- El Controller decide cortes por valor de producto, no por facilidad de PR.

Permite: usar GitHub para auditoria, CI, review y trazabilidad.

Bloquea: abrir PRs como sustituto de resolver dominio, datos o QA.

Evidencia: Context Card, Codex Operating Brief, Master Roadmap y PR #95.

Revisar si: se adopta otro sistema de trazabilidad formal.

## DL-20260527-003 - Codex ejecuta, no dirige roadmap

Estado: Aprobada

Fecha: 2026-05-27

Decision: Codex actua como ejecutor tecnico bajo direccion de Controller. No decide roadmap, fiscalidad, negocio ni arquitectura final.

Contexto: Necktral requiere coordinacion entre producto, contador, ingenieros, RRHH, finanzas, flota y operacion.

Razon: Muchas decisiones dependen de negocio real y expertos. Codex debe leer, auditar, implementar cortes aprobados y revisar, no improvisar direccion.

Impacto:

- Codex debe usar ASK ONLY cuando el dominio no esta claro.
- Codex debe detenerse ante stop conditions.
- Codex debe reportar hechos vs hipotesis.

Permite: Controller -> Auditor Agent -> Fixer Agent -> Reviewer Agent.

Bloquea: implementaciones automaticas por lectura superficial del roadmap.

Evidencia: `CODEX_OPERATING_BRIEF.md`.

Revisar si: se instala un skill/agente rector formal con reglas mas estrictas.

## DL-20260527-004 - Roadmap no autoriza implementacion automatica

Estado: Aprobada

Fecha: 2026-05-27

Decision: `NECKTRAL_MASTER_ROADMAP.md` define direccion y programas, pero no autoriza crear modelos, APIs, migraciones ni integraciones sin corte aprobado.

Contexto: El roadmap contiene programas amplios: Party, Portfolio, Payments, Billing, Supply Chain, Workforce, Work Planning, Fleet, CEC y Platform Hardening.

Razon: Un roadmap amplio puede inducir scope creep si se interpreta como backlog ejecutable directo.

Impacto:

- Todo corte futuro requiere objetivo, scope, archivos permitidos/prohibidos, invariantes, tests, QA y review.
- Los programas se transforman en cortes pequenos y revisables.

Permite: usar el roadmap para priorizar y mapear dependencias.

Bloquea: implementar varios programas a la vez.

Evidencia: `NECKTRAL_MASTER_ROADMAP.md`.

Revisar si: se formaliza un backlog ejecutable separado.

## DL-20260527-005 - Party/Counterparty es prerequisito para cartera

Estado: Aprobada

Fecha: 2026-05-27

Decision: Party/Counterparty es prerequisito para CxC, CxP y Creditos.

Contexto: Auditoria previa confirmo que Billing/Fuel/POS/Compras usaban snapshots textuales y no existian clientes/proveedores fuertes antes del Corte 1.

Razon: Saldos financieros no deben asociarse a texto, nombres sueltos ni OrgUnit.

Impacto:

- Financial Portfolio debe operar sobre Party.
- Customer/Supplier/Employee/Producer/Declarant deben derivar de Party o roles sobre Party.
- CEC debe bloquear operaciones financieras sin contraparte cuando aplique.

Permite: adaptar HR, Billing, Compras y cartera hacia Party por cortes.

Bloquea: crear CxC/CxP/Creditos sobre `customer_name`, `supplier_name` o `OrgUnit`.

Evidencia:

- Corte 1 Party/Counterparty aprobado.
- `NECKTRAL_CONTEXT_CARD.md`.
- `NECKTRAL_MASTER_ROADMAP.md`.

Revisar si: aparece un modelo canonico superior ya existente en repo o se redefine el bounded context de Party.

## DL-20260527-006 - Financiamiento es kernel financiero

Estado: Aprobada

Fecha: 2026-05-27

Decision: Financiamiento, creditos, CxC y CxP pertenecen al Financial Portfolio Kernel; no son modulo secundario ni payment method.

Contexto: Necktral necesita soportar microfinanciera o funcion fuerte de financiamiento, creditos otorgados y recibidos, intereses, mora, pagos aplicados y reportes contador.

Razon: Credito financiero crea obligaciones, vencimientos, intereses y riesgo. No equivale a tender `CREDIT`.

Impacto:

- Payments aplica pagos; no inventa deuda.
- Billing emite documentos; no posee saldos.
- Accounting consume hechos; no posee cartera.
- Portfolio debe emitir eventos economicos cuando aplique.

Permite: disenar Obligation, Receivable, Payable, CreditFacility y PaymentAllocation.

Bloquea: mezclar credito financiero con `payment_method=CREDIT`.

Evidencia: Context Card y Master Roadmap.

Revisar si: contador/finanzas definen reglas que requieren separar sub-kernels.

## DL-20260527-007 - Verticales productivos no reemplazan kernels

Estado: Aprobada

Fecha: 2026-05-27

Decision: Hacienda, ganado, flota, maquinaria, agroquimicos y work planning son verticales/operaciones que consumen kernels; no reemplazan identidad, cartera, pagos, inventario ni contabilidad.

Contexto: Necktral debe soportar fincas de cafe, ganado, flota, mantenimiento, agroquimicos, transporte y labores productivas.

Razon: Si un vertical posee cartera, pagos, inventario o contabilidad final, rompe ownership y cierre.

Impacto:

- Work Planning posee planes/tareas, no inventario ni pagos.
- Fleet posee activos/mantenimiento, no compras ni contabilidad.
- Hacienda/Ganado consumen HR, Inventory, Fleet, Portfolio, CEC y Accounting projection.

Permite: crear verticales despues de kernels base y personalization gates.

Bloquea: implementar cafe/finca como modulo aislado antes de Party, cartera, HR, cost objects y contador.

Evidencia: Context Card y Master Roadmap.

Revisar si: un vertical demuestra necesidad real de bounded context nuevo con ownership propio.

## DL-20260527-008 - Contador lleva contabilidad formal

Estado: Aprobada

Fecha: 2026-05-27

Decision: El contador certificado lleva la contabilidad formal. Necktral produce evidencia, cierres, reportes, soporte operacional y Shadow Ledger auxiliar.

Contexto: El negocio necesita reportes fiscales, paquetes por RUC/persona/proveedor/cliente/finca, revisiones y reclasificaciones.

Razon: Necktral debe ordenar operaciones y pre-asientos, pero no sustituye juicio profesional ni contabilidad oficial.

Impacto:

- Accounting/Shadow Ledger proyecta hechos economicos.
- CEC produce paquetes y excepciones.
- AccountantPackage debe ser revisable.

Permite: crear reportes, evidence packages y review status.

Bloquea: vender o disenar Necktral como reemplazo total del contador.

Evidencia: Context Card y Master Roadmap.

Revisar si: contador certificado aprueba nuevas responsabilidades formales del sistema.

## 4. Decisiones pendientes

Las siguientes decisiones estan pendientes y no autorizan implementacion directa:

- Tax/RUC profile: estructura final para RUC, declarantes, limites y reportes fiscales.
- Financial Portfolio: modelo final de Obligation, Receivable, Payable, CreditAgreement e InterestAccrual.
- Customer/Supplier migration: estrategia para mover snapshots textuales hacia Party.
- Cost Backbone: modelo canonico para finca, zona, labor, activo, trabajador y periodo.
- Work Planning: catalogo tecnico de labores, zonas, calendarios e indicadores.
- Payroll/Attendance: reglas de jornada, temporales, adelantos, deducciones y pagos.
- Fleet/Maintenance: odometro, horometro, planes, repuestos, combustible y costeo.
- CEC Accountant Package: formato exacto de paquetes, estados de revision y bloqueos.
- Sync/offline economic invariants: reglas para operaciones economicas offline.

## 5. Reglas de mantenimiento

- Cada decision nueva debe agregarse con identificador `DL-YYYYMMDD-NNN`.
- Una decision aprobada no se borra; se marca como `Reemplazada` si cambia.
- Las decisiones deben citar evidencia: PR, commit, QA, documento, reunion o auditoria.
- Si una decision depende de contador, ingenieros, RRHH, flota, finanzas u operacion, debe quedar como pendiente hasta validacion.
- Si el codigo real contradice este log, se debe abrir Auditor Agent antes de implementar.
- Este log debe actualizarse cuando se cierre un programa rector, se cambie un kernel o se desbloquee un corte C1.

## 6. Regla de uso para Codex

Codex debe leer este log junto con Context Card, Operating Brief y Master Roadmap antes de tareas amplias.

Codex no debe usar este log para implementar automaticamente. Debe usarlo para:

- no reabrir decisiones cerradas;
- detectar decisiones pendientes;
- declarar impacto de cada corte;
- activar stop conditions;
- preparar prompts de Auditor/Fixer/Reviewer con contexto real.

## 7. Estado operativo

Decision Log inicial creado despues del merge de PR #95.

Siguiente mantenimiento esperado:

- registrar cierre o supersedencia de ramas docs antiguas si se limpian;
- registrar decision sobre Corte 1 Party/Counterparty cuando entre formalmente a `master`;
- registrar decision sobre Corte 2 HR -> Party cuando su PR sea aprobado/mergeado;
- registrar decisiones de Tax/RUC, Financial Portfolio y Cost Backbone antes de implementarlos.

## DL-20260530-005 - Estrategia de 3 frentes de ejecucion

Estado: Aprobada

Fecha: 2026-05-30

Decision: La ejecucion de Necktral se divide en 3 frentes con responsabilidades no solapadas: Frente 1 (Cloud/Copilot Coding Agent) implementa logica y bloques de codigo; Frente 2 (Local/Codex) ejecuta tests y validacion con PostgreSQL real; Frente 3 (Frontend) solo conecta APIs ya certificadas y es fase posterior.

Contexto: Se requiere paralelizar el avance sin conflictos entre plataformas. El frontend no avanza hasta que los endpoints esten validados por los frentes 1 y 2.

Razon: Maximiza throughput evitando bloqueos entre implementacion, testing y consumo. Cada frente tiene scope cerrado y entregables claros.

Impacto:

- Datos: ninguno runtime directo.
- Auditoria: no aplica.
- Shadow Ledger: no aplica.
- CEC: no aplica.
- Contador: no aplica.
- Codex: Codex queda asignado formalmente como Frente 2 (testing y validacion local).

Permite:

- Cloud Agent implementa logica sin esperar DB real.
- Codex valida con PostgreSQL real sin implementar logica nueva.
- Frontend solo consume APIs estables.

Bloquea:

- Frontend no avanza hasta que Frentes 1 y 2 certifiquen endpoints.
- Codex no implementa logica de negocio nueva (eso es Frente 1).
- Cloud Agent no aprueba persistencia critica sin evidencia de Frente 2.

Evidencia: `docs/project/EXECUTION_FRONTS_STRATEGY.md`, actualizaciones en `CODEX_OPERATING_BRIEF.md` y `COPILOT_CODING_AGENT.md`.

Revisar si: se agrega un cuarto frente (mobile, analytics) o cambian las condiciones de entrada del Frente 3.
