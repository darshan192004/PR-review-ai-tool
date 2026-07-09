#!/bin/bash
set -e

echo "[CI Triage Runner] Starting watcher daemon..."
python3 -m ci_triage_agent.watcher &
WATCHER_PID=$!
echo "[CI Triage Runner] Watcher started (PID: $WATCHER_PID)"

if [ ! -f /opt/actions-runner/.runner ]; then
    echo "[CI Triage Runner] Runner not configured — running configure.sh"
    /opt/actions-runner/configure.sh
fi

cleanup() {
    echo "[CI Triage Runner] Shutting down..."
    kill -TERM "$RUNNER_PID" 2>/dev/null || true
    wait "$RUNNER_PID" 2>/dev/null || true
    kill -TERM "$WATCHER_PID" 2>/dev/null || true
    wait "$WATCHER_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

echo "[CI Triage Runner] Starting GitHub Actions runner..."
/opt/actions-runner/run.sh "$@" &
RUNNER_PID=$!

wait "$RUNNER_PID"
cleanup
