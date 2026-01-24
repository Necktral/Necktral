#!/usr/bin/env bash
set -euo pipefail

# Genera un snapshot Markdown para que un PM/LLM pueda “ponerse al día”
# sin tener que leer todo el repo.
#
# Uso local:
#   bash scripts/pm_snapshot.sh
#   bash scripts/pm_snapshot.sh /tmp/pm_snapshot.md
#
# En GitHub Actions se usa para adjuntar un artefacto.

OUT_FILE="${1:-pm_snapshot.md}"

OUT_DIR="$(dirname "$OUT_FILE")"
mkdir -p "$OUT_DIR" 2>/dev/null || true

if [[ ! -w "$OUT_DIR" ]]; then
  OUT_FILE="/tmp/pm_snapshot.md"
fi

REPO_URL="$(git config --get remote.origin.url || true)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
SHA="$(git rev-parse HEAD)"
NOW_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# Si es PR en GitHub Actions, calcula diff contra base.
BASE_REF="${GITHUB_BASE_REF:-}"
HEAD_REF="${GITHUB_HEAD_REF:-}"

{
  echo "# PM Snapshot"
  echo
  echo "- Generated (UTC): ${NOW_UTC}"
  echo "- Repo: ${REPO_URL:-"(no origin)"}"
  echo "- Branch: ${BRANCH}"
  echo "- HEAD: ${SHA}"

  if [[ -n "${GITHUB_WORKFLOW:-}" ]]; then
    echo "- GitHub workflow: ${GITHUB_WORKFLOW}"
  fi
  if [[ -n "${GITHUB_REF_NAME:-}" ]]; then
    echo "- GitHub ref: ${GITHUB_REF_NAME}"
  fi

  echo
  echo "## Ramas remotas (top 50)"
  echo
  git fetch --all --prune >/dev/null 2>&1 || true
  git branch -r | sed 's/^  *//' | head -n 50 | sed 's/^/- /'

  echo
  echo "## Últimos commits (top 30)"
  echo
  git --no-pager log -n 30 --date=short --pretty=format:'- %h %ad %s (%an)'

  echo
  echo
  if [[ -n "$BASE_REF" && -n "$HEAD_REF" ]]; then
    echo "## Pull Request diff"
    echo
    echo "- Base: ${BASE_REF}"
    echo "- Head: ${HEAD_REF}"
    echo
    # Intentar resolver el merge base.
    git fetch origin "+refs/heads/${BASE_REF}:refs/remotes/origin/${BASE_REF}" >/dev/null 2>&1 || true
    echo "### Archivos cambiados (name-status)"
    echo
    git --no-pager diff --name-status "origin/${BASE_REF}...HEAD" | sed 's/^/- /'
    echo
    echo "### Diff stat"
    echo
    git --no-pager diff --stat "origin/${BASE_REF}...HEAD"
  else
    echo "## Cambios recientes (último commit)"
    echo
    echo "### Archivos tocados"
    echo
    git --no-pager show --name-status --pretty=format: HEAD | tail -n +2 | sed 's/^/- /'
    echo
    echo "### Diff stat"
    echo
    git --no-pager show --stat --pretty=format: HEAD
  fi

  echo
  echo "## Punteros útiles"
  echo
  echo "- QA reports (si se ejecuta el workflow QA): artefacto 'qa-reports'"
  echo "- Este snapshot: artefacto 'pm-snapshot'"
} >"$OUT_FILE"

echo "Wrote: $OUT_FILE"
