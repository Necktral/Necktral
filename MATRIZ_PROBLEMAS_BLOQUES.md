# Matriz de Problemas - Validación Profunda de Bloques de Código

## Resumen Ejecutivo

- **Bloques validados**: 331
- **Bloques con problemas**: 70
- **Total de problemas**: 302
- **Archivos afectados**: 21

## Distribución por Severidad

| Severidad | Cantidad | % del Total |
|-----------|----------|-------------|
| CRÍTICA | 5 | 1.7% |
| ALTA | 12 | 4.0% |
| MEDIA | 282 | 93.4% |
| BAJA | 0 | 0.0% |
| INFO | 3 | 1.0% |

## Distribución por Tipo de Problema

| Tipo | Cantidad |
|------|----------|
| comando_no_existe | 279 |
| archivo_no_existe | 12 |
| secreto_potencial_expuesto | 4 |
| output_desactualizado | 3 |
| comando_peligroso | 2 |
| sintaxis_invalida | 2 |

## Problemas Críticos

### 1. Error de sintaxis Python: invalid syntax. Perhaps you forgot a comma?
- **Archivo**: docs/ANALISIS_ROBUSTEZ_MULTIPLATAFORMA_v1.0.md
- **Líneas**: 192-199
- **Tipo**: sintaxis_invalida
- **Sugerencia**: Corregir sintaxis Python

### 2. Posible secreto expuesto en documentación
- **Archivo**: simulacion/README.md
- **Líneas**: 98-107
- **Tipo**: secreto_potencial_expuesto
- **Sugerencia**: Usar variables de entorno o archivos .env

### 3. Posible secreto expuesto en documentación
- **Archivo**: simulacion/README.md
- **Líneas**: 111-124
- **Tipo**: secreto_potencial_expuesto
- **Sugerencia**: Usar variables de entorno o archivos .env

### 4. Posible secreto expuesto en documentación
- **Archivo**: simulacion/dashboards/README.md
- **Líneas**: 97-106
- **Tipo**: secreto_potencial_expuesto
- **Sugerencia**: Usar variables de entorno o archivos .env

### 5. Posible secreto expuesto en documentación
- **Archivo**: simulacion/dashboards/README.md
- **Líneas**: 110-123
- **Tipo**: secreto_potencial_expuesto
- **Sugerencia**: Usar variables de entorno o archivos .env


## Top 10 Archivos con Más Problemas

| Archivo | Problemas |
|---------|-----------|
| qa/README.md | 48 |
| docs/operacion/ADAPTER_B_FASE6_CERTIFICACION_v1.0.md | 37 |
| docs/operacion/GO_LIVE_FASE8_PRODUCCION_v1.0.md | 33 |
| qa/k6/README.md | 31 |
| docs/operacion/GL_FASE7A_CERTIFICACION_v1.0.md | 30 |
| docs/operacion/SHADOW_LEDGER_FASE4A_CERTIFICACION_v1.0.md | 30 |
| docs/BRANCH_GOVERNANCE.md | 13 |
| simulacion/README.md | 13 |
| simulacion/dashboards/README.md | 13 |
| docs/operacion/GO_LIVE_BILLING_INVENTORY_F4_F5_v1.0.md | 10 |