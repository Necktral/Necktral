# Inventario y Análisis Inicial de Bloques de Código en Documentación

**Fecha**: 2026-05-29
**Objetivo**: Inventariar todos los bloques de código en la documentación para facilitar la sincronización progresiva con el código real.

## Resumen Ejecutivo

Se ha completado el inventario exhaustivo de todos los bloques de código presentes en la documentación del repositorio Necktral. Este es el primer paso para actualizar la documentación defasada mediante sincronización progresiva.

### Números Clave

- **331 bloques de código** distribuidos en **43 archivos** de documentación
- **1,901 líneas de código** documentadas
- **11 lenguajes/formatos** diferentes identificados
- **80% del contenido** está en comandos Bash (265 bloques) y texto plano (37 bloques)

## Distribución por Lenguaje

| Lenguaje | Bloques | Líneas | % del Total |
|----------|---------|--------|-------------|
| bash | 265 | 835 | 80.1% |
| text | 37 | 761 | 11.2% |
| python | 9 | 112 | 2.7% |
| json | 6 | 62 | 1.8% |
| plain | 4 | 40 | 1.2% |
| mermaid | 2 | 35 | 0.6% |
| typescript | 2 | 27 | 0.6% |
| yaml | 2 | 21 | 0.6% |
| cron | 2 | 2 | 0.6% |
| powershell | 1 | 1 | 0.3% |
| env | 1 | 5 | 0.3% |

## Archivos con Mayor Concentración de Código

### Top 10

1. **qa/README.md** - 78 bloques (23.6% del total)
2. **README.md** - 41 bloques (12.4% del total)
3. **docs/ANALISIS_ROBUSTEZ_MULTIPLATAFORMA_v1.0.md** - 15 bloques
4. **docs/operacion/GO_LIVE_BILLING_INVENTORY_F4_F5_v1.0.md** - 15 bloques
5. **docs/operacion/PROMPTS_STACK_REAL.md** - 13 bloques
6. **docs/operacion/GO_LIVE_FASE8_PRODUCCION_v1.0.md** - 11 bloques
7. **docs/operacion/SHADOW_LEDGER_FASE4A_CERTIFICACION_v1.0.md** - 10 bloques
8. **docs/operacion/ADAPTER_B_FASE6_CERTIFICACION_v1.0.md** - 9 bloques
9. **docs/operacion/CODEX_MASTER_PACK_v1.0.md** - 9 bloques
10. **docs/operacion/GL_FASE7A_CERTIFICACION_v1.0.md** - 9 bloques

## Categorización de Documentos

### Documentación Operativa (docs/operacion/)
- **31 archivos** con bloques de código
- Documentos de certificación, go-live, handoff y runbooks
- Alto contenido de comandos bash para operaciones de deployment

### Documentación Raíz
- **README.md principal** con 41 bloques (inicio rápido, comandos Docker)
- **BITACORA.md** y **CHANGELOG.md** (sin bloques de código)

### Documentación de QA
- **qa/README.md** con 78 bloques
- Comandos de testing, CI/CD, guards y verificaciones
- Alto contenido técnico operativo

### Documentación de Proyecto (docs/project/)
- **4 archivos** con contenido principalmente descriptivo
- Bajo contenido de código (14 bloques total)

## Artefactos Generados

Se han creado los siguientes artefactos para facilitar el trabajo de sincronización:

1. **inventario_bloques_codigo.json** (509 KB)
   - Inventario completo en formato JSON estructurado
   - Incluye metadatos, ubicación exacta (archivo y líneas), contenido completo
   - Agrupaciones por archivo y por lenguaje
   - Listo para procesamiento automatizado

2. **inventario_bloques_codigo.md** (30 KB)
   - Resumen legible en Markdown
   - Estadísticas consolidadas
   - Detalle por archivo con ubicación de cada bloque

3. **scripts/inventario_bloques_codigo.py**
   - Script Python reutilizable para regenerar inventario
   - Puede ejecutarse en cualquier momento para actualizar

## Siguiente Fase: Plan de Sincronización

### Prioridades Recomendadas

#### Fase 1: Documentación de Alto Tráfico (Crítica)
- [ ] README.md principal (41 bloques) - entrada principal al proyecto
- [ ] qa/README.md (78 bloques) - usado en CI/CD diario
- [ ] backend/README.md y frontend/README.md - guías de desarrollo

#### Fase 2: Documentación Operativa (Alta)
- [ ] Runbooks de go-live (F8, F9, F10, F11, F12)
- [ ] Documentos de certificación (ADAPTER_B, GL_FASE7A, etc.)
- [ ] Guías de deployment (CD_DEPLOY, STAGING_FIRST)

#### Fase 3: Documentación de Contexto (Media)
- [ ] docs/ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md
- [ ] docs/CONTRACT_PACK_v*.md
- [ ] docs/operacion/CODEX_MASTER_PACK_v1.0.md

#### Fase 4: Documentación de Proyecto (Baja)
- [ ] docs/project/* (contexto, roadmap, decisiones)
- [ ] Documentos de análisis y diagnóstico

### Metodología de Sincronización

Para cada bloque de código identificado:

1. **Verificar existencia**: ¿El código/comando existe en el repo actual?
2. **Validar correctitud**: ¿El código funciona con la versión actual?
3. **Actualizar o eliminar**: Sincronizar con la realidad actual
4. **Documentar cambios**: Registrar qué se actualizó y por qué

### Herramientas de Soporte

```bash
# Regenerar inventario en cualquier momento
python scripts/inventario_bloques_codigo.py

# Buscar un bloque específico en el JSON
jq '.all_blocks[] | select(.file_relative == "README.md") | .language' inventario_bloques_codigo.json | sort | uniq -c

# Listar archivos por cantidad de bloques
jq -r '.by_file | to_entries | .[] | "\(.value | length)\t\(.key)"' inventario_bloques_codigo.json | sort -rn
```

## Observaciones Importantes

### Hallazgos Técnicos

1. **Dominancia de Bash**: 80% del código documentado son comandos shell, indicando documentación muy orientada a operaciones y deployment

2. **Bajo contenido de código fuente**: Solo 9 bloques Python y 2 TypeScript, la documentación se enfoca más en "cómo usar" que en "cómo funciona internamente"

3. **Fragmentación**: El contenido está distribuido en 43 archivos, requiere enfoque sistemático para no perder bloques

4. **Bloques de texto**: 37 bloques marcados como "text" contienen principalmente outputs de comandos y resultados esperados

### Riesgos Identificados

1. **Comandos obsoletos**: Alta probabilidad de que comandos bash estén desactualizados con cambios en scripts, Makefile o Docker
2. **Rutas hardcodeadas**: Muchos comandos pueden tener rutas que ya no existen
3. **Outputs desactualizados**: Los bloques "text" con outputs esperados probablemente no coinciden con la realidad actual

## Conclusión

El inventario está completo y listo para la siguiente fase. Se recomienda:

1. Comenzar con README.md y qa/README.md por su alto impacto
2. Usar el JSON para automatización donde sea posible
3. Documentar patrones de actualización para aplicar a bloques similares
4. Mantener el inventario actualizado conforme se realicen cambios

---

**Artefactos relacionados:**
- `inventario_bloques_codigo.json` - Inventario completo estructurado
- `inventario_bloques_codigo.md` - Resumen legible
- `scripts/inventario_bloques_codigo.py` - Script de regeneración
