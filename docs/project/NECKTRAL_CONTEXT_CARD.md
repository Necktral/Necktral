# NECKTRAL_CONTEXT_CARD

## 0. Encabezado de control

Documento: `NECKTRAL_CONTEXT_CARD.md`
Proyecto: Necktral ERP/CRM/POS multiempresa
Estado: Contexto rector vivo
Ultima actualizacion: 2026-05-27
Uso: ChatGPT / Codex / orientacion tecnica / handoff PC1-PC2
Regla superior: este documento guia, pero el codigo real, las migraciones y QA mandan si hay conflicto.

GitHub es evidencia tecnica, no objetivo. Codex ejecuta bajo direccion, no dirige producto ni arquitectura final. El roadmap de negocio manda; el repo real verifica.

## 1. Identidad del sistema

Necktral es una plataforma modular multiempresa, multiplataforma y multidominio para operacion real en Nicaragua. No es solamente ERP/POS: debe ordenar ventas, cobros, pagos, caja, banco, inventario, facturacion, cartera, creditos, nomina, asistencia, auditoria, cierre, Shadow Ledger, evidencia y reportes utiles para contador certificado.

Necktral debe poder soportar, de forma gradual y gobernada:

- ERP/CRM/POS.
- Microfinanciera o funcion fuerte de financiamiento.
- CxC, CxP y creditos como kernels financieros.
- Nomina, asistencia, adelantos, deducciones y relacion laboral.
- Inventario, compras, insumos, costos y proveedores.
- Caja, banco, pagos, settlement y conciliacion.
- Flota, mantenimiento, transporte y maquinaria.
- Fincas de cafe, ganaderia, agroquimicos y operaciones productivas.
- CEC, auditoria, cierre operativo y paquete contador.

Necktral no reemplaza al contador certificado ni pretende ser la contabilidad formal completa. El contador lleva la contabilidad oficial. Necktral produce datos operativos, evidencia, saldos, pre-asientos, Shadow Ledger auxiliar, revisiones y reportes conciliables.

## 2. Proposito operacional

El flujo rector del sistema es:

```text
operacion -> evidencia -> cierre -> contador -> reportes -> Shadow Ledger
```

Para los flujos comerciales y financieros, la regla practica es:

```text
venta -> cobro -> factura -> caja/banco -> inventario -> cierre -> auditoria -> Shadow Ledger -> reportes
```

Todo nuevo modulo debe demostrar como se conecta a ese flujo o declarar por que no aplica. Si un modulo genera dinero, stock, deuda, obligacion, planilla, cierre o evidencia, debe entrar con contratos explicitos, tests y QA.

## 3. Realidad de negocio confirmada

### Confirmado

- Pais principal: Nicaragua.
- El contador certificado lleva la contabilidad formal.
- La empresa/grupo opera multiples negocios relacionados.
- Existe necesidad fuerte de financiamiento, cartera o microfinanciera.
- Se requieren CxC, CxP y creditos como base financiera real.
- Se requiere soporte para nomina, planilla, asistencia y personal operativo.
- Hay multiples fincas de cafe.
- Hay fincas de ganado.
- Hay flota vehicular, maquinaria, mantenimiento y transporte.
- Hay comercio, proveedores, agroquimicos y creditos relevantes.
- Hay personal administrativo, campo normal, cosecha, conductores, cocineras, operarios, agronomos, calidad y financieros.
- Hay compradores externos de cafe, como Atlantic, Emco u otros.
- Los compradores externos depositan a quien vende formalmente.
- Las fincas procesan su propio cafe.
- Los detalles tecnicos agricolas los manejan ingenieros, agronomia y calidad.

### Pendiente con contador

- Tratamiento fiscal exacto por persona, RUC, declarante y empresa.
- Limites por declarante natural o juridico.
- Reportes exactos para declaracion.
- Criterios de revision contable.
- Estados de revision y aprobacion por contador.
- Estrategias fiscales legales permitidas.
- Clasificacion de gastos, costos, cartera, intereses, mora, deducciones y reestructuraciones.

### Pendiente con ingenieros / agronomia / calidad

- Estructura tecnica de fincas, zonas, lotes y labores.
- Calendario anual y mensual de abonos, foliares, deshierba, aplicaciones, cosecha y mantenimiento.
- Catalogo tecnico de labores.
- Insumos por labor, dosis, metrica y rendimiento esperado.
- Indicadores de productividad por finca, zona, lote, jefe y cuadrilla.
- Calidad de cafe, beneficiado, trazabilidad productiva y merma.

