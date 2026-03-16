#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class DomainSpec:
    name: str
    path_prefixes: tuple[str, ...]


DOMAIN_SPECS: tuple[DomainSpec, ...] = (
    DomainSpec("sync_engine", ("src/apps/sync_engine/",)),
    DomainSpec("iam", ("src/apps/iam/",)),
    DomainSpec("audit", ("src/apps/audit/",)),
    DomainSpec("rbac", ("src/apps/rbac/",)),
    DomainSpec("accounts", ("src/apps/accounts/",)),
    DomainSpec("integration", ("src/apps/integration/",)),
    DomainSpec("accounting", ("src/apps/accounting/",)),
    DomainSpec("billing", ("modulos/facturacion/",)),
    DomainSpec("inventory", ("modulos/inventarios/",)),
    DomainSpec("procurement", ("modulos/compras/",)),
)


def _normalize_file_path(path_value: str) -> str:
    normalized = path_value.replace("\\", "/")
    marker = "/login_module/"
    idx = normalized.find(marker)
    if idx >= 0:
        normalized = normalized[idx + len(marker) :]
    marker_src = "/src/"
    idx_src = normalized.find(marker_src)
    if idx_src >= 0:
        normalized = normalized[idx_src + 1 :]
    marker_mod = "/modulos/"
    idx_mod = normalized.find(marker_mod)
    if idx_mod >= 0:
        normalized = normalized[idx_mod + 1 :]
    return normalized.lstrip("/")


def _extract_domain(path_value: str) -> str | None:
    norm = _normalize_file_path(path_value)
    for spec in DOMAIN_SPECS:
        if any(norm.startswith(prefix) for prefix in spec.path_prefixes):
            return spec.name
    return None


def _candidate_paths(filename: str, sources: list[str]) -> list[str]:
    candidates: list[str] = [filename]
    if "/" in filename or "\\" in filename:
        return candidates
    for src in sources:
        src_text = str(src or "").strip()
        if not src_text:
            continue
        candidates.append(f"{src_text.rstrip('/')}/{filename}")
    return candidates


def _parse_coverage_xml(coverage_xml: Path) -> list[dict[str, Any]]:
    root = ET.fromstring(coverage_xml.read_text(encoding="utf-8"))
    sources = [str(node.text or "").strip() for node in root.findall("./sources/source")]
    rows: list[dict[str, Any]] = []
    for cls in root.findall(".//class"):
        filename = cls.attrib.get("filename", "")
        resolved_name = filename
        domain = None
        for candidate in _candidate_paths(filename, sources):
            found = _extract_domain(candidate)
            if found is not None:
                domain = found
                resolved_name = candidate
                break
        if domain is None:
            continue
        lines = cls.findall(".//line")
        valid = len(lines)
        covered = 0
        for ln in lines:
            try:
                hits = int(ln.attrib.get("hits", "0"))
            except ValueError:
                hits = 0
            if hits > 0:
                covered += 1
        rows.append(
            {
                "domain": domain,
                "filename": _normalize_file_path(resolved_name),
                "valid_lines": valid,
                "covered_lines": covered,
            }
        )
    return rows


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        domain = str(row["domain"])
        current = out.setdefault(domain, {"domain": domain, "valid_lines": 0, "covered_lines": 0, "file_count": 0})
        current["valid_lines"] += int(row["valid_lines"])
        current["covered_lines"] += int(row["covered_lines"])
        current["file_count"] += 1
    for current in out.values():
        valid = int(current["valid_lines"])
        covered = int(current["covered_lines"])
        pct = 0.0 if valid <= 0 else (covered / valid) * 100.0
        current["coverage_pct"] = round(pct, 2)
    return out


def _to_markdown(domains: list[dict[str, Any]]) -> str:
    lines = [
        "# Domain Coverage",
        "",
        "| Domain | Files | Covered Lines | Valid Lines | Coverage |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in domains:
        lines.append(
            f"| {row['domain']} | {row['file_count']} | {row['covered_lines']} | {row['valid_lines']} | {row['coverage_pct']}% |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera cobertura agregada por dominio/kernel.")
    parser.add_argument("--coverage-xml", required=True, help="Ruta al coverage.xml")
    parser.add_argument("--json-output", required=True, help="Salida JSON")
    parser.add_argument("--md-output", required=True, help="Salida Markdown")
    parser.add_argument(
        "--min-domain",
        action="append",
        default=[],
        help="Umbral por dominio, formato domain=pct (ej: audit=80). Repetible.",
    )
    args = parser.parse_args()

    rows = _parse_coverage_xml(Path(args.coverage_xml))
    agg = _aggregate(rows)
    ordered = sorted(agg.values(), key=lambda r: str(r["domain"]))
    min_domain: dict[str, float] = {}
    for raw in args.min_domain:
        if "=" not in raw:
            raise SystemExit(f"--min-domain inválido: {raw}")
        k, v = raw.split("=", 1)
        min_domain[k.strip()] = float(v.strip())

    checks: list[dict[str, Any]] = []
    status = "PASS"
    for domain, threshold in min_domain.items():
        row = agg.get(domain)
        pct = float(row["coverage_pct"]) if row else 0.0
        passed = pct >= threshold
        checks.append({"domain": domain, "threshold_pct": threshold, "coverage_pct": pct, "status": "PASS" if passed else "FAIL"})
        if not passed:
            status = "FAIL"

    payload = {
        "status": status,
        "coverage_xml": str(args.coverage_xml),
        "domains": ordered,
        "checks": checks,
    }
    Path(args.json_output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.md_output).write_text(_to_markdown(ordered), encoding="utf-8")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
