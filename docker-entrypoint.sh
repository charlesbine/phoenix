#!/bin/bash
set -e

read -ra services <<< "${PHOENIX_SERVICES:-dashboard render display}"
if (( ${#services[@]} == 0 )); then
    echo "No Phoenix services selected" >&2
    exit 2
fi
for service in "${services[@]}"; do
    case "$service" in
        dashboard|render|display) ;;
        *) echo "Unknown Phoenix service: $service" >&2; exit 2 ;;
    esac
done

pids=()
shutdown() {
    if (( ${#pids[@]} )); then
        kill "${pids[@]}" 2>/dev/null || true
        wait 2>/dev/null || true
    fi
    exit "$1"
}
trap 'shutdown 0' SIGTERM SIGINT

runs() { [[ " ${services[*]} " == *" $1 "* ]]; }

# Applets can fetch /proxy and /data from the dashboard during render.
if runs dashboard; then
    uv run phoenix dashboard &
    pids+=("$!")
    sleep 1
fi
if runs render; then
    uv run phoenix render &
    pids+=("$!")
fi
if runs display; then
    uv run phoenix display &
    pids+=("$!")
fi

status=0
wait -n || status=$?
shutdown "$status"