### Pendiente con operacion

- Responsables por empresa, finca, sucursal, zona, flota y bodega.
- Jefes y trabajadores por cuadrilla.
- Reglas de asistencia y control de jornadas.
- Reglas de adelantos, deducciones, vales, prestamos internos y pago.
- Ciclo de mantenimiento de vehiculos y maquinaria.
- Evidencias obligatorias por operacion.

## 4. Principios no negociables

1. No crear modulos aislados sin contratos.
2. Todo dominio critico debe tener dueno de datos.
3. Toda operacion economica genera evento, evidencia o excepcion explicita.
4. Todo lo que toque dinero, stock, credito, nomina, caja, cierre o auditoria es C1.
5. Contabilidad formal pertenece al contador; Necktral produce Shadow Ledger auxiliar y soporte operativo.
6. CEC controla, evidencia y cierra; no corrige datos primarios.
7. Accounting no inventa hechos; consume eventos operativos.
8. Inventory no crea deuda.
9. Financing no mueve stock directamente.
10. Payments no emite facturas.
11. Billing no posee saldos de cartera.
12. HR no posee caja ni contabilidad.
13. OrgUnit no debe usarse como basurero para clientes, proveedores ni personas naturales.
14. Party/Counterparty representa personas y entidades de negocio.
15. No microservicios hasta que existan senales objetivas de escala, ownership, deploy o aislamiento.
16. Acotar alcance no significa bajar calidad.
17. SQLite no cierra gates de persistencia para modelos criticos; PostgreSQL real es gate fuerte.

### Invariantes para operaciones criticas

Toda operacion que toque dinero, stock, cartera, credito, nomina, caja, cierre o evidencia debe declarar explicitamente si requiere:

- `AuditEvent` para trazabilidad de quien, cuando, que cambio y por que.
- `OutboxEvent` para publicar hechos operativos idempotentes.
- `EconomicEvent` cuando el hecho operativo tenga impacto economico.
- `JournalDraft` cuando el hecho requiera pre-asiento o validacion contable.
- `idempotency_key` o clave natural equivalente para evitar duplicados.
- `company` y, cuando aplique, `branch` como scope obligatorio.
- `evidence_refs` o evidencia adjunta/referenciada.
- `accountant_review_status` cuando el contador deba revisar.
- gate CEC cuando el cierre dependa de evidencia, saldo, draft o revision.

Si un corte decide no usar alguno de estos contratos, debe documentar la excepcion y el motivo. No se permite omitirlos por comodidad.

## 5. Estado tecnico actual confirmado

Este estado mezcla repo inspeccionado en la base `f8f6229e` y checkpoints operativos confirmados en la conversacion. Si el repo cambia, este bloque debe actualizarse con evidencia.

### Org / IAM / RBAC

- `OrgUnit` soporta estructura interna.
- `OrgUnit` no representa clientes, proveedores ni personas externas.
- `CompanyProfile` existe para datos legales de empresa.
- `CompanyLink` existe para relaciones company-company.
- RBAC tiene roles, permisos y asignaciones por unidad organizativa.

### Party / Counterparty

- Corte 1 Party/Counterparty base + hardening aprobado.
- Commit base aprobado: `f8f6229e Add audited Party counterparty base with admin hardening`.
- App creada: `apps.modulos.parties`.
- Modelos existentes: `Party`, `PartyRole`.
- Auditoria Party company-scoped aprobada.
- Admin Party read-only/no-delete aprobado.
- PostgreSQL QA del Corte 1 reportado como OK.

### HR

- Existe `Employee`.
- Existe `JobPosition`.
- Existe `EmploymentAssignment`.
- Existe `PositionRoleMap`.
- Existe `linked_user` como acceso tecnico.
- HR tiene servicios de provisioning, reset, revoke y automatizacion RBAC por puesto.
- En la base `f8f6229e`, `Employee` aun no tiene `Party`.
- Corte 2 `HR -> Party` existe como trabajo local reportado en rama `feat/hr-party-link`, con PostgreSQL QA OK, pero queda pendiente de commit/review/PR antes de considerarse cerrado en este Context Card.

### Billing / Facturacion

- `BillingDocument` existe.
- Billing usa `customer_name` / `customer_ref` textual en el estado auditado.
- Falta cliente fuerte basado en `Party`.
- Billing no debe poseer cartera.

