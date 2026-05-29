#!/usr/bin/env python3
"""
Inventario de bloques de código en documentación Markdown.

Este script escanea todos los archivos .md en el repositorio y genera un inventario
detallado de todos los bloques de código encontrados, incluyendo:
- Ubicación (archivo, línea)
- Lenguaje del bloque
- Contenido del bloque
- Longitud (líneas)

El inventario se genera en formato JSON para procesamiento posterior.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass, asdict
import sys


@dataclass
class CodeBlock:
    """Representa un bloque de código encontrado en documentación."""
    file_path: str
    line_start: int
    line_end: int
    language: str
    content: str
    lines_count: int
    file_relative: str


class DocumentationInventory:
    """Inventario de bloques de código en documentación."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.code_blocks: List[CodeBlock] = []

    def scan_markdown_file(self, file_path: Path) -> List[CodeBlock]:
        """Escanea un archivo markdown y extrae todos los bloques de código."""
        blocks = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Error leyendo {file_path}: {e}", file=sys.stderr)
            return blocks

        in_code_block = False
        current_block_start = 0
        current_language = ""
        current_content = []

        for i, line in enumerate(lines, start=1):
            # Detectar inicio de bloque de código con ```
            if line.strip().startswith('```'):
                if not in_code_block:
                    # Inicio de bloque
                    in_code_block = True
                    current_block_start = i
                    # Extraer lenguaje (si existe)
                    lang_match = line.strip()[3:].strip()
                    current_language = lang_match if lang_match else "plain"
                    current_content = []
                else:
                    # Fin de bloque
                    in_code_block = False

                    # Crear bloque
                    block = CodeBlock(
                        file_path=str(file_path),
                        line_start=current_block_start,
                        line_end=i,
                        language=current_language,
                        content=''.join(current_content),
                        lines_count=len(current_content),
                        file_relative=str(file_path.relative_to(self.repo_root))
                    )
                    blocks.append(block)

                    # Reset
                    current_block_start = 0
                    current_language = ""
                    current_content = []
            elif in_code_block:
                # Dentro de un bloque de código
                current_content.append(line)

        # Si terminamos dentro de un bloque (bloque mal cerrado)
        if in_code_block:
            block = CodeBlock(
                file_path=str(file_path),
                line_start=current_block_start,
                line_end=len(lines),
                language=current_language + " (INCOMPLETO)",
                content=''.join(current_content),
                lines_count=len(current_content),
                file_relative=str(file_path.relative_to(self.repo_root))
            )
            blocks.append(block)

        return blocks

    def scan_all_documentation(self) -> None:
        """Escanea todos los archivos .md en el repositorio."""
        # Buscar todos los archivos .md
        md_files = list(self.repo_root.rglob("*.md"))

        print(f"Escaneando {len(md_files)} archivos markdown...")

        for md_file in sorted(md_files):
            blocks = self.scan_markdown_file(md_file)
            self.code_blocks.extend(blocks)
            if blocks:
                print(f"  {md_file.relative_to(self.repo_root)}: {len(blocks)} bloques")

    def generate_report(self) -> Dict[str, Any]:
        """Genera reporte consolidado del inventario."""
        # Agrupar por archivo
        by_file = {}
        for block in self.code_blocks:
            if block.file_relative not in by_file:
                by_file[block.file_relative] = []
            by_file[block.file_relative].append(asdict(block))

        # Agrupar por lenguaje
        by_language = {}
        for block in self.code_blocks:
            lang = block.language
            if lang not in by_language:
                by_language[lang] = []
            by_language[lang].append(asdict(block))

        # Estadísticas
        total_blocks = len(self.code_blocks)
        total_lines = sum(block.lines_count for block in self.code_blocks)
        files_with_code = len(by_file)
        languages = list(by_language.keys())

        return {
            "metadata": {
                "total_code_blocks": total_blocks,
                "total_code_lines": total_lines,
                "files_with_code_blocks": files_with_code,
                "languages_found": sorted(languages),
                "languages_count": len(languages)
            },
            "by_file": by_file,
            "by_language": {
                lang: {
                    "count": len(blocks),
                    "total_lines": sum(b["lines_count"] for b in blocks),
                    "blocks": blocks
                }
                for lang, blocks in by_language.items()
            },
            "all_blocks": [asdict(block) for block in self.code_blocks]
        }

    def generate_summary_markdown(self) -> str:
        """Genera un resumen en formato markdown."""
        report = self.generate_report()
        metadata = report["metadata"]

        lines = [
            "# Inventario de Bloques de Código en Documentación",
            "",
            "## Resumen Ejecutivo",
            "",
            f"- **Total de bloques de código**: {metadata['total_code_blocks']}",
            f"- **Total de líneas de código**: {metadata['total_code_lines']}",
            f"- **Archivos con bloques**: {metadata['files_with_code_blocks']}",
            f"- **Lenguajes encontrados**: {metadata['languages_count']}",
            "",
            "## Distribución por Lenguaje",
            ""
        ]

        # Ordenar lenguajes por cantidad de bloques
        lang_stats = [
            (lang, data["count"], data["total_lines"])
            for lang, data in report["by_language"].items()
        ]
        lang_stats.sort(key=lambda x: x[1], reverse=True)

        lines.append("| Lenguaje | Bloques | Líneas |")
        lines.append("|----------|---------|--------|")
        for lang, count, total_lines in lang_stats:
            lines.append(f"| {lang} | {count} | {total_lines} |")

        lines.append("")
        lines.append("## Distribución por Archivo")
        lines.append("")

        # Ordenar archivos por cantidad de bloques
        file_stats = [
            (file_path, len(blocks))
            for file_path, blocks in report["by_file"].items()
        ]
        file_stats.sort(key=lambda x: x[1], reverse=True)

        lines.append("| Archivo | Bloques |")
        lines.append("|---------|---------|")
        for file_path, count in file_stats[:50]:  # Top 50
            lines.append(f"| {file_path} | {count} |")

        if len(file_stats) > 50:
            lines.append(f"| ... y {len(file_stats) - 50} más | ... |")

        lines.append("")
        lines.append("## Detalle por Archivo")
        lines.append("")

        for file_path in sorted(report["by_file"].keys()):
            blocks = report["by_file"][file_path]
            lines.append(f"### {file_path}")
            lines.append("")
            lines.append(f"Total de bloques: {len(blocks)}")
            lines.append("")

            for i, block in enumerate(blocks, 1):
                lines.append(f"#### Bloque {i} (líneas {block['line_start']}-{block['line_end']})")
                lines.append(f"- **Lenguaje**: `{block['language']}`")
                lines.append(f"- **Líneas**: {block['lines_count']}")
                lines.append("")

        return '\n'.join(lines)


