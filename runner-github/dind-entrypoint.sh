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

# --- Stable runner name & labels ---
RUNNER_NAME="${RUNNER_NAME:-ci-triage-runner}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,ci-triage}"
export RUNNER_NAME RUNNER_LABELS

GITHUB_OWNER="${GITHUB_OWNER:-}"
GITHUB_REPO="${GITHUB_REPO:-}"

# Extract owner/repo from GITHUB_URL if not provided separately
if [ -z "$GITHUB_OWNER" ] || [ -z "$GITHUB_REPO" ]; then
    if [ -n "$GITHUB_URL" ]; then
        GITHUB_OWNER=$(echo "$GITHUB_URL" | awk -F'/' '{print $(NF-1)}')
        GITHUB_REPO=$(echo "$GITHUB_URL" | awk -F'/' '{print $NF}')
    fi
fi

# --- Registration function (called at boot and on re-registration) ---
register_runner() {
    echo "[CI Triage Runner] Registering runner..."

    if [ -z "$GH_TOKEN" ] || [ -z "$GITHUB_OWNER" ] || [ -z "$GITHUB_REPO" ]; then
        echo "[CI Triage Runner] WARNING: GH_TOKEN, GITHUB_OWNER, or GITHUB_REPO not set. Cannot register."
        return 1
    fi

    API_BASE="https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/runners"

    # Only delete runners with our exact name (not ALL offline runners)
    echo "[CI Triage Runner] Cleaning up stale runner '${RUNNER_NAME}' from GitHub..."
    EXISTING=$(curl -s -H "Authorization: token $GH_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "$API_BASE" | jq -r \
        ".runners[] | select(.name == \"${RUNNER_NAME}\") | .id") || true

    for id in $EXISTING; do
        echo "[CI Triage Runner]   Deleting stale runner ID $id ..."
        curl -s -X DELETE -H "Authorization: token $GH_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            "$API_BASE/$id" > /dev/null || true
    done

    # Generate fresh registration token
    echo "[CI Triage Runner] Generating fresh registration token..."
    REG_TOKEN=$(curl -s -X POST \
        -H "Authorization: token $GH_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/runners/registration-token" \
        | jq -r '.token') || true

    if [ "$REG_TOKEN" = "null" ] || [ -z "$REG_TOKEN" ]; then
        echo "[CI Triage Runner] ERROR: Could not generate registration token."
        echo "[CI Triage Runner] Check that GH_TOKEN has 'Administration: Write' scope."
        return 1
    fi

    RUNNER_TOKEN="$REG_TOKEN"
    export RUNNER_TOKEN
    GITHUB_URL="https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}"
    export GITHUB_URL
    rm -f /opt/actions-runner/.runner

    sudo -E -u runner /opt/actions-runner/configure.sh
    echo "[CI Triage Runner] Registration complete"
}

# --- Initial registration ---
# If .runner exists, try to use it. If registration fails (stale), re-register.
if [ -f /opt/actions-runner/.runner ]; then
    echo "[CI Triage Runner] Existing registration found (will re-register on failure)"
fi

# Always re-register on fresh start to avoid stale credentials
register_runner

# Write critical env vars to runner's .env file so they're available to job steps
echo "[CI Triage Runner] Writing env vars to .env for job steps..."
: > /opt/actions-runner/.env
for var in LLM_API_KEY LLM_PROVIDER GH_TOKEN; do
    val="${!var}"
    if [ -n "$val" ]; then
        echo "${var}=${val}" >> /opt/actions-runner/.env
        echo "[CI Triage Runner]   ✓ ${var} written to .env ($(echo "$val" | wc -c) chars)"
    else
        echo "[CI Triage Runner]   ✗ ${var} is EMPTY — skipped"
    fi
done
chown runner:runner /opt/actions-runner/.env
echo "[CI Triage Runner] .env file contents:"
cat /opt/actions-runner/.env

# --- Runner daemon loop ---
# Restart the runner if it crashes, re-register if registration is stale.
cleanup() {
    echo "[CI Triage Runner] Shutting down..."
    RUNNER_PID_TO_KILL="${RUNNER_PID:-}"
    WATCHER_PID_TO_KILL="${WATCHER_PID:-}"
    DOCKER_PID_TO_KILL="${DOCKER_PID:-}"

    # Remove this runner from GitHub so it doesn't appear offline
    if [ -f /opt/actions-runner/.runner ] && [ -n "$GH_TOKEN" ] && [ -n "$GITHUB_OWNER" ] && [ -n "$GITHUB_REPO" ]; then
        RUNNER_ID=$(cat /opt/actions-runner/.runner | python3 -c "import sys,json; print(json.load(sys.stdin).get('agentId', ''))" 2>/dev/null || true)
        if [ -n "$RUNNER_ID" ]; then
            echo "[CI Triage Runner] Removing runner ID $RUNNER_ID from GitHub..."
            curl -s -X DELETE \
                -H "Authorization: token $GH_TOKEN" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/runners/${RUNNER_ID}" > /dev/null 2>&1 || true
        fi
    fi

    [ -n "$RUNNER_PID_TO_KILL" ] && kill -TERM "$RUNNER_PID_TO_KILL" 2>/dev/null || true
    [ -n "$RUNNER_PID_TO_KILL" ] && wait "$RUNNER_PID_TO_KILL" 2>/dev/null || true
    [ -n "$WATCHER_PID_TO_KILL" ] && kill -TERM "$WATCHER_PID_TO_KILL" 2>/dev/null || true
    [ -n "$WATCHER_PID_TO_KILL" ] && wait "$WATCHER_PID_TO_KILL" 2>/dev/null || true
    [ -n "$DOCKER_PID_TO_KILL" ] && kill -TERM "$DOCKER_PID_TO_KILL" 2>/dev/null || true
    [ -n "$DOCKER_PID_TO_KILL" ] && wait "$DOCKER_PID_TO_KILL" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

echo "[CI Triage Runner] Starting runner daemon (auto-restart on crash)..."
while true; do
    echo "[CI Triage Runner] Launching runner (attempt)..."
    sudo -u runner /opt/actions-runner/run.sh "$@" &
    RUNNER_PID=$!

    # Wait for the runner to exit
    set +e
    wait "$RUNNER_PID"
    EXIT_CODE=$?
    set -e

    echo "[CI Triage Runner] Runner exited (code: $EXIT_CODE). Restarting in 5s..."
    sleep 5

    # If the session failed because registration was revoked, re-register
    if [ $EXIT_CODE -ne 0 ] && [ -n "$GH_TOKEN" ]; then
        echo "[CI Triage Runner] Re-registering runner..."
        register_runner || true
    fi
done
