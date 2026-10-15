#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
# Check PostgreSQL availability and credentials before running schema setup.
# pg_isready checks the server; psql SELECT 1 confirms the configured URL can
# authenticate and reach the intended database.
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
echo "[backend] Checking PostgreSQL at ${DB_HOST}:${DB_PORT}..."
if ! command -v pg_isready >/dev/null 2>&1; then
  echo "[backend] PostgreSQL client tools are missing (pg_isready). Install the PostgreSQL client package and retry." >&2
  exit 1
fi
if ! pg_isready -h "$DB_HOST" -p "$DB_PORT"; then
  echo "[backend] PostgreSQL is not accepting connections at ${DB_HOST}:${DB_PORT}. Start PostgreSQL and retry." >&2
  exit 1
fi
if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "[backend] DATABASE_URL is not configured. Set DATABASE_URL or POSTGRES_USER and POSTGRES_DB in .env." >&2
  exit 1
fi
if ! command -v psql >/dev/null 2>&1; then
  echo "[backend] PostgreSQL client tools are missing (psql). Install the PostgreSQL client package and retry." >&2
  exit 1
fi
echo "[backend] Verifying database credentials..."
if ! psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -c 'SELECT 1;' >/dev/null; then
  echo "[backend] Database login/check failed. Verify DATABASE_URL or POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB in .env." >&2
  exit 1
fi
# Upgrade additive PostgreSQL columns before Uvicorn accepts requests. This
# includes summary bullet/hash fields on articles and news_clusters.
echo "[backend] Initializing database schema..."
"$PYTHON_BIN" -m backend.models.database
echo "[backend] Database schema ready; starting Uvicorn on ${HOST:-0.0.0.0}:${BACKEND_PORT:-8000}..."
exec "$PYTHON_BIN" -m uvicorn backend.api:app \
  --app-dir src \
  --host "${HOST:-0.0.0.0}" \
  --port "${BACKEND_PORT:-8000}" \
  --reload \
  --reload-dir "$PROJECT_ROOT/src/backend"
