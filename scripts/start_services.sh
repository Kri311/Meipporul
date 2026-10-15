#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Start the API and frontend in separate terminals:"
echo "  $PROJECT_ROOT/scripts/start_backend.sh"
echo "  $PROJECT_ROOT/scripts/start_frontend.sh"
echo "RSS/semantic daemon (separate terminal):"
echo "  $PROJECT_ROOT/scripts/start_daemon.sh"
