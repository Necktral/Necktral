#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from typing import Any

EXCLUDED_PATH_PARTS = (
    "node_modules/",
    "/dist/",
    "/.quasar/",
    "/docs/operacion/evidencia/",
    "/migrations/",
)

LANG_BY_EXT = {
    ".py": "python",
    ".ts": "typescript",
    ".js": "javascript",
    ".vue": "vue",
}

CRITICAL_MODULES: dict[str, tuple[str, ...]] = {
    "accounting_backend": ("backend/src/apps/accounting/",),
    "accounting_phase7_core": ("backend/src/apps/accounting/phase7.py",),
    "accounting_views_api": ("backend/src/apps/accounting/views.py",),
    "hr_employees_frontend": ("frontend/src/pages/HrEmployeesPage.vue",),
}

CRITICAL_FILE_POLICIES: dict[str, dict[str, Any]] = {
    "backend/src/apps/accounting/views.py": {
        "require_module_docstring": True,
        "required_symbol_docstrings": (
            "HealthView",
            "ChartOfAccountView",
            "_resolve_range_payload",
            "_serialize_intercompany",
        ),
        "min_annotation_lines": 10,
    },
    "backend/src/apps/accounting/phase7.py": {
        "require_module_docstring": True,
        "required_symbol_docstrings": (
            "get_or_create_accounting_config",
            "upsert_chart_of_accounts",
            "build_entry_lines_from_draft",
            "run_fx_revaluation",
        ),
        "min_annotation_lines": 10,
    },
    "frontend/src/pages/HrEmployeesPage.vue": {
        "min_annotation_lines": 12,
    },
}