def main():
    """Función principal."""
    # Determinar raíz del repositorio
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent

    print(f"Raíz del repositorio: {repo_root}")
    print()

    # Crear inventario
    inventory = DocumentationInventory(repo_root)

    # Escanear documentación
    inventory.scan_all_documentation()

    print()
    print("=" * 80)
    print("Generando reportes...")
    print()

    # Generar reporte JSON
    report = inventory.generate_report()
    output_json = repo_root / "inventario_bloques_codigo.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"✓ Reporte JSON guardado en: {output_json}")

    # Generar resumen markdown
    summary_md = inventory.generate_summary_markdown()
    output_md = repo_root / "inventario_bloques_codigo.md"
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(summary_md)
    print(f"✓ Resumen Markdown guardado en: {output_md}")

    # Mostrar resumen en consola
    print()
    print("=" * 80)
    print("RESUMEN DEL INVENTARIO")
    print("=" * 80)
    print()
    metadata = report["metadata"]
    print(f"Total de bloques de código: {metadata['total_code_blocks']}")
    print(f"Total de líneas de código: {metadata['total_code_lines']}")
    print(f"Archivos con bloques: {metadata['files_with_code_blocks']}")
    print(f"Lenguajes encontrados: {metadata['languages_count']}")
    print()
    print("Lenguajes detectados:")
    for lang in sorted(metadata['languages_found']):
        count = len(report['by_language'][lang]['blocks'])
        lines = report['by_language'][lang]['total_lines']
        print(f"  - {lang}: {count} bloques, {lines} líneas")
    print()
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
