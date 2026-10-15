#!/bin/bash
cd "$(dirname "$0")/../../../.."
set -e

PID_FILE="logs/reprocess_daemon.pid"
LOG_FILE="logs/reprocess_daemon.log"
mkdir -p logs

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Error: The Reprocess Daemon is ALREADY running (PID: $OLD_PID)."
        echo "Check logs at $LOG_FILE or kill it manually."
        exit 1
    else
            rm "$PID_FILE"
    fi
fi

if [ -d "venv" ]; then
    source venv/bin/activate
fi

mkdir -p logs

echo "Starting the 2026 article reprocessor..."
PYTHONPATH="./src" nohup python3 src/backend/scripts/reprocess_articles.py >> "$LOG_FILE" 2>&1 &
PID=$!

echo $PID > "$PID_FILE"
echo "Daemon started successfully!"
echo "PID: $PID"
echo "Logs are being appended to: $LOG_FILE"
echo "You can monitor the progress by running: tail -f $LOG_FILE"
