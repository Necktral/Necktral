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

SERVER_URL="${GITHUB_SERVER_URL:-https://github.com}"
REPO_SLUG="${GITHUB_REPOSITORY:-}"
RUN_ID="${GITHUB_RUN_ID:-}"
RUN_NUMBER="${GITHUB_RUN_NUMBER:-}"
WORKFLOW_NAME="${GITHUB_WORKFLOW:-}"
REF_NAME="${GITHUB_REF_NAME:-}"

# Preferimos PM_* (inyectado por workflow) para que el script sea determinista.
BASE_REF="${PM_BASE_REF:-${GITHUB_BASE_REF:-}}"
HEAD_REF="${PM_HEAD_REF:-${GITHUB_HEAD_REF:-}}"
BASE_SHA="${PM_BASE_SHA:-}"
HEAD_SHA="${PM_HEAD_SHA:-${GITHUB_SHA:-$SHA}}"
PR_NUMBER="${PM_PR_NUMBER:-}"
PR_URL="${PM_PR_URL:-}"

REPO_HTTP=""
RUN_URL=""
if [[ -n "$REPO_SLUG" ]]; then
  REPO_HTTP="${SERVER_URL}/${REPO_SLUG}"
  if [[ -n "$RUN_ID" ]]; then
    RUN_URL="${REPO_HTTP}/actions/runs/${RUN_ID}"
  fi
fi

_commit_link() {
  local sha="$1"
  if [[ -n "$REPO_HTTP" && -n "$sha" ]]; then
    printf "[%s](%s/commit/%s)" "${sha:0:12}" "$REPO_HTTP" "$sha"
  else
    printf "%s" "${sha:0:12}"
  fi
}

MERGE_BASE_SHA=""
if [[ -n "$BASE_SHA" && -n "$HEAD_SHA" ]]; then
  # asegurar que los SHAs existan en el checkout (por si el runner hizo checkout shallow)
  git fetch --no-tags --prune --depth=1 origin "$BASE_SHA" "$HEAD_SHA" >/dev/null 2>&1 || true
  MERGE_BASE_SHA="$(git merge-base "$BASE_SHA" "$HEAD_SHA" 2>/dev/null || true)"
fi

RANGE_DIFFSTAT=""
if [[ -n "$BASE_SHA" && -n "$HEAD_SHA" ]]; then
  RANGE_DIFFSTAT="${BASE_SHA}...${HEAD_SHA}"
elif [[ -n "$BASE_REF" ]]; then
  git fetch origin "+refs/heads/${BASE_REF}:refs/remotes/origin/${BASE_REF}" >/dev/null 2>&1 || true
  RANGE_DIFFSTAT="origin/${BASE_REF}...HEAD"
else
  RANGE_DIFFSTAT=""
fi

{
  echo "# PM Snapshot"
  echo
  echo "## Repo"
  echo "- generated_at_utc: ${NOW_UTC}"
  if [[ -n "$REPO_HTTP" ]]; then
    echo "- repo: ${REPO_HTTP}"
  else
    echo "- repo: ${REPO_URL:-"(no origin)"}"
  fi
  if [[ -n "$RUN_URL" ]]; then
    if [[ -n "$RUN_NUMBER" ]]; then
      echo "- run: ${RUN_URL} (run_number=${RUN_NUMBER})"
    else
      echo "- run: ${RUN_URL}"
    fi
  fi
  [[ -n "$WORKFLOW_NAME" ]] && echo "- workflow: ${WORKFLOW_NAME}"
  [[ -n "$REF_NAME" ]] && echo "- ref: ${REF_NAME}"

  echo
  echo "## Head"
  echo "- branch: ${BRANCH}"
  echo "- head_ref: ${HEAD_REF:-""}"
  echo "- head_sha: ${HEAD_SHA} ($(_commit_link "$HEAD_SHA"))"

  echo
  echo "## Branches"
  git fetch --all --prune >/dev/null 2>&1 || true
  git branch -r | sed 's/^  *//' | head -n 50 | sed 's/^/- /'

  echo
  echo "## Recent commits"
  git --no-pager log -n 30 --date=short --pretty=format:'- %h %ad %s (%an)'

  echo
  echo
  echo "## PR context"
  if [[ -n "$PR_NUMBER" ]]; then
    echo "- pr_number: ${PR_NUMBER}"
  else
    echo "- pr_number:"
  fi
  if [[ -n "$PR_URL" ]]; then
    echo "- pr_url: ${PR_URL}"
  elif [[ -n "$REPO_HTTP" && -n "$PR_NUMBER" ]]; then
    echo "- pr_url: ${REPO_HTTP}/pull/${PR_NUMBER}"
  else
    echo "- pr_url:"
  fi
  echo "- base_ref: ${BASE_REF}"
  echo "- base_sha: ${BASE_SHA}"
  echo "- head_ref: ${HEAD_REF}"
  echo "- head_sha: ${HEAD_SHA}"
  echo "- merge_base_sha: ${MERGE_BASE_SHA}"
  if [[ -n "$BASE_SHA" ]]; then
    echo "- base_commit: $(_commit_link "$BASE_SHA")"
  fi
  if [[ -n "$MERGE_BASE_SHA" ]]; then
    echo "- merge_base_commit: $(_commit_link "$MERGE_BASE_SHA")"
  fi

  echo
  echo "## Diffstat"
  if [[ -n "$RANGE_DIFFSTAT" ]]; then
    git --no-pager diff --stat "$RANGE_DIFFSTAT"
  else
    git --no-pager show --stat --pretty=format: HEAD
  fi

  echo
  echo "## Changed files"
  if [[ -n "$RANGE_DIFFSTAT" ]]; then
    git --no-pager diff --name-status "$RANGE_DIFFSTAT" | sed 's/^/- /'
  else
    git --no-pager show --name-status --pretty=format: HEAD | sed '/^$/d' | sed 's/^/- /'
  fi

  echo
  echo "## Notes"
  echo "- artifact: pm-snapshot (pm_snapshot.md)"
  if git show-ref --verify --quiet refs/remotes/origin/main && git show-ref --verify --quiet refs/remotes/origin/master; then
    COUNTS="$(git rev-list --left-right --count origin/main...origin/master 2>/dev/null || true)"
    if [[ -n "$COUNTS" ]]; then
      BEHIND_MAIN="$(echo "$COUNTS" | awk '{print $1}')"
      BEHIND_MASTER="$(echo "$COUNTS" | awk '{print $2}')"
      echo "- divergence: origin/main_only=${BEHIND_MAIN} origin/master_only=${BEHIND_MASTER}"
    fi
  fi
} >"$OUT_FILE"

echo "Wrote: $OUT_FILE"