### Payments / Cash / Settlement

- `PaymentIntent` existe.
- `CashSession` existe.
- `CashMovement` existe.
- El carril `TRANSFER` tiene captura, reversa, Shadow Ledger y snapshot read-only de settlement cerrados segun checkpoint.
- `CREDIT` como tender no debe confundirse con credito financiero.

### Inventory / Compras / Proveedores

- `Warehouse`, `InventoryItem`, `StockBalance` y `StockMovement` existen.
- Compras tiene documentos de proveedor y pagos de proveedor en modulos existentes.
- Falta proveedor fuerte basado en `Party`.
- Inventory no debe crear deuda ni cartera.

### Accounting / Shadow Ledger

- `EconomicEvent` existe.
- `JournalDraft` existe.
- `JournalEntry` existe.
- Shadow Ledger esta avanzado.
- Accounting debe consumir hechos economicos; no debe poseer operacion primaria.
- `PAYMENTS` no debe entrar de forma indiscriminada en cierres contables; el carril TRANSFER ya tiene reglas especificas.

### CEC

- `CloseRun` existe.
- CEC tiene cierre, excepciones y evidencia.
- Aun no tiene gates de cartera.
- CEC no debe corregir datos primarios: bloquea, evidencia, advierte y gobierna cierre.

### PRs / decisiones cerradas por checkpoint

- PR #87: transfer reversal cerrado.
- PR #88: transfer payment accounting cerrado.
- PR #89: `js-cookie` security gate cerrado.
- PR #90: transfer settlement visibility cerrado.

## 6. Mapa de arquitectura por capas

### Capa 1 - Plataforma

- Org/IAM.
- RBAC.
- Audit.
- Common.
- Integration / Outbox.
- Sync.
- Seguridad y release stability.

### Capa 2 - Identidad de negocio

- Party / Counterparty.
- Persona natural.
- Persona juridica.
- Cliente.
- Proveedor.
- Empleado.
- Productor.
- Declarante.
- Comprador externo.
- Relacionado.

### Capa 3 - Nucleos financieros

- Payments / Cash.
- CxC.
- CxP.
- Credit / Financing.
- Accounting / Shadow Ledger.

### Capa 4 - Operacion comercial

- Billing.
- Sales / POS.
- Purchasing.
- Inventory.
- Reporting.

### Capa 5 - Trabajo y personas

- HR.
- Payroll.
- Attendance.
- Crew / cuadrilla.
- Work assignment.
- Deductions.
- Employee loans.

### Capa 6 - Operacion productiva

- Farm operations.
- Work planning.
- Coffee operation.
- Cattle operation.
- Agrochemical operations.
- Fleet / maintenance.
- Machinery.
- Transport.

### Capa 7 - Control

- CEC.
- CloseRun.
- Evidence package.
- Accountant package.
- Exception management.
- Review status.

## 7. Kernels centrales

Los kernels son nucleos con ownership claro. Los verticales productivos consumen kernels; no los reemplazan.

1. Org / IAM / RBAC Kernel: estructura interna, usuarios, roles, permisos y contexto.
2. Party / Counterparty Kernel: identidad de negocio, personas, entidades y roles de contraparte.
3. Financial Portfolio Kernel: CxC, CxP, creditos, obligaciones, vencimientos y aplicaciones.
4. Payments / Cash Kernel: cobros, pagos, caja, banco, settlement y conciliacion.
5. Billing / Fiscal Document Kernel: documentos, facturas, notas y contratos fiscales.
6. Inventory / Cost Kernel: existencias, movimientos, costo, bodegas e insumos.
7. Accounting / Shadow Ledger Kernel: hechos economicos, pre-asientos, validacion y proyeccion.
8. HR / Payroll / Attendance Kernel: persona laboral, puestos, asistencia, planilla y deducciones.
9. CEC / Control Plane Kernel: cierre, evidencia, excepciones, revision y paquete contador.

Regla: no todo es kernel. Un modulo productivo puede ser importante sin poseer dinero, stock, cartera o contabilidad.

### Familias de eventos y limites

Eventos de master data:

- `party.created.v1`
- `party.updated.v1`
- `party.role.assigned.v1`
- `party.role.revoked.v1`
- `hr.employee.linked_to_party.v1`
- `hr.employee.party_link_changed.v1`

Eventos financieros futuros:

