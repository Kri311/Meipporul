#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT/src/frontend"
if [[ ! -d node_modules ]]; then
  echo "Frontend dependencies are missing. Run npm install in src/frontend first." >&2
  exit 1
fi
exec npm run dev -- --hostname "${HOST:-0.0.0.0}" --port "${FRONTEND_PORT:-3000}"