def _run(cmd: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _safe_run(cmd: list[str], *, cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _is_excluded(path: str) -> bool:
    normalized = f"/{path}"
    return any(part in normalized for part in EXCLUDED_PATH_PARTS)


def _iter_tracked_files(repo_root: Path) -> list[Path]:
    out = _run(["git", "ls-files"], cwd=repo_root)
    files: list[Path] = []
    for raw in out.splitlines():
        path = raw.strip()
        if not path:
            continue
        if _is_excluded(path):
            continue
        ext = Path(path).suffix.lower()
        if ext not in LANG_BY_EXT:
            continue
        files.append(repo_root / path)
    return files


def _count_annotations(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    nonempty = 0
    comments = 0
    docstrings = 0

    ext = path.suffix.lower()
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        nonempty += 1

        if ext == ".py":
            if stripped.startswith("#"):
                comments += 1
            elif stripped.startswith('"""') or stripped.startswith("'''"):
                docstrings += 1
            continue

        if ext in {".ts", ".js", ".vue"}:
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                comments += 1
            elif ext == ".vue" and stripped.startswith("<!--"):
                comments += 1

    annotated = comments + docstrings
    density = (annotated / nonempty * 100.0) if nonempty else 0.0
    return {
        "nonempty_lines": int(nonempty),
        "comment_lines": int(comments),
        "docstring_lines": int(docstrings),
        "annotated_lines": int(annotated),
        "annotation_density_pct": round(density, 2),
    }


def _match_critical_modules(rel_path: str) -> list[str]:
    hits: list[str] = []
    for module_name, patterns in CRITICAL_MODULES.items():
        for pattern in patterns:
            if pattern.endswith("/") and rel_path.startswith(pattern):
                hits.append(module_name)
                break
            if rel_path == pattern:
                hits.append(module_name)
                break
    return hits


def _get_git_sync(repo_root: Path, *, fetch: bool) -> dict[str, Any]:
    if fetch:
        _safe_run(["git", "fetch", "--all", "--prune"], cwd=repo_root)

    branch = _run(["git", "branch", "--show-current"], cwd=repo_root)
    head_is_detached = not bool(branch)
    ci_event = (os.environ.get("GITHUB_EVENT_NAME") or "").strip() or "local"
    branch_source = "git"
    if not branch:
        env_branch = (os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME") or "").strip()
        if env_branch and env_branch.lower() != "merge":
            branch = env_branch
            branch_source = "env"
        else:
            branch = "HEAD"
            branch_source = "detached"

    head = _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    head_short = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
    head_date = _run(["git", "show", "-s", "--format=%ci", "HEAD"], cwd=repo_root)
    porcelain = _run(["git", "status", "--porcelain=v1"], cwd=repo_root)

    origin_ref = f"origin/{branch}" if branch not in {"", "HEAD"} else ""
    origin_exists = False
    if origin_ref:
        rc_origin, _, _ = _safe_run(["git", "show-ref", "--verify", f"refs/remotes/{origin_ref}"], cwd=repo_root)
        origin_exists = rc_origin == 0

    ahead_origin = behind_origin = 0
    if origin_exists:
        left_right = _run(["git", "rev-list", "--left-right", "--count", f"HEAD...{origin_ref}"], cwd=repo_root)
        left, right = left_right.split()
        ahead_origin = int(left)
        behind_origin = int(right)

    sync_origin = bool(origin_exists and not porcelain and ahead_origin == 0 and behind_origin == 0)
    sync_origin_mode = "strict"
    if ci_event == "pull_request" and head_is_detached:
        sync_origin_mode = "pr_detached_tolerant"

    origin_reason_code = "ORIGIN_SYNC_OK"
    if sync_origin_mode == "strict":
        if not origin_ref:
            origin_status = "WARN"
            origin_reason_code = "ORIGIN_REF_UNRESOLVED"
            origin_detail = "Rama local no resoluble (HEAD detached sin referencia de rama)."
        elif not origin_exists:
            origin_status = "WARN"
            origin_reason_code = "ORIGIN_REF_MISSING"
            origin_detail = f"No existe referencia remota para `{origin_ref}`."
        elif sync_origin:
            origin_status = "PASS"
            origin_reason_code = "ORIGIN_SYNC_OK"
            origin_detail = "Rama local en sync con remoto y árbol limpio."
        else:
            origin_status = "FAIL"
            origin_reason_code = "ORIGIN_OUT_OF_SYNC_OR_DIRTY"
            origin_detail = "Rama local no está en sync con remoto o árbol no está limpio."
    else:
        if not origin_ref:
            origin_status = "WARN"
            origin_reason_code = "PR_DETACHED_ORIGIN_REF_UNRESOLVED"
            origin_detail = "Contexto PR en HEAD detached sin referencia de rama resoluble."
        elif not origin_exists:
            origin_status = "WARN"
            origin_reason_code = "PR_DETACHED_ORIGIN_REF_MISSING"
            origin_detail = f"Contexto PR detached: no existe referencia remota para `{origin_ref}`."
        elif sync_origin:
            origin_status = "PASS"
            origin_reason_code = "ORIGIN_SYNC_OK"
            origin_detail = "Rama local en sync con remoto y árbol limpio."
        else:
            origin_status = "WARN"
            if porcelain:
                origin_reason_code = "PR_DETACHED_WORKTREE_DIRTY"
                origin_detail = "Contexto PR detached con árbol no limpio; revisar checkout del runner."
            else:
                origin_reason_code = "PR_DETACHED_MERGE_REF_NOT_SYNC"
                origin_detail = (
                    "Contexto PR detached (merge ref): comparación directa con rama remota no determinística."
                )

    rc_upstream, _, _ = _safe_run(["git", "show-ref", "--verify", "refs/remotes/upstream/master"], cwd=repo_root)
    upstream_exists = rc_upstream == 0
    ahead_upstream = behind_upstream = 0
    if upstream_exists:
        left_right = _run(["git", "rev-list", "--left-right", "--count", "HEAD...upstream/master"], cwd=repo_root)
        left, right = left_right.split()
        ahead_upstream = int(left)
        behind_upstream = int(right)

    return {
        "ci_event": ci_event,
        "head_is_detached": head_is_detached,
        "sync_origin_mode": sync_origin_mode,
        "sync_origin_reason_code": origin_reason_code,
        "branch": branch,
        "branch_source": branch_source,
        "head": head,
        "head_short": head_short,
        "head_date": head_date,
        "working_tree_clean": not bool(porcelain),
        "origin": {
            "ref": origin_ref,
            "exists": origin_exists,
            "ahead": ahead_origin,
            "behind": behind_origin,
            "sync_origin": sync_origin,
            "status": origin_status,
            "reason_code": origin_reason_code,
            "detail": origin_detail,
        },
        "upstream_master": {
            "ref": "upstream/master",
            "exists": upstream_exists,
            "ahead": ahead_upstream,
            "behind": behind_upstream,
            "status": "WARN" if (upstream_exists and behind_upstream > 0) else "PASS",
        },
    }


def _collect_python_docstring_coverage(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "module_has_docstring": False,
        "symbol_has_docstring": {},
        "parse_error": None,
    }

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as exc:  # pragma: no cover
        result["parse_error"] = str(exc)
        return result

    result["module_has_docstring"] = bool(ast.get_docstring(tree))

    symbol_map: dict[str, bool] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbol_map[node.name] = bool(ast.get_docstring(node))
    result["symbol_has_docstring"] = symbol_map
    return result


def _aggregate_metrics(file_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    by_language: dict[str, dict[str, Any]] = {}
    by_critical_module: dict[str, dict[str, Any]] = {}

    for row in file_rows:
        language = row["language"]
        lang_bucket = by_language.setdefault(
            language,
            {
                "files": 0,
                "nonempty_lines": 0,
                "comment_lines": 0,
                "docstring_lines": 0,
                "annotated_lines": 0,
            },
        )
        lang_bucket["files"] += 1
        lang_bucket["nonempty_lines"] += row["nonempty_lines"]
        lang_bucket["comment_lines"] += row["comment_lines"]
        lang_bucket["docstring_lines"] += row["docstring_lines"]
        lang_bucket["annotated_lines"] += row["annotated_lines"]

        for module_name in row["critical_modules"]:
            bucket = by_critical_module.setdefault(
                module_name,
                {
                    "files": 0,
                    "nonempty_lines": 0,
                    "comment_lines": 0,
                    "docstring_lines": 0,
                    "annotated_lines": 0,
                },
            )
            bucket["files"] += 1
            bucket["nonempty_lines"] += row["nonempty_lines"]
            bucket["comment_lines"] += row["comment_lines"]
            bucket["docstring_lines"] += row["docstring_lines"]
            bucket["annotated_lines"] += row["annotated_lines"]

    for bucket in list(by_language.values()) + list(by_critical_module.values()):
        nonempty = bucket["nonempty_lines"]
        density = (bucket["annotated_lines"] / nonempty * 100.0) if nonempty else 0.0
        bucket["annotation_density_pct"] = round(density, 2)

    return by_language, by_critical_module


def _evaluate_policy(
    *,
    repo_root: Path,
    file_rows: list[dict[str, Any]],
    min_large_lines: int,
) -> dict[str, Any]:
    by_path = {row["path"]: row for row in file_rows}
    violations: list[dict[str, Any]] = []

    for rel_path, policy in CRITICAL_FILE_POLICIES.items():
        row = by_path.get(rel_path)
        if row is None:
            violations.append(
                {
                    "type": "critical_file_missing",
                    "path": rel_path,
                    "detail": "Archivo crítico no encontrado en archivos rastreados.",
                }
            )
            continue

        min_annotations = int(policy.get("min_annotation_lines", 0))
        if row["annotated_lines"] < min_annotations:
            violations.append(
                {
                    "type": "min_annotation_lines",
                    "path": rel_path,
                    "detail": f"annotated_lines={row['annotated_lines']} < min={min_annotations}",
                }
            )

        if row["nonempty_lines"] >= min_large_lines and row["annotated_lines"] == 0:
            violations.append(
                {
                    "type": "large_file_without_annotations",
                    "path": rel_path,
                    "detail": f"nonempty_lines={row['nonempty_lines']} y annotated_lines=0",
                }
            )

        if Path(rel_path).suffix != ".py":
            continue

        py_doc = _collect_python_docstring_coverage(repo_root / rel_path)
        if py_doc.get("parse_error"):
            violations.append(
                {
                    "type": "docstring_parse_error",
                    "path": rel_path,
                    "detail": str(py_doc["parse_error"]),
                }
            )
            continue

        if policy.get("require_module_docstring") and not py_doc["module_has_docstring"]:
            violations.append(
                {
                    "type": "module_docstring_missing",
                    "path": rel_path,
                    "detail": "Docstring de módulo requerida en archivo crítico.",
                }
            )

        symbol_map = py_doc.get("symbol_has_docstring", {})
        for symbol in policy.get("required_symbol_docstrings", ()):  # type: ignore[assignment]
            if not symbol_map.get(str(symbol), False):
                violations.append(
                    {
                        "type": "symbol_docstring_missing",
                        "path": rel_path,
                        "detail": f"Docstring faltante en símbolo crítico: {symbol}",
                    }
                )

    status = "PASS" if not violations else "WARN"
    return {
        "status": status,
        "violations": violations,
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Auditoría de Repositorio y Comentarios")
    lines.append("")
    lines.append(f"- Fecha UTC: `{payload['generated_at']}`")
    lines.append(f"- Estado global: **{payload['status']}**")
    lines.append("")

    git_sync = payload["git_sync"]
    lines.append("## Sync Git")
    lines.append(f"- Evento CI: `{git_sync.get('ci_event', 'local')}`")
    lines.append(f"- sync_origin_mode: `{git_sync.get('sync_origin_mode', 'strict')}`")
    lines.append(f"- sync_origin_reason_code: `{git_sync.get('sync_origin_reason_code', 'UNKNOWN')}`")
    lines.append(f"- Rama: `{git_sync['branch']}`")
    lines.append(f"- Fuente de rama: `{git_sync['branch_source']}`")
    lines.append(f"- HEAD: `{git_sync['head_short']}` ({git_sync['head_date']})")
    lines.append(f"- Árbol limpio: `{git_sync['working_tree_clean']}`")
    origin = git_sync["origin"]
    lines.append(
        f"- sync_origin: **{origin['status']}** (ahead={origin['ahead']}, behind={origin['behind']}, ref={origin['ref']})"
    )
    lines.append(f"- detalle sync_origin: {origin['detail']}")
    reason_code = str(git_sync.get("sync_origin_reason_code", ""))
    if reason_code.startswith("PR_DETACHED_"):
        lines.append("- Clasificación: warning de contexto PR detached (no bloqueo estructural).")
    elif origin["status"] == "FAIL":
        lines.append("- Clasificación: fallo bloqueante real de sync Git.")
    else:
        lines.append("- Clasificación: sin warning contextual de sync Git.")
    upstream = git_sync["upstream_master"]
    if upstream["exists"]:
        lines.append(
            f"- upstream/master: **{upstream['status']}** (ahead={upstream['ahead']}, behind={upstream['behind']})"
        )
    else:
        lines.append("- upstream/master: `N/A` (ref no configurada)")
    lines.append("")

    lines.append("## Densidad por Lenguaje")
    for lang, row in sorted(payload["metrics"]["by_language"].items()):
        lines.append(
            f"- `{lang}`: files={row['files']}, nonempty={row['nonempty_lines']}, annotated={row['annotated_lines']}, density={row['annotation_density_pct']}%"
        )
    lines.append("")

    lines.append("## Módulos Críticos")
    for mod, row in sorted(payload["metrics"]["by_critical_module"].items()):
        lines.append(
            f"- `{mod}`: files={row['files']}, nonempty={row['nonempty_lines']}, annotated={row['annotated_lines']}, density={row['annotation_density_pct']}%"
        )
    lines.append("")

    lines.append("## Top archivos críticos con menor densidad")
    ranking = payload["metrics"]["critical_low_annotation_ranking"]
    if not ranking:
        lines.append("- Sin archivos críticos elegibles para ranking.")
    else:
        for item in ranking:
            lines.append(
                f"- `{item['path']}`: nonempty={item['nonempty_lines']}, annotated={item['annotated_lines']}, density={item['annotation_density_pct']}%"
            )
    lines.append("")

    policy = payload["policy"]
    lines.append("## Política mínima (módulos críticos)")
    lines.append(f"- Estado: **{policy['status']}**")
    if policy["violations"]:
        for violation in policy["violations"]:
            lines.append(f"- `{violation['type']}` en `{violation['path']}`: {violation['detail']}")
    else:
        lines.append("- Sin violaciones detectadas.")
    lines.append("")
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auditoría de sync Git y comentarios/docstrings")
    parser.add_argument("--repo-root", default=".", help="Ruta raíz del repositorio")
    parser.add_argument("--json-output", default="qa/reports/repo_comment_audit.json")
    parser.add_argument("--md-output", default="qa/reports/repo_comment_audit.md")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--min-large-lines", type=int, default=120)
    parser.add_argument("--fetch", action="store_true", help="Ejecuta git fetch --all --prune antes de medir")
    parser.add_argument("--fail-on-warn", action="store_true", help="Sale con código 1 si el estado global es WARN")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()

    git_sync = _get_git_sync(repo_root, fetch=bool(args.fetch))

    files = _iter_tracked_files(repo_root)
    file_rows: list[dict[str, Any]] = []
    for abs_path in files:
        rel_path = abs_path.relative_to(repo_root).as_posix()
        metrics = _count_annotations(abs_path)
        file_rows.append(
            {
                "path": rel_path,
                "language": LANG_BY_EXT[abs_path.suffix.lower()],
                "critical_modules": _match_critical_modules(rel_path),
                **metrics,
            }
        )

    by_language, by_critical_module = _aggregate_metrics(file_rows)

    critical_rows = [
        row
        for row in file_rows
        if row["critical_modules"] and row["nonempty_lines"] >= int(args.min_large_lines)
    ]
    critical_rows.sort(key=lambda row: (row["annotation_density_pct"], -row["nonempty_lines"], row["path"]))

    ranking = [
        {
            "path": row["path"],
            "nonempty_lines": row["nonempty_lines"],
            "comment_lines": row["comment_lines"],
            "docstring_lines": row["docstring_lines"],
            "annotated_lines": row["annotated_lines"],
            "annotation_density_pct": row["annotation_density_pct"],
        }
        for row in critical_rows[: int(args.top_n)]
    ]

    policy = _evaluate_policy(repo_root=repo_root, file_rows=file_rows, min_large_lines=int(args.min_large_lines))

    sync_origin_status = git_sync["origin"]["status"]
    upstream_status = git_sync["upstream_master"]["status"] if git_sync["upstream_master"]["exists"] else "PASS"

    if sync_origin_status == "FAIL":
        status = "FAIL"
    elif policy["status"] == "WARN" or upstream_status == "WARN" or sync_origin_status == "WARN":
        status = "WARN"
    else:
        status = "PASS"

    payload = {
        "generated_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "status": status,
        "ci_event": git_sync.get("ci_event", "local"),
        "sync_origin_mode": git_sync.get("sync_origin_mode", "strict"),
        "sync_origin_reason_code": git_sync.get("sync_origin_reason_code", "UNKNOWN"),
        "git_sync": git_sync,
        "metrics": {
            "file_count": len(file_rows),
            "by_language": by_language,
            "by_critical_module": by_critical_module,
            "critical_low_annotation_ranking": ranking,
        },
        "policy": policy,
        "defaults": {
            "excluded_path_parts": list(EXCLUDED_PATH_PARTS),
            "critical_modules": CRITICAL_MODULES,
            "critical_file_policies": CRITICAL_FILE_POLICIES,
            "min_large_lines": int(args.min_large_lines),
            "top_n": int(args.top_n),
        },
    }

    json_output = Path(args.json_output)
    if not json_output.is_absolute():
        json_output = repo_root / json_output
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md_output = Path(args.md_output)
    if not md_output.is_absolute():
        md_output = repo_root / md_output
    md_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.write_text(_render_markdown(payload), encoding="utf-8")

    print(f"[qa] repo comment audit JSON: {json_output}")
    print(f"[qa] repo comment audit MD: {md_output}")
    print(
        "[qa] status="
        f"{status} sync_origin={git_sync['origin']['status']} "
        f"mode={git_sync.get('sync_origin_mode', 'strict')} "
        f"reason={git_sync.get('sync_origin_reason_code', 'UNKNOWN')} "
        f"policy={policy['status']}"
    )

    if status == "FAIL":
        return 1
    if status == "WARN" and bool(args.fail_on_warn):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