- `receivable.created.v1`
- `payable.created.v1`
- `credit.disbursement.recorded.v1`
- `payment.applied.v1`
- `portfolio.balance.updated.v1`

Eventos de cierre/control futuros:

- `cec.portfolio.exception.raised.v1`
- `cec.evidence.required.v1`
- `cec.accountant_review.requested.v1`

Limites:

- Eventos de master data no crean saldos.
- Eventos financieros no deben vivir dentro de Accounting como dueno de operacion.
- Eventos CEC no corrigen datos primarios; bloquean, alertan o solicitan revision.
- Outbox publica hechos; Audit registra trazabilidad; Accounting consume hechos economicos.

## 8. Party / Counterparty

Party/Counterparty es la base canonica para personas y entidades de negocio. OrgUnit representa estructura interna; Party representa quien opera, compra, vende, trabaja, declara, provee, financia o recibe financiamiento.

Debe representar:

- clientes;
- proveedores;
- empleados;
- productores;
- compradores externos;
- personas naturales con RUC;
- declarantes;
- familiares o relacionados;
- contador;
- contratistas;
- transportistas;
- proveedores de agroquimicos;
- compradores formales e informales cuando aplique.

Roles esperados actuales y futuros:

- `CUSTOMER`
- `SUPPLIER`
- `EMPLOYEE`
- `PRODUCER`
- `DECLARANT`
- `EXTERNAL_BUYER`
- `NATURAL_DECLARANT`
- `RELATED_PARTY`
- `ACCOUNTANT`
- `CONTRACTOR`
- `TRANSPORT_PROVIDER`
- `AGROCHEMICAL_PROVIDER`

Importancia:

- Sin Party no hay CxC/CxP/creditos solidos.
- Sin Party Billing queda atado a `customer_name` textual.
- Sin Party Payments no sabe quien paga o cobra.
- Sin Party HR queda desconectado de identidad legal.
- Sin Party el contador no puede reportar por RUC, persona, proveedor o cliente.

Reglas:

- `PartyRole` describe relacion de negocio, no autorizacion tecnica.
- `PartyRole.EMPLOYEE` no reemplaza RBAC.
- `Party` no genera saldos ni obligaciones por si mismo.
- Eventos Party son auditoria de master data; no son `EconomicEvent`.

## 9. CxC / CxP / Creditos

CxC, CxP y creditos deben ser kernel financiero, no feature secundaria.

Conceptos esperados:

- `Receivable`
- `Payable`
- `CreditFacility`
- `CreditAgreement`
- `Obligation`
- `Installment`
- `PaymentAllocation`
- `InterestAccrual`
- `Penalty`
- `Adjustment`
- `Restructure`
- `WriteOff`
- `AccountantReviewStatus`
- `Evidence`

Reglas:

- CxC = nos deben.
- CxP = debemos.
- Financing crea obligaciones CxC o CxP segun direccion.
- Creditos no son `payment_method=CREDIT`.
- `CREDIT` como tender no equivale a credito financiero.
- Billing emite documentos; no posee saldos de cartera.
- Payments registra/aplica pagos; no inventa deuda.
- Accounting consume hechos; no posee cartera.

Reportes necesarios para contador:

- saldos por persona/RUC;
- saldos por proveedor;
- saldos por cliente/comprador;
- antiguedad de saldos;
- vencimientos;
- abonos;
- intereses;
- mora;
- creditos recibidos;
- creditos otorgados;
- reestructuraciones;
- ajustes;
- castigos;
- operaciones sin evidencia;
- operaciones pendientes de revision.

Eventos candidatos futuros, no implementados por este documento:

- `receivable.created.v1`
- `payable.created.v1`
- `credit.disbursement.recorded.v1`
- `payment.applied.v1`
- `portfolio.balance.updated.v1`
- `cec.portfolio.exception.raised.v1`

## 10. HR, nomina y asistencia

HR debe soportar relaciones laborales reales y distintas clases de trabajadores:

- administracion;
- campo normal;
- temporales de cosecha;
- conductores;
- cocineras;
- operarios;
- agronomos;
- control de calidad;
- financieros;
- jefes de zona;
- trabajadores por jefe;
- cuadrillas.

Separacion de ownership:

- `Party` = persona o entidad de negocio/legal.
- `Employee` = relacion laboral base.
- `linked_user` = acceso tecnico al sistema.
- `EmploymentAssignment` = puesto, empresa, sucursal, finca o zona cuando exista.
- `Attendance` = asistencia y jornada.
- `Payroll` = calculo/pago de planilla.
- `Crew` = cuadrilla.
- `WorkLog` = trabajo realizado.
- `Deduction` = deducciones, adelantos y creditos internos.

