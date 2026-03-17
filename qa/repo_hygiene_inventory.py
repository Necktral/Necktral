#!/usr/bin/env python3
"""Genera inventario ejecutable y reporte de duplicados para reorganización de repo."""

from __future__ import annotations

import argparse
import csv
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

TARGET_ROOTS = (
    "login_module/src",
    "modulos",
    "frontend/src",
    "qa",
    "docs",
    "backend",
)

EXCLUDED_SUBTREES = (
    "frontend/node_modules/",
    "frontend/dist/",
    "frontend/.quasar/",
    "system_wis/",
    "docs/operacion/evidencia/",
    "simulacion/reports/",
    ".git/",
)

GENERATED_TOKENS = (
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
)

GENERATED_FILES = (
    ".coverage",
    ".DS_Store",
)

OWNERS_BY_PREFIX = (
    ("login_module/src/apps/accounting", "owner.accounting"),
    ("login_module/src/apps/iam", "owner.iam"),
    ("login_module/src/apps/rbac", "owner.rbac"),
    ("login_module/src/apps/audit", "owner.audit"),
    ("login_module/src/apps/org", "owner.org"),
    ("login_module/src/apps/hr", "owner.hr"),
    ("login_module/src/apps/payments", "owner.payments"),
    ("login_module/src/apps/integration", "owner.integration"),
    ("login_module/src/apps/sync_engine", "owner.sync"),
    ("login_module/src/apps", "owner.backend"),
    ("login_module/src/config", "owner.platform"),
    ("modulos/facturacion", "owner.billing"),
    ("modulos/inventarios", "owner.inventory"),
    ("modulos/estacion_servicios", "owner.fuel"),
    ("modulos/compras", "owner.procurement"),
    ("frontend/src", "owner.frontend"),
    ("qa", "owner.qa"),
    ("docs", "owner.architecture"),
    ("backend", "owner.platform"),
)

TEXT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".vue",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".md",
    ".txt",
    ".sh",
    ".env",
    ".sql",
    ".css",
    ".scss",
    ".html",
}


@dataclass(frozen=True)
class InventoryRow:
    ruta: str
    tipo: str
    estado: str
    accion: str
    riesgo: str
    justificacion: str
    owner: str


def is_excluded(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in EXCLUDED_SUBTREES)


def owner_for(path: str) -> str:
    for prefix, owner in OWNERS_BY_PREFIX:
        if path.startswith(prefix):
            return owner
    return "owner.unassigned"


def classify(path: str) -> InventoryRow | None:
    normalized = path.replace("\\", "/")
    if is_excluded(normalized):
        return None

    if any(token in normalized for token in GENERATED_TOKENS):
        return InventoryRow(
            ruta=normalized,
            tipo="artefacto-generado",
            estado="residuo",
            accion="DELETE",
            riesgo="bajo",
            justificacion="cache/artefacto no canónico, re-generable",
            owner=owner_for(normalized),
        )

    if normalized.endswith(".pyc") or normalized.endswith(".pyo") or normalized.endswith(".pyd"):
        return InventoryRow(
            ruta=normalized,
            tipo="artefacto-generado",
            estado="residuo",
            accion="DELETE",
            riesgo="bajo",
            justificacion="binario compilado no versionable",
            owner=owner_for(normalized),
        )

    name = Path(normalized).name
    if name in GENERATED_FILES or name == "CACHEDIR.TAG":
        return InventoryRow(
            ruta=normalized,
            tipo="artefacto-generado",
            estado="residuo",
            accion="DELETE",
            riesgo="bajo",
            justificacion="resultado local no contractual",
            owner=owner_for(normalized),
        )

    if normalized.startswith("backend/"):
        return InventoryRow(
            ruta=normalized,
            tipo="legacy-local",
            estado="legacy",
            accion="LEGACY",
            riesgo="medio",
            justificacion="árbol legado fuera del backend canónico",
            owner=owner_for(normalized),
        )

    suffix = Path(normalized).suffix.lower()
    if suffix in TEXT_EXTENSIONS or Path(normalized).name in {"Dockerfile", "Makefile"}:
        tipo = "codigo-fuente" if normalized.startswith(
            ("login_module/src/", "modulos/", "frontend/src/", "qa/")
        ) else "documentacion"
        return InventoryRow(
            ruta=normalized,
            tipo=tipo,
            estado="activo",
            accion="KEEP",
            riesgo="medio" if tipo == "codigo-fuente" else "bajo",
            justificacion="software/documentación propia en superficie canónica",
            owner=owner_for(normalized),
        )

    return InventoryRow(
        ruta=normalized,
        tipo="soporte",
        estado="activo",
        accion="KEEP",
        riesgo="bajo",
        justificacion="archivo de soporte no generado",
        owner=owner_for(normalized),
    )


def iter_target_files(root: Path) -> Iterable[str]:
    for rel in TARGET_ROOTS:
        start = root / rel
        if not start.exists():
            continue
        for path in start.rglob("*"):
            if not path.is_file():
                continue
            yield path.relative_to(root).as_posix()


