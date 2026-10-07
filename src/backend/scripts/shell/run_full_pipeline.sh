#!/bin/bash
cd "$(dirname "$0")/../../../.."

set -e

# Redirect all output of this script to both console and rss_daemon.log
exec > >(tee -a logs/rss_daemon.log) 2>&1

INTERVAL=15

# Trap Ctrl+C (SIGINT) to allow graceful exit
trap "echo -e '\n====================================================='; echo 'Pipeline manually interrupted by user (Ctrl+C). Exiting...'; exit 0" SIGINT

while true; do
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
    echo "Sleeping for $INTERVAL minutes before the next cycle..."
    echo "Press [Ctrl+C] to stop."
    echo ""
    
    # Sleep in short increments to allow immediate reaction to Ctrl+C
    for ((i=0; i<INTERVAL*60; i++)); do
        sleep 1
    done
done