Reglas:

- HR no debe ser dueno de identidad legal completa.
- HR no debe crear contabilidad ni caja.
- `linked_user` no debe confundirse con `Party`.
- `PartyRole.EMPLOYEE` no concede permisos.
- Nomina, asistencia y creditos de empleado deben entrar como cortes separados.

## 11. Work Planning por finca / zona / labor

Work Planning debe conectar plan tecnico, personal, insumos, equipo, costo y avance real.

Debe soportar:

- plan anual por finca;
- plan mensual;
- finca;
- zona;
- lote cuando aplique;
- labor;
- jefe responsable;
- trabajadores asignados;
- cantidad estimada de personal;
- insumo requerido;
- equipo requerido;
- costo esperado;
- avance real;
- variacion;
- evidencia.

Labores ejemplo:

- abonos;
- foliares;
- deshierba;
- aplicaciones;
- limpieza;
- mantenimiento de caminos;
- control de plagas;
- corte / cosecha;
- fertilizacion;
- mantenimiento productivo.

Estados esperados:

- `PLANNED`
- `SCHEDULED`
- `IN_PROGRESS`
- `COMPLETED`
- `BLOCKED`
- `CANCELLED`
- `REWORK_REQUIRED`

Conexiones:

- HR / Attendance.
- Inventory / insumos.
- Fleet / equipo.
- Cost center.
- CEC.
- Shadow Ledger.
- Reportes.

Regla: Work Planning no debe poseer inventario, deuda, pagos ni contabilidad. Debe consumir esos kernels.

## 12. Fleet maintenance

Fleet debe cubrir vehiculos, maquinaria, mantenimiento, combustible, viajes y costos asignables.

Debe soportar:

- vehiculo;
- tipo;
- placa;
- responsable;
- odometro;
- horometro;
- plan preventivo;
- mantenimiento correctivo;
- combustible;
- llantas;
- repuestos;
- seguros;
- documentos;
- viajes;
- costos por finca, empresa, labor o centro de costo.

Estados esperados:

- `ACTIVE`
- `IN_SERVICE`
- `MAINTENANCE_DUE`
- `IN_MAINTENANCE`
- `OUT_OF_SERVICE`
- `RETIRED`

Eventos candidatos:

- `fleet.maintenance.scheduled`
- `fleet.maintenance.completed`
- `fleet.fuel.consumed`
- `fleet.trip.completed`
- `fleet.cost.allocated`

Regla: Fleet no reemplaza Payments, Inventory ni Accounting. Debe producir hechos operativos y evidencia para costeo y cierre.

## 13. Verticales productivos

Los verticales productivos son capas de negocio que usan kernels compartidos.

### Hacienda / fincas

Usa Party, HR, Inventory, Fleet, Work Planning, CxC/CxP, CEC y Accounting. No debe poseer cartera, pagos, inventario maestro ni contabilidad final.

### Ganaderia

Debe cubrir hato, lote, alimentacion, sanidad, mortalidad, ventas, costos, personal y plan de labores.

### Agroquimicos

Debe cubrir proveedores, credito recibido, inventario, consumo por finca/zona/labor, CxP y costeo.

### Transporte / maquinaria

Debe cubrir flota, viajes, mantenimiento, cargos internos y costos.

### Cafe

Debe esperar definicion con contador e ingenieros para tratamiento fiscal, flujo tecnico, compradores, declarantes, beneficiado, calidad y reportes. No se implementa como modulo aislado antes de Party, cartera, HR y costeo.

## 14. CEC y paquete contador

CEC debe producir paquetes de cierre y revision para contador, por empresa, persona, proveedor, cliente, finca y dominio operativo.

Paquetes esperados:

- paquete por empresa/RUC;
- paquete por persona declarante;
- paquete por proveedor;
- paquete por cliente/comprador;
- paquete por finca;
- paquete de cartera;
- paquete de CxP;
- paquete de nomina;
- paquete de inventario/costos;
- paquete de flota;
- paquete de produccion.

Estados esperados:

- `OPEN`
- `PENDING_EVIDENCE`
- `PENDING_ACCOUNTANT_REVIEW`
- `APPROVED`
- `RECLASSIFICATION_REQUIRED`
- `BLOCKED`
- `CLOSED`

