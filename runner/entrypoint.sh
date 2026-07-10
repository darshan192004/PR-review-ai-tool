#!/bin/sh
set -e

echo "[CI Triage Runner] Starting watcher..."
python3 -m ci_triage_agent.cli.watcher_entry &
WATCHER_PID=$!
echo "[CI Triage Runner] Watcher started (PID: $WATCHER_PID)"

if [ -f /opt/act/runner-config.yaml ]; then
    CONFIG_ARG="--config /opt/act/runner-config.yaml"
elif [ -f /config.yml ]; then
    CONFIG_ARG="--config /config.yml"
else
    CONFIG_ARG=""
fi

cleanup() {
    echo "[CI Triage Runner] Shutting down..."
    if [ -n "$WATCHER_PID" ] && kill -0 "$WATCHER_PID" 2>/dev/null; then
        kill "$WATCHER_PID" 2>/dev/null
        wait "$WATCHER_PID" 2>/dev/null
    fi
    exit 0
}
trap cleanup SIGTERM SIGINT

echo "[CI Triage Runner] Starting act_runner... $CONFIG_ARG"
exec /usr/local/bin/act_runner $CONFIG_ARG "$@"
