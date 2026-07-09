#!/bin/bash
set -e

echo "[CI Triage Runner] Starting Docker daemon..."
dockerd > /var/log/dockerd.log 2>&1 &
DOCKER_PID=$!

for i in $(seq 1 15); do
    if docker info >/dev/null 2>&1; then
        echo "[CI Triage Runner] Docker daemon ready"
        break
    fi
    if [ "$i" -eq 15 ]; then
        echo "[CI Triage Runner] Docker daemon failed to start"
        cat /var/log/dockerd.log
        exit 1
    fi
    sleep 1
done

echo "[CI Triage Runner] Starting watcher daemon..."
python3 -m ci_triage_agent.watcher &
WATCHER_PID=$!
echo "[CI Triage Runner] Watcher started (PID: $WATCHER_PID)"

# Make Docker socket accessible to non-root runner user
chmod 666 /var/run/docker.sock 2>/dev/null || true

if [ ! -f /opt/actions-runner/.runner ]; then
    echo "[CI Triage Runner] Runner not configured — running configure.sh"
    GITHUB_URL="${GITHUB_URL:-https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}}"
    export GITHUB_URL
    sudo -E -u runner /opt/actions-runner/configure.sh
fi

cleanup() {
    echo "[CI Triage Runner] Shutting down..."
    kill -TERM "$RUNNER_PID" 2>/dev/null || true
    wait "$RUNNER_PID" 2>/dev/null || true
    kill -TERM "$WATCHER_PID" 2>/dev/null || true
    wait "$WATCHER_PID" 2>/dev/null || true
    kill -TERM "$DOCKER_PID" 2>/dev/null || true
    wait "$DOCKER_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Write critical env vars to runner's .env file so they're available to job steps
echo "[CI Triage Runner] Writing env vars to .env for job steps..."
: > /opt/actions-runner/.env
for var in LLM_API_KEY LLM_PROVIDER GH_TOKEN; do
    if [ -n "${!var}" ]; then
        echo "${var}=${!var}" >> /opt/actions-runner/.env
    fi
done
chown runner:runner /opt/actions-runner/.env

echo "[CI Triage Runner] Starting GitHub Actions runner..."
sudo -u runner /opt/actions-runner/run.sh "$@" &
RUNNER_PID=$!

wait "$RUNNER_PID"
cleanup
