#!/bin/bash
# start_daemon.sh - Starts the Veritas Lens RSS fetcher in the background

cd "$(dirname "$0")"
PID_FILE="rss_daemon.pid"

# 1. Prevent multiple instances from running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Error: The RSS fetcher is ALREADY running (PID: $OLD_PID)."
        echo "You can only run one instance at a time."
        echo "To stop it, run: ./stop_daemon.sh"
        exit 1
    else
        # Process died but PID file remained (stale lock), clean it up
        rm "$PID_FILE"
    fi
fi

# Interval in minutes between fetches
INTERVAL=15

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run the fetcher continuously in the background
nohup python fetch_rss_standalone.py --interval $INTERVAL >> rss_daemon.log 2>&1 &
PID=$!

# Save the new PID to lock the process
echo $PID > "$PID_FILE"

echo "Veritas Lens RSS Fetcher started in the background!"
echo "PID: $PID (saved to $PID_FILE)"
echo "Fetching every $INTERVAL minutes."
echo "Logs are being appended to: rss_daemon.log"
echo "To stop it anytime, run: ./stop_daemon.sh"
