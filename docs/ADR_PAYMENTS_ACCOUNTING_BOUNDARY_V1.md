# ADR — Payments Accounting Boundary v1

Version: v1.0  
Fecha: 2026-03-17  
Estado: Aprobado

## Decisión

En v1, Payments & Cash mantiene ownership de operación de pago/caja, mientras Accounting conserva ownership de journal final y cierre financiero.

## Baseline actual congelado

- Payments produce eventos operativos como:
  - `PaymentIntentCreated`
  - `CashSessionOpened`
  - `CashMovementPosted`
  - `CashSessionClosed`
- Accounting reconoce eventos PAYMENTS dentro de `SUPPORTED_ECONOMIC_EVENTS`.
- Accounting no procesa hoy PAYMENTS vía `OPERATIONAL_ACCOUNTING_EVENTS` en write-time.

## Regla operativa

- Payments no hace posting final.
- La conciliación provider y los estados de cash session viven en Payments/Cash.
- Cualquier cambio futuro para write-time accounting link desde Payments requiere ADR y pruebas específicas.

## Resultado esperado

- Frontera explícita y no ambigua.
- Sin dual ownership entre caja operativa y journal final.