Reglas de cierre:

- sin evidencia -> warning o block;
- sin contraparte -> block;
- sin finca/cost center cuando aplica -> block;
- sin revision contador cuando aplica -> block;
- `JournalDraft` en exception -> block;
- pagos no aplicados -> warning o block segun monto y periodo;
- saldos vencidos no revisados -> warning o block;
- operaciones con Party faltante -> block en dominios financieros.

## 15. Roadmap rector de 12 objetivos

Este roadmap puede ajustarse con Decision Log, pero no debe reinventarse en cada chat.

1. Context Card / mapa rector de plataforma.
2. Party / Counterparty.
3. CxC / CxP / Creditos.
4. HR / Nomina / Asistencia.
5. Work Planning por finca / zona / labor.
6. Inventory / Compras / Insumos / Costos.
7. Fleet / Mantenimiento / Transporte / Maquinaria.
8. Payments / Cash / Settlement / Cartera.
9. Billing / Documentos / Cartera.
10. Verticales productivos: hacienda / ganado / agro.
11. CEC / Paquete contador / Reportes.
12. Seguridad / Auditoria / Sync / Release Stability.

Estado de avance:

- Objetivo 1: este documento crea la primera version persistente del Context Card rector.
- Objetivo 2: Party/Counterparty base aprobado en Corte 1.
- Objetivo 4: HR -> Party esta en trabajo local reportado, pendiente de cierre formal.
- Objetivos 3, 5, 6, 7, 8, 9, 10 y 11 requieren cortes independientes.

## 16. Estado cerrado / log de decisiones

### Decisiones cerradas

- Settlement TRANSFER cerrado.
- Reversa TRANSFER cerrada.
- Shadow Ledger para TRANSFER cerrado.
- Snapshot read-only de settlement TRANSFER cerrado.
- Security gate `js-cookie` cerrado.
- Party/Counterparty sube a prioridad arquitectonica.
- CxC/CxP/Creditos son kernels financieros.
- Hacienda es vertical productivo, no nucleo total.
- Financing es kernel financiero.
- Nomina/asistencia son nucleo operativo.
- Flota y Work Planning son dominios operativos fuertes.
- OrgUnit no representa contrapartes.
- Accounting consume hechos; no posee operacion primaria.

### Decisiones pendientes

- Cierre formal de Corte 2 `HR -> Party` despues de review.
- Diseno de kernel de cartera.
- Diseno de CxP para proveedores y agroquimicos.
- Diseno de creditos recibidos/otorgados.
- Estrategia de backfill de clientes/proveedores textuales hacia Party.
- Paquete contador final por RUC/persona/proveedor/cliente/finca.

## 17. Reglas para Codex

Codex debe:

1. Leer este Context Card antes de tareas Necktral amplias.
2. Verificar branch, HEAD y worktree.
3. Auditar codigo antes de sugerir implementacion.
4. No inventar roadmap.
5. No abrir microfrentes.
6. No convertir GitHub en objetivo.
7. Proponer Ask/read-only antes de Code si el dominio no esta claro.
8. Reportar hechos vs hipotesis.
9. Respetar archivos permitidos/prohibidos.
10. Exigir tests y QA antes de PR.
11. Usar PostgreSQL real para modelos criticos, migraciones y constraints.
12. Mantener cambios acotados por alcance, no por calidad.
13. Declarar impacto en datos, auditoria, eventos y cierre.
14. Mantener Controller -> Auditor Agent -> Fixer Agent -> Reviewer Agent.
15. Detenerse si el repo contradice este documento y reportar la discrepancia.
16. Detenerse si aparecen datos existentes que exigen backfill no aprobado.
17. Detenerse si el cambio obliga a tocar dominios prohibidos para compilar.
18. Detenerse si no puede ejecutar QA requerido por entorno y marcar `BLOCKED_BY_ENVIRONMENT`.

Codex no debe:

1. Implementar cafe/finca sin contador e ingenieros.
2. Implementar CxC/CxP sin Party.
3. Usar OrgUnit como Party.
4. Meter todo en Accounting.
5. Crear modulos aislados.
6. Tocar Sync/frontend/migraciones sin autorizacion.
7. Proponer microservicios sin senales objetivas.
8. Confundir tender `CREDIT` con credito financiero.
9. Abrir HR, Billing, Compras, Fuel, POS, Payments, Accounting o CEC sin corte aprobado.
10. Aprobar cambios persistentes solo con SQLite cuando el riesgo es de DB real.
11. Usar este Context Card como permiso para implementar todo el roadmap.
12. Crear APIs, migraciones o integraciones si la tarea era read-only.

