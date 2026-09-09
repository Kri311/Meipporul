#!/bin/bash
# stop_daemon.sh - Stops the Veritas Lens RSS fetcher background process

cd "$(dirname "$0")"
PID_FILE="rss_daemon.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    
    # Check if process is actually running
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping RSS fetcher daemon (PID: $PID)..."
        kill "$PID"
        echo "Daemon stopped successfully."
    else
        echo "Daemon is not currently running (stale PID file)."
    fi
    
    # Always clean up the PID file
    rm "$PID_FILE"
else
    echo "No rss_daemon.pid file found. The daemon does not appear to be running."
fi
