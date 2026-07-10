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
python3 -m ci_triage_agent.cli.watcher_entry &
WATCHER_PID=$!
echo "[CI Triage Runner] Watcher started (PID: $WATCHER_PID)"

# Make Docker socket accessible to non-root runner user
chmod 666 /var/run/docker.sock 2>/dev/null || true

# --- Auto-registration logic ---
# Generates a fresh runner registration token on every container start,
# ensuring the runner never goes stale after PC reboot.

GITHUB_OWNER="${GITHUB_OWNER:-}"
GITHUB_REPO="${GITHUB_REPO:-}"

# Extract owner/repo from GITHUB_URL if not provided separately
if [ -z "$GITHUB_OWNER" ] || [ -z "$GITHUB_REPO" ]; then
    if [ -n "$GITHUB_URL" ]; then
        # GITHUB_URL format: https://github.com/owner/repo
        GITHUB_OWNER=$(echo "$GITHUB_URL" | awk -F'/' '{print $(NF-1)}')
        GITHUB_REPO=$(echo "$GITHUB_URL" | awk -F'/' '{print $NF}')
    fi
fi

if [ -n "$GH_TOKEN" ] && [ -n "$GITHUB_OWNER" ] && [ -n "$GITHUB_REPO" ]; then
    echo "[CI Triage Runner] Generating fresh registration token via GitHub API..."

    REG_TOKEN=$(curl -s -X POST \
        -H "Authorization: token $GH_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/runners/registration-token" \
        | jq -r '.token')

    if [ "$REG_TOKEN" != "null" ] && [ -n "$REG_TOKEN" ]; then
        RUNNER_TOKEN="$REG_TOKEN"
        export RUNNER_TOKEN
        GITHUB_URL="https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}"
        export GITHUB_URL
        # Remove old registration so configure.sh --replace registers fresh
        rm -f /opt/actions-runner/.runner
        echo "[CI Triage Runner] Fresh registration token obtained"
    else
        echo "[CI Triage Runner] WARNING: Could not generate registration token."
        echo "[CI Triage Runner] Check that GH_TOKEN has 'Administration: Write' scope."
    fi
else
    echo "[CI Triage Runner] WARNING: GH_TOKEN, GITHUB_OWNER, or GITHUB_REPO not set."
    echo "[CI Triage Runner] Falling back to existing .runner file (may be stale after reboot)."
fi

# Register if no .runner file exists (either fresh start or after deleting stale one)
if [ ! -f /opt/actions-runner/.runner ]; then
    echo "[CI Triage Runner] Runner not configured — running configure.sh"
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
