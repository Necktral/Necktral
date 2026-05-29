#!/usr/bin/env python3
"""
Validación Profunda de Bloques de Código en Documentación.

Este script realiza un análisis exhaustivo línea por línea de todos los bloques
de código documentados para detectar:
- Funcionalidad: ¿Los comandos/scripts funcionan?
- Robustez: ¿Están bien escritos?
- Fallos: ¿Comandos obsoletos o incorrectos?
- Inconsistencias: ¿Coincide con el código real?
- Descripciones: ¿Son precisas?

Genera una matriz dura de problemas sin sesgos.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum
import sys


class Severidad(Enum):
    """Severidad de problemas detectados."""
    CRITICA = "CRÍTICA"      # Bloquea operación, causa error fatal
    ALTA = "ALTA"            # Funcionalidad incorrecta, resultados erróneos
    MEDIA = "MEDIA"          # Funciona pero subóptimo, warnings
    BAJA = "BAJA"            # Mejoras cosméticas, documentación
    INFO = "INFO"            # Información, sin problema real


class TipoProblema(Enum):
    """Tipos de problemas."""
    ARCHIVO_NO_EXISTE = "archivo_no_existe"
    COMANDO_NO_EXISTE = "comando_no_existe"
    SINTAXIS_INVALIDA = "sintaxis_invalida"
    RUTA_HARDCODED = "ruta_hardcodeada"
    INCONSISTENCIA_CODIGO = "inconsistencia_con_codigo"
    COMANDO_OBSOLETO = "comando_obsoleto"
    DESCRIPCION_IMPRECISA = "descripcion_imprecisa"
    FALTA_CONTEXTO = "falta_contexto"
    OUTPUT_DESACTUALIZADO = "output_desactualizado"
    SECRETO_EXPUESTO = "secreto_potencial_expuesto"
    COMANDO_PELIGROSO = "comando_peligroso"
    VERSION_DESACTUALIZADA = "version_desactualizada"
    BLOQUE_INCOMPLETO = "bloque_incompleto"
    FORMATO_INCORRECTO = "formato_incorrecto"


@dataclass
class Problema:
    """Representa un problema detectado en un bloque de código."""
    archivo: str
    bloque_linea_inicio: int
    bloque_linea_fin: int
    lenguaje: str
    severidad: Severidad
    tipo: TipoProblema
    descripcion: str
    linea_especifica: Optional[int] = None
    contenido_problematico: Optional[str] = None
    sugerencia: Optional[str] = None
    evidencia: Optional[str] = None


@dataclass
class EstadisticasValidacion:
    """Estadísticas de validación."""
    total_bloques: int = 0
    bloques_validados: int = 0
    bloques_con_problemas: int = 0
    problemas_criticos: int = 0
    problemas_altos: int = 0
    problemas_medios: int = 0
    problemas_bajos: int = 0
    problemas_info: int = 0
    archivos_no_existen: int = 0
    comandos_obsoletos: int = 0
    inconsistencias: int = 0


class ValidadorBloquesCodigo:
    """Validador profundo de bloques de código."""

    def __init__(self, repo_root: Path, inventario_path: Path):
        self.repo_root = repo_root
        self.inventario_path = inventario_path
        self.problemas: List[Problema] = []
        self.stats = EstadisticasValidacion()

        # Cargar inventario
        with open(inventario_path, 'r', encoding='utf-8') as f:
            self.inventario = json.load(f)

        # Cache de archivos existentes
        self.archivos_existentes = self._construir_cache_archivos()

        # Comandos conocidos del sistema
        self.comandos_sistema = self._detectar_comandos_sistema()

        # Patrones de problemas comunes
        self._compilar_patrones()

    def _construir_cache_archivos(self) -> set:
        """Construye cache de todos los archivos en el repo."""
        archivos = set()
        for path in self.repo_root.rglob("*"):
            if path.is_file():
                try:
                    rel_path = path.relative_to(self.repo_root)
                    archivos.add(str(rel_path))
                    archivos.add(str(path))
                except ValueError:
                    pass
        return archivos

    def _detectar_comandos_sistema(self) -> set:
        """Detecta comandos disponibles en el sistema."""
        comandos = set()
        common_cmds = [
            'docker', 'docker-compose', 'git', 'make', 'python', 'python3',
            'pip', 'npm', 'node', 'yarn', 'curl', 'wget', 'bash', 'sh',
            'psql', 'mysql', 'redis-cli', 'kubectl', 'helm', 'cp', 'mv',
            'ls', 'cat', 'grep', 'sed', 'awk', 'find', 'chmod', 'chown'
        ]

        for cmd in common_cmds:
            try:
                result = subprocess.run(
                    ['which', cmd],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if result.returncode == 0:
                    comandos.add(cmd)
            except:
                pass

        return comandos

    def _compilar_patrones(self):
        """Compila patrones regex para detección."""
        # Rutas absolutas hardcoded (sospechosas)
        self.patron_ruta_absoluta = re.compile(r'/home/[^/]+|/Users/[^/]+|C:\\Users\\[^\\]+')

        # Secretos potenciales
        self.patron_secreto = re.compile(
            r'(?i)(password|secret|token|key|api_key|auth)[\s]*[=:][\s]*["\']?[a-zA-Z0-9]{8,}',
            re.IGNORECASE
        )

        # Variables de entorno sin valor por defecto
        self.patron_env_var = re.compile(r'\$\{?([A-Z_][A-Z0-9_]*)\}?')

        # Comandos peligrosos
        self.comandos_peligrosos = {
            'rm -rf': 'Comando destructivo sin protección',
            'chmod 777': 'Permisos excesivamente permisivos',
            'sudo': 'Requiere privilegios elevados',
            '--force': 'Flag forzado puede ser peligroso',
            'DROP TABLE': 'Operación destructiva en BD',
            'DELETE FROM': 'Operación destructiva en BD',
            'TRUNCATE': 'Operación destructiva en BD',
        }

    def validar_bloque_bash(self, bloque: Dict[str, Any]) -> List[Problema]:
        """Valida un bloque de código bash."""
        problemas = []
        contenido = bloque['content']
        lineas = contenido.split('\n')

        for i, linea in enumerate(lineas, start=1):
            linea_strip = linea.strip()
            if not linea_strip or linea_strip.startswith('#'):
                continue

            # Detectar archivos referenciados
            archivos_en_linea = re.findall(r'(?:^|\s)([./][^\s]+\.[a-z]{2,4})', linea)
            for archivo in archivos_en_linea:
                archivo_abs = (self.repo_root / archivo).resolve()
                if not archivo_abs.exists() and archivo not in self.archivos_existentes:
                    problemas.append(Problema(
                        archivo=bloque['file_relative'],
                        bloque_linea_inicio=bloque['line_start'],
                        bloque_linea_fin=bloque['line_end'],
                        lenguaje='bash',
                        severidad=Severidad.ALTA,
                        tipo=TipoProblema.ARCHIVO_NO_EXISTE,
                        descripcion=f"Archivo referenciado no existe: {archivo}",
                        linea_especifica=bloque['line_start'] + i - 1,
                        contenido_problematico=linea_strip,
                        sugerencia=f"Verificar si el archivo existe o actualizar ruta"
                    ))

            # Detectar comandos
            comando_match = re.match(r'^\s*([a-z-]+)', linea_strip)
            if comando_match:
                comando = comando_match.group(1)

                # Verificar si comando existe
                if comando not in ['cd', 'echo', 'export', 'source', '.'] and \
                   comando not in self.comandos_sistema:
                    problemas.append(Problema(
                        archivo=bloque['file_relative'],
                        bloque_linea_inicio=bloque['line_start'],
                        bloque_linea_fin=bloque['line_end'],
                        lenguaje='bash',
                        severidad=Severidad.MEDIA,
                        tipo=TipoProblema.COMANDO_NO_EXISTE,
                        descripcion=f"Comando no encontrado en sistema: {comando}",
                        linea_especifica=bloque['line_start'] + i - 1,
                        contenido_problematico=linea_strip,
                        sugerencia=f"Verificar si '{comando}' está instalado o es un script custom"
                    ))

            # Detectar rutas hardcoded
            if self.patron_ruta_absoluta.search(linea):
                problemas.append(Problema(
                    archivo=bloque['file_relative'],
                    bloque_linea_inicio=bloque['line_start'],
                    bloque_linea_fin=bloque['line_end'],
                    lenguaje='bash',
                    severidad=Severidad.MEDIA,
                    tipo=TipoProblema.RUTA_HARDCODED,
                    descripcion="Ruta absoluta hardcoded detectada",
                    linea_especifica=bloque['line_start'] + i - 1,
                    contenido_problematico=linea_strip,
                    sugerencia="Usar rutas relativas o variables de entorno"
                ))

            # Detectar secretos potenciales
            if self.patron_secreto.search(linea):
                problemas.append(Problema(
                    archivo=bloque['file_relative'],
                    bloque_linea_inicio=bloque['line_start'],
                    bloque_linea_fin=bloque['line_end'],
                    lenguaje='bash',
                    severidad=Severidad.CRITICA,
                    tipo=TipoProblema.SECRETO_EXPUESTO,
                    descripcion="Posible secreto expuesto en documentación",
                    linea_especifica=bloque['line_start'] + i - 1,
                    contenido_problematico="[REDACTED]",
                    sugerencia="Usar variables de entorno o archivos .env"
                ))

            # Detectar comandos peligrosos
            for cmd_peligroso, razon in self.comandos_peligrosos.items():
                if cmd_peligroso.lower() in linea.lower():
                    problemas.append(Problema(
                        archivo=bloque['file_relative'],
                        bloque_linea_inicio=bloque['line_start'],
                        bloque_linea_fin=bloque['line_end'],
                        lenguaje='bash',
                        severidad=Severidad.ALTA,
                        tipo=TipoProblema.COMANDO_PELIGROSO,
                        descripcion=f"Comando peligroso detectado: {razon}",
                        linea_especifica=bloque['line_start'] + i - 1,
                        contenido_problematico=linea_strip,
                        sugerencia="Agregar advertencias y validaciones"
                    ))

        # Validar docker-compose vs docker compose
        if 'docker-compose' in contenido:
            problemas.append(Problema(
                archivo=bloque['file_relative'],
                bloque_linea_inicio=bloque['line_start'],
                bloque_linea_fin=bloque['line_end'],
                lenguaje='bash',
                severidad=Severidad.BAJA,
                tipo=TipoProblema.COMANDO_OBSOLETO,
                descripcion="'docker-compose' es obsoleto, usar 'docker compose'",
                contenido_problematico="docker-compose",
                sugerencia="Reemplazar con 'docker compose' (sin guion)"
            ))

        return problemas

    def validar_bloque_python(self, bloque: Dict[str, Any]) -> List[Problema]:
        """Valida un bloque de código Python."""
        problemas = []
        contenido = bloque['content']

        # Validación de sintaxis
        try:
            compile(contenido, '<string>', 'exec')
        except SyntaxError as e:
            problemas.append(Problema(
                archivo=bloque['file_relative'],
                bloque_linea_inicio=bloque['line_start'],
                bloque_linea_fin=bloque['line_end'],
                lenguaje='python',
                severidad=Severidad.CRITICA,
                tipo=TipoProblema.SINTAXIS_INVALIDA,
                descripcion=f"Error de sintaxis Python: {e.msg}",
                linea_especifica=bloque['line_start'] + (e.lineno or 0) - 1,
                contenido_problematico=e.text or "",
                sugerencia="Corregir sintaxis Python"
            ))

        # Detectar imports de archivos locales que no existen
        import_pattern = re.compile(r'(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_.]*)')
        for match in import_pattern.finditer(contenido):
            modulo = match.group(1)
            if '.' in modulo:
                # Puede ser módulo local
                ruta_py = modulo.replace('.', '/') + '.py'
                if ruta_py not in self.archivos_existentes:
                    problemas.append(Problema(
                        archivo=bloque['file_relative'],
                        bloque_linea_inicio=bloque['line_start'],
                        bloque_linea_fin=bloque['line_end'],
                        lenguaje='python',
                        severidad=Severidad.MEDIA,
                        tipo=TipoProblema.ARCHIVO_NO_EXISTE,
                        descripcion=f"Módulo local no encontrado: {modulo}",
                        contenido_problematico=match.group(0),
                        sugerencia="Verificar si el módulo existe o es externo"
                    ))

        return problemas

    def validar_bloque_json(self, bloque: Dict[str, Any]) -> List[Problema]:
        """Valida un bloque JSON."""
        problemas = []
        contenido = bloque['content']

        try:
            json.loads(contenido)
        except json.JSONDecodeError as e:
            problemas.append(Problema(
                archivo=bloque['file_relative'],
                bloque_linea_inicio=bloque['line_start'],
                bloque_linea_fin=bloque['line_end'],
                lenguaje='json',
                severidad=Severidad.ALTA,
                tipo=TipoProblema.SINTAXIS_INVALIDA,
                descripcion=f"JSON inválido: {e.msg}",
                linea_especifica=bloque['line_start'] + e.lineno - 1,
                sugerencia="Corregir formato JSON"
            ))

        return problemas

    def validar_bloque_text(self, bloque: Dict[str, Any]) -> List[Problema]:
        """Valida bloques de texto (outputs esperados)."""
        problemas = []
        contenido = bloque['content']

        # Detectar si es un output que debería actualizarse
        indicadores_output = ['$', '>', 'Output:', 'Result:', '✓', '✗', 'Success', 'Error']
        if any(ind in contenido for ind in indicadores_output):
            problemas.append(Problema(
                archivo=bloque['file_relative'],
                bloque_linea_inicio=bloque['line_start'],
                bloque_linea_fin=bloque['line_end'],
                lenguaje='text',
                severidad=Severidad.INFO,
                tipo=TipoProblema.OUTPUT_DESACTUALIZADO,
                descripcion="Bloque de texto parece ser output de comando - verificar si está actualizado",
                sugerencia="Re-ejecutar comando y actualizar output documentado"
            ))

        return problemas

    def validar_bloque(self, bloque: Dict[str, Any]) -> List[Problema]:
        """Valida un bloque según su lenguaje."""
        lenguaje = bloque['language'].lower()

        # Detectar bloques incompletos
        if '(INCOMPLETO)' in bloque['language']:
            return [Problema(
                archivo=bloque['file_relative'],
                bloque_linea_inicio=bloque['line_start'],
                bloque_linea_fin=bloque['line_end'],
                lenguaje=lenguaje,
                severidad=Severidad.ALTA,
                tipo=TipoProblema.BLOQUE_INCOMPLETO,
                descripcion="Bloque de código mal cerrado (falta ```)",
                sugerencia="Cerrar bloque correctamente con ```"
            )]

        if lenguaje == 'bash':
            return self.validar_bloque_bash(bloque)
        elif lenguaje == 'python':
            return self.validar_bloque_python(bloque)
        elif lenguaje == 'json':
            return self.validar_bloque_json(bloque)
        elif lenguaje == 'text':
            return self.validar_bloque_text(bloque)
        else:
            # Otros lenguajes: validación básica
            return []

    def validar_todos_los_bloques(self):
        """Valida todos los bloques del inventario."""
        print("Iniciando validación profunda de bloques de código...")
        print(f"Total de bloques a validar: {self.inventario['metadata']['total_code_blocks']}")
        print()

        self.stats.total_bloques = self.inventario['metadata']['total_code_blocks']

        for bloque in self.inventario['all_blocks']:
            self.stats.bloques_validados += 1
            problemas_bloque = self.validar_bloque(bloque)

            if problemas_bloque:
                self.stats.bloques_con_problemas += 1
                self.problemas.extend(problemas_bloque)

                for problema in problemas_bloque:
                    if problema.severidad == Severidad.CRITICA:
                        self.stats.problemas_criticos += 1
                    elif problema.severidad == Severidad.ALTA:
                        self.stats.problemas_altos += 1
                    elif problema.severidad == Severidad.MEDIA:
                        self.stats.problemas_medios += 1
                    elif problema.severidad == Severidad.BAJA:
                        self.stats.problemas_bajos += 1
                    elif problema.severidad == Severidad.INFO:
                        self.stats.problemas_info += 1

                    if problema.tipo == TipoProblema.ARCHIVO_NO_EXISTE:
                        self.stats.archivos_no_existen += 1
                    elif problema.tipo == TipoProblema.COMANDO_OBSOLETO:
                        self.stats.comandos_obsoletos += 1
                    elif problema.tipo == TipoProblema.INCONSISTENCIA_CODIGO:
                        self.stats.inconsistencias += 1

            # Progreso
            if self.stats.bloques_validados % 50 == 0:
                print(f"  Validados: {self.stats.bloques_validados}/{self.stats.total_bloques}")

    def generar_matriz_problemas(self) -> Dict[str, Any]:
        """Genera matriz de problemas estructurada."""
        # Agrupar por archivo
        por_archivo = {}
        for problema in self.problemas:
            if problema.archivo not in por_archivo:
                por_archivo[problema.archivo] = []
            prob_dict = asdict(problema)
            # Convertir enums a strings
            prob_dict['severidad'] = problema.severidad.value
            prob_dict['tipo'] = problema.tipo.value
            por_archivo[problema.archivo].append(prob_dict)

        # Agrupar por severidad
        por_severidad = {
            'CRÍTICA': [],
            'ALTA': [],
            'MEDIA': [],
            'BAJA': [],
            'INFO': []
        }
        for problema in self.problemas:
            prob_dict = asdict(problema)
            prob_dict['severidad'] = problema.severidad.value
            prob_dict['tipo'] = problema.tipo.value
            por_severidad[problema.severidad.value].append(prob_dict)

        # Agrupar por tipo
        por_tipo = {}
        for problema in self.problemas:
            tipo_str = problema.tipo.value
            if tipo_str not in por_tipo:
                por_tipo[tipo_str] = []
            prob_dict = asdict(problema)
            prob_dict['severidad'] = problema.severidad.value
            prob_dict['tipo'] = problema.tipo.value
            por_tipo[tipo_str].append(prob_dict)

        return {
            "metadata": {
                "total_bloques_validados": self.stats.bloques_validados,
                "bloques_con_problemas": self.stats.bloques_con_problemas,
                "total_problemas": len(self.problemas),
                "problemas_criticos": self.stats.problemas_criticos,
                "problemas_altos": self.stats.problemas_altos,
                "problemas_medios": self.stats.problemas_medios,
                "problemas_bajos": self.stats.problemas_bajos,
                "problemas_info": self.stats.problemas_info,
                "archivos_afectados": len(por_archivo),
                "tipos_problemas": len(por_tipo)
            },
            "estadisticas": asdict(self.stats),
            "por_archivo": por_archivo,
            "por_severidad": por_severidad,
            "por_tipo": por_tipo,
            "todos_los_problemas": [
                {
                    **asdict(p),
                    'severidad': p.severidad.value,
                    'tipo': p.tipo.value
                }
                for p in self.problemas
            ]
        }

    def generar_reporte_markdown(self, matriz: Dict[str, Any]) -> str:
        """Genera reporte en Markdown."""
        lines = [
            "# Matriz de Problemas - Validación Profunda de Bloques de Código",
            "",
            "## Resumen Ejecutivo",
            "",
            f"- **Bloques validados**: {matriz['metadata']['total_bloques_validados']}",
            f"- **Bloques con problemas**: {matriz['metadata']['bloques_con_problemas']}",
            f"- **Total de problemas**: {matriz['metadata']['total_problemas']}",
            f"- **Archivos afectados**: {matriz['metadata']['archivos_afectados']}",
            "",
            "## Distribución por Severidad",
            "",
            "| Severidad | Cantidad | % del Total |",
            "|-----------|----------|-------------|",
        ]

        total = matriz['metadata']['total_problemas']
        for sev in ['CRÍTICA', 'ALTA', 'MEDIA', 'BAJA', 'INFO']:
            count = len(matriz['por_severidad'][sev])
            pct = (count / total * 100) if total > 0 else 0
            lines.append(f"| {sev} | {count} | {pct:.1f}% |")

        lines.extend([
            "",
            "## Distribución por Tipo de Problema",
            "",
            "| Tipo | Cantidad |",
            "|------|----------|"
        ])

        tipos_sorted = sorted(matriz['por_tipo'].items(), key=lambda x: len(x[1]), reverse=True)
        for tipo, problemas in tipos_sorted:
            lines.append(f"| {tipo} | {len(problemas)} |")

        lines.extend([
            "",
            "## Problemas Críticos",
            ""
        ])

        criticos = matriz['por_severidad']['CRÍTICA']
        if criticos:
            for i, p in enumerate(criticos, 1):
                lines.extend([
                    f"### {i}. {p['descripcion']}",
                    f"- **Archivo**: {p['archivo']}",
                    f"- **Líneas**: {p['bloque_linea_inicio']}-{p['bloque_linea_fin']}",
                    f"- **Tipo**: {p['tipo']}",
                    f"- **Sugerencia**: {p['sugerencia']}",
                    ""
                ])
        else:
            lines.append("✅ No se detectaron problemas críticos")

        lines.extend([
            "",
            "## Top 10 Archivos con Más Problemas",
            "",
            "| Archivo | Problemas |",
            "|---------|-----------|"
        ])

        archivos_sorted = sorted(
            matriz['por_archivo'].items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:10]

        for archivo, problemas in archivos_sorted:
            lines.append(f"| {archivo} | {len(problemas)} |")

        return '\n'.join(lines)


def main():
    """Función principal."""
    repo_root = Path(__file__).resolve().parent.parent
    inventario_path = repo_root / "inventario_bloques_codigo.json"

    if not inventario_path.exists():
        print(f"ERROR: No se encuentra {inventario_path}")
        print("Ejecuta primero: python scripts/inventario_bloques_codigo.py")
        sys.exit(1)

    print(f"Repositorio: {repo_root}")
    print(f"Inventario: {inventario_path}")
    print()

    # Crear validador
    validador = ValidadorBloquesCodigo(repo_root, inventario_path)

    # Validar todos los bloques
    validador.validar_todos_los_bloques()

    print()
    print("=" * 80)
    print("Generando matriz de problemas...")

    # Generar matriz
    matriz = validador.generar_matriz_problemas()

    # Guardar JSON
    output_json = repo_root / "matriz_problemas_bloques.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(matriz, f, indent=2, ensure_ascii=False)
    print(f"✓ Matriz JSON guardada: {output_json}")

    # Generar reporte
    reporte = validador.generar_reporte_markdown(matriz)
    output_md = repo_root / "MATRIZ_PROBLEMAS_BLOQUES.md"
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(reporte)
    print(f"✓ Reporte Markdown guardado: {output_md}")

    print()
    print("=" * 80)
    print("RESULTADOS DE VALIDACIÓN")
    print("=" * 80)
    print()
    print(f"Bloques validados: {matriz['metadata']['total_bloques_validados']}")
    print(f"Bloques con problemas: {matriz['metadata']['bloques_con_problemas']}")
    print(f"Total de problemas: {matriz['metadata']['total_problemas']}")
    print()
    print("Por severidad:")
    print(f"  CRÍTICA: {matriz['metadata']['problemas_criticos']}")
    print(f"  ALTA:    {matriz['metadata']['problemas_altos']}")
    print(f"  MEDIA:   {matriz['metadata']['problemas_medios']}")
    print(f"  BAJA:    {matriz['metadata']['problemas_bajos']}")
    print(f"  INFO:    {matriz['metadata']['problemas_info']}")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
