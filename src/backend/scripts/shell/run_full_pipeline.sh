#!/bin/bash
cd "$(dirname "$0")/../../../.."

set -e

# Prevent a second loop even when the script is started outside start_daemon.sh.
mkdir -p logs
exec 8>"logs/rss_daemon.instance.lock"
if ! flock -n 8; then
    echo "RSS pipeline already running; refusing to start a second loop."
    exit 1
fi

INTERVAL="${PIPELINE_INTERVAL_MINUTES:-5}"

# Trap Ctrl+C (SIGINT) to allow graceful exit
trap "echo -e '\n====================================================='; echo 'Pipeline manually interrupted by user (Ctrl+C). Exiting...'; exit 0" SIGINT

while true; do
    CYCLE_STARTED=$SECONDS
    echo "====================================================="
    echo "   Veritas Lens - Full Automated Pipeline Triggered  "
    echo "   Timestamp: $(date)                                "
    echo "====================================================="

    # Pass control to the modularized scripts
    bash src/backend/scripts/shell/run_ingestion.sh
    bash src/backend/scripts/shell/run_semantics_and_ner.sh

    echo "====================================================="
    echo "Full Pipeline Completed Successfully at $(date)      "
    echo "====================================================="
    CYCLE_ELAPSED=$((SECONDS - CYCLE_STARTED))
    SLEEP_SECONDS=$((INTERVAL * 60 - CYCLE_ELAPSED))
    if (( SLEEP_SECONDS < 0 )); then
        SLEEP_SECONDS=0
    fi
    echo "Sleeping for $((SLEEP_SECONDS / 60))m $((SLEEP_SECONDS % 60))s before the next cycle..."
    echo "Press [Ctrl+C] to stop."
    echo ""
    
    # Sleep in short increments to allow immediate reaction to Ctrl+C
    for ((i=0; i<SLEEP_SECONDS; i++)); do
        sleep 1
    done
done