Stop conditions obligatorias:

- Ya existe un modelo equivalente no detectado.
- Las reglas multiempresa no son claras.
- La unicidad, migracion o backfill puede romper datos existentes.
- La auditoria cae en `SYSTEM` cuando debe ser `COMPANY:{id}`.
- La implementacion requiere tocar Accounting, Payments, CEC, Sync o frontend fuera de alcance.
- PostgreSQL real no esta disponible para un cambio que depende de constraints/migraciones.
- El reviewer devuelve `REQUEST_CHANGES` o `REVERT_RECOMMENDED`.

Formato minimo de tarea Codex:

```text
Objetivo
Contexto funcional
Tipo de cambio
Alcance permitido
Archivos prohibidos
Contratos impactados
Invariantes
Tests requeridos
QA PostgreSQL si aplica
Criterios de aceptacion
Non-goals
```

## 18. Preguntas pendientes

### Contador

- Que reportes fiscales son obligatorios por empresa, persona, proveedor, cliente y finca.
- Limites por declarante.
- Criterios de revision.
- Clasificacion fiscal de gastos, costos, intereses, mora, deducciones y creditos.
- Estrategias fiscales legales permitidas.
- Paquete contador minimo para cierre mensual.

### Ingenieros / agronomia / calidad

- Catalogo de labores.
- Zonas, lotes y unidades productivas.
- Calendarios tecnicos.
- Insumos por labor.
- Metricas de productividad.
- Calidad, beneficiado, merma y trazabilidad de cafe.

### Operacion

- Responsables por empresa/finca/zona/flota.
- Jefes, cuadrillas y trabajadores.
- Reglas de asistencia.
- Reglas de mantenimiento.
- Evidencias obligatorias por tipo de operacion.
- Politicas de adelantos, vales y deducciones.

### Desarrollo

- Que existe realmente en repo por cada dominio.
- Que falta antes de cada corte implementable.
- Donde ubicar nuevos kernels vs modulos.
- Que contratos/eventos deben existir antes de integrar.
- Que tests cierran cada gate.

## 19. Backlog de alto nivel

P0 - Crear Context Card persistente.
P1 - Cerrar trazabilidad de Party/Counterparty y Corte 2 HR -> Party.
P2 - Reviewer Agent para HR -> Party.
P3 - Disenar kernel Financial Portfolio: CxC, CxP y creditos.
P4 - Adaptar HR a Party como hecho cerrado si el review aprueba.
P5 - Adaptar Billing clientes -> Party.
P6 - Adaptar Compras/proveedores -> Party.
P7 - CxC/CxP base con saldos, vencimientos, evidencia y accountant review status.
P8 - Creditos/Financing con obligaciones, cuotas, intereses, mora y pagos aplicados.
P9 - Attendance/Payroll/Deductions.
P10 - Work Planning finca/zona/labor.
P11 - Inventory/Compras/Insumos/Costos por finca y labor.
P12 - Fleet/Mantenimiento/Transporte/Maquinaria.
P13 - CEC gates de cartera, nomina, inventario, flota y produccion.
P14 - Paquete contador y reportes ejecutivos.
P15 - Verticales productivos: cafe, ganaderia, agroquimicos y transporte.

## 20. Formato de mantenimiento

Este documento debe mantenerse como memoria viva:

- Cada cambio de direccion crea Decision Log.
- Cada objetivo cerrado se marca como confirmado con fecha, rama/commit/PR y QA.
- Cada hipotesis validada pasa a hecho confirmado.
- Cada duda con contador/ingenieros queda en preguntas pendientes hasta resolverse.
- Cada corte implementable debe referenciar este Context Card y el estado real del repo.
- Cada bloque economicamente critico debe declarar impacto en evidencia, audit, Shadow Ledger, CEC y contador.
- Si el codigo contradice el documento, se actualiza el documento o se corrige el codigo; no se ignora la discrepancia.

## Estado operativo de este Context Card

Este archivo es un documento rector, no una migracion ni una implementacion. No habilita por si solo CxC, CxP, creditos, HR, nomina, finca, cafe, flota, compras, Billing ni CEC. Sirve para orientar auditorias y cortes futuros con evidencia.
