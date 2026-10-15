#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Read simple KEY=value dotenv entries without eval (and never overwrite an
# environment value supplied by the caller).
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*# || ! "$line" =~ ^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*= ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key//[[:space:]]/}"
    value="${value%$'\r'}"
    if [[ ${#value} -ge 2 ]]; then
      if [[ "$value" == \"*\" || "$value" == \'*\' ]]; then
        value="${value:1:${#value}-2}"
      fi
    fi
    if [[ ! -v "$key" ]]; then
      export "$key=$value"
    fi
  done < "$PROJECT_ROOT/.env"
fi

if [[ -z "${DATABASE_URL:-}" && -n "${POSTGRES_USER:-}" && -n "${POSTGRES_DB:-}" ]]; then
  POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
  POSTGRES_PORT="${POSTGRES_PORT:-5432}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"
  export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
fi

if [[ -f "$PROJECT_ROOT/venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/venv/bin/activate"
fi

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="${PYTHON_BIN:-python}"

require_python_module() {
  "$PYTHON_BIN" -c "import $1" >/dev/null 2>&1 || {
    echo "Missing Python dependency: $1. Install project requirements first." >&2
    exit 1
  }
}
