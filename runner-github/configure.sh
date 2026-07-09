#!/bin/bash
set -e

: "${GITHUB_URL:?GITHUB_URL is required (e.g. https://github.com/your-org)}"
: "${RUNNER_TOKEN:?RUNNER_TOKEN is required}"

RUNNER_NAME="${RUNNER_NAME:-ci-triage-runner-$(hostname)}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,ci-triage}"
RUNNER_GROUP="${RUNNER_GROUP:-default}"
REPLACE_RUNNER="${REPLACE_RUNNER:-true}"

echo "[CI Triage Runner] Registering runner:"
echo "  URL:      $GITHUB_URL"
echo "  Name:     $RUNNER_NAME"
echo "  Labels:   $RUNNER_LABELS"
echo "  Group:    $RUNNER_GROUP"

./config.sh \
    --url "$GITHUB_URL" \
    --token "$RUNNER_TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "$RUNNER_LABELS" \
    --runnergroup "$RUNNER_GROUP" \
    --replace "$REPLACE_RUNNER" \
    --unattended

echo "[CI Triage Runner] Registration complete"
