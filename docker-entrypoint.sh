#!/bin/bash
set -e

echo "Starting Phoenix..."

# Trap signals for clean shutdown
cleanup() {
    echo "Shutting down..."
    kill $RENDERER_PID $DASHBOARD_PID $DISPLAY_PID 2>/dev/null
    wait
    exit 0
}
trap cleanup SIGTERM SIGINT

# Start dashboard first (applets need /proxy and /data)
uv run phoenix dashboard &
DASHBOARD_PID=$!
sleep 1

# Start renderer
uv run phoenix render &
RENDERER_PID=$!

# Start display
uv run phoenix display &
DISPLAY_PID=$!

echo "Phoenix running: renderer=$RENDERER_PID dashboard=$DASHBOARD_PID display=$DISPLAY_PID"

# Wait for any process to exit
wait -n 2>/dev/null || wait
echo "A process exited, shutting down..."
cleanup