def sha256_file(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_EXTENSIONS and path.name not in {"Makefile", "Dockerfile"}:
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def write_inventory_csv(rows: list[InventoryRow], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ruta", "tipo", "estado", "accion", "riesgo", "justificacion", "owner"])
        for row in rows:
            writer.writerow(
                [row.ruta, row.tipo, row.estado, row.accion, row.riesgo, row.justificacion, row.owner]
            )


def write_duplicates_csv(rows: list[InventoryRow], output_csv: Path) -> None:
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row.accion not in {"KEEP", "LEGACY"}:
            continue
        digest = sha256_file(ROOT / row.ruta)
        if digest is None:
            continue
        groups[digest].append(row.ruta)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["hash", "conteo", "canonical_path", "duplicate_path", "status"])
        for digest, paths in sorted(groups.items(), key=lambda item: len(item[1]), reverse=True):
            if len(paths) <= 1:
                continue
            canonical = sorted(paths)[0]
            for duplicate in sorted(paths):
                status = "canonical" if duplicate == canonical else "duplicate"
                writer.writerow([digest, len(paths), canonical, duplicate, status])


def write_summary_md(rows: list[InventoryRow], duplicates_csv: Path, summary_md: Path) -> None:
    by_action = Counter(row.accion for row in rows)
    by_type = Counter(row.tipo for row in rows)
    by_owner = Counter(row.owner for row in rows)

    duplicate_groups = 0
    duplicate_rows = 0
    if duplicates_csv.exists():
        with duplicates_csv.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            seen = set()
            for row in reader:
                duplicate_rows += 1
                seen.add(row["hash"])
            duplicate_groups = len(seen)

    summary_md.parent.mkdir(parents=True, exist_ok=True)
    summary_md.write_text(
        "\n".join(
            [
                "# Matriz de Inventario Ejecutable v1.1",
                "",
                "Fecha: 2026-03-17",
                "",
                "## Cobertura",
                "- Rutas auditadas: `login_module/src`, `modulos`, `frontend/src`, `qa`, `docs`, `backend`.",
                "- Exclusiones: terceros/artefactos masivos (`node_modules`, `system_wis`, evidencias operativas, outputs de build).",
                "",
                "## Resumen cuantitativo",
                f"- Filas inventariadas: **{len(rows)}**.",
                f"- `KEEP`: **{by_action.get('KEEP', 0)}**.",
                f"- `LEGACY`: **{by_action.get('LEGACY', 0)}**.",
                f"- `DELETE`: **{by_action.get('DELETE', 0)}**.",
                "",
                "## Distribución por tipo",
                *(f"- `{k}`: **{v}**" for k, v in sorted(by_type.items())),
                "",
                "## Distribución por owner",
                *(f"- `{k}`: **{v}**" for k, v in sorted(by_owner.items())),
                "",
                "## Duplicados por hash",
                f"- Grupos detectados: **{duplicate_groups}**.",
                f"- Filas en reporte de duplicados: **{duplicate_rows}**.",
                "",
                "## Checklist por lotes",
                "- Lote A (Documentación contractual): crear/normalizar `CONTRACT_PACK_v1.1` y referencias cruzadas.",
                "- Lote B (Canónico backend): declarar `login_module/` como raíz oficial y `backend/` como legacy local.",
                "- Lote C (Limpieza conservadora): eliminar residuos `DELETE` confirmados del árbol legacy y caches generados.",
                "- Lote D (Guardas): activar chequeo de higiene en QA para evitar reintroducción de residuos/duplicados.",
                "",
                "## Archivos generados",
                "- `docs/repo_higiene/inventario_software_v1.1.csv`",
                "- `docs/repo_higiene/duplicados_software_v1.1.csv`",
                "- `docs/repo_higiene/resumen_reorganizacion_v1.1.md`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventario y duplicados para higiene de repo.")
    parser.add_argument(
        "--inventory-csv",
        default="docs/repo_higiene/inventario_software_v1.1.csv",
        help="Ruta de salida del inventario CSV",
    )
    parser.add_argument(
        "--duplicates-csv",
        default="docs/repo_higiene/duplicados_software_v1.1.csv",
        help="Ruta de salida del reporte de duplicados CSV",
    )
    parser.add_argument(
        "--summary-md",
        default="docs/repo_higiene/resumen_reorganizacion_v1.1.md",
        help="Ruta de salida del resumen Markdown",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows: list[InventoryRow] = []

    for rel_path in sorted(iter_target_files(ROOT)):
        row = classify(rel_path)
        if row is None:
            continue
        rows.append(row)

    inventory_csv = ROOT / args.inventory_csv
    duplicates_csv = ROOT / args.duplicates_csv
    summary_md = ROOT / args.summary_md

    write_inventory_csv(rows, inventory_csv)
    write_duplicates_csv(rows, duplicates_csv)
    write_summary_md(rows, duplicates_csv, summary_md)

    print(f"[repo-hygiene] inventory_rows={len(rows)}")
    print(f"[repo-hygiene] inventory_csv={inventory_csv.relative_to(ROOT)}")
    print(f"[repo-hygiene] duplicates_csv={duplicates_csv.relative_to(ROOT)}")
    print(f"[repo-hygiene] summary_md={summary_md.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
