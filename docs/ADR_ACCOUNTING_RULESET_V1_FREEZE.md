# ADR — Accounting Ruleset v1 Freeze

Version: v1.0  
Fecha: 2026-03-17  
Estado: Aprobado

## Decisión

`PostingRuleSet v1` queda congelado como baseline contractual del shadow ledger y posting controlado.

## Congelado en v1

- selección por scope y vigencia
- `fiscal_mode`
- precedencia determinista
- versionado explícito
- relación con `EconomicEvent`, `JournalDraft` y `JournalEntry`

## Reglas

- Si no existe ruleset activo aplicable, el resultado es `PENDING_RULESET`, no bypass silencioso.
- Si no existe regla aplicable, el resultado es `PENDING_RULE`.
- Si el draft viola invariantes, pasa a `EXCEPTION`.
- Mismo input/version debe producir la misma selección de ruleset y el mismo draft derivado.

## No incluido en esta decisión

- Nuevos eventos operativos fuera del baseline actual.
- Nuevas reglas contables “de ejemplo”.
- Reapertura de fases certificadas por razones no contractuales.
