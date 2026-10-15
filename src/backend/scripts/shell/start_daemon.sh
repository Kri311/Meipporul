#!/bin/bash
cd "$(dirname "$0")/../../../.."
set -e

# start_daemon.sh - Starts the full Veritas Lens pipeline in the background


PID_FILE="logs/rss_daemon.pid"
LOG_FILE="logs/rss_daemon.log"
START_LOCK_FILE="logs/rss_daemon.start.lock"
mkdir -p logs

# Serialize concurrent starts. The lock protects the PID check + process spawn.
exec 9>"$START_LOCK_FILE"
if ! flock -n 9; then
    echo "Another start_daemon.sh invocation is already starting the pipeline."
    exit 1
fi

# 1. Prevent multiple instances from running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if [[ "$OLD_PID" =~ ^[0-9]+$ ]] && ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Error: The Daemon is ALREADY running (PID: $OLD_PID)."
        echo "You can only run one instance at a time."
        echo "To stop it, run: ./stop_daemon.sh"
        exit 1
    else
        # Process died but PID file remained (stale lock), clean it up
        rm "$PID_FILE"
    fi
fi

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# run_full_pipeline.sh now contains the infinite loop internally
nohup bash src/backend/scripts/shell/run_full_pipeline.sh >> "$LOG_FILE" 2>&1 < /dev/null &
PID=$!

# Save the new PID to lock the process
echo $PID > "$PID_FILE"

echo "Veritas Lens Full Pipeline Daemon started in the background!"
echo "PID: $PID (saved to $PID_FILE)"
echo "The pipeline will loop continuously based on its internal interval."
echo "Logs are being appended to: $LOG_FILE"
echo "To stop it anytime, run: ./stop_daemon.sh"
