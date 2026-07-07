#!/usr/bin/env bash
#
# validate_e2e.sh — End-to-End Validation of CI Triage Agent
#
# This script:
#   1. Creates a test branch with intentionally broken code
#   2. Pushes the branch and opens a PR
#   3. Waits for CI to run (with the triage agent)
#   4. Checks that the triage agent posted a comment on the PR
#   5. Cleans up the test branch and PR
#
# Prerequisites:
#   - gh CLI installed and authenticated
#   - CI workflow configured in your repo (with LLM_API_KEY secret)
#   - GITHUB_TOKEN with write access to pull requests
#
# Usage:
#   export GITHUB_TOKEN=ghp_xxx
#   bash scripts/validate_e2e.sh <owner/repo>
#
# Example:
#   bash scripts/validate_e2e.sh myuser/my-repo
#

set -euo pipefail

REPO="${1:?Usage: $0 <owner/repo>}"
BRANCH="triage-e2e-test-$(date +%s)"
BASE_BRANCH="main"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== CI Triage Agent — E2E Validation ==="
echo "Repo:   $REPO"
echo "Branch: $BRANCH"
echo ""

# ── Step 1: Create test branch with broken code ──
echo ">>> Creating test branch: $BRANCH"
git checkout -b "$BRANCH"

echo ">>> Adding intentionally broken test"
cp "$PROJECT_DIR/scripts/test_failure_example.py" "$PROJECT_DIR/"

git add test_failure_example.py
git commit -m "test: intentionally broken test for CI Triage Agent E2E validation

This commit adds a test that will fail deliberately to verify the
CI Triage Agent captures the failure, analyzes it via LLM, and
posts a diagnostic comment on the PR.

Co-authored-by: CI Triage Agent <triage@ci-agent.local>
"

echo ">>> Pushing branch"
git push origin "$BRANCH"

# ── Step 2: Create PR ──
echo ">>> Creating pull request"
PR_URL=$(gh pr create \
    --repo "$REPO" \
    --base "$BASE_BRANCH" \
    --head "$BRANCH" \
    --title "E2E Test: Intentionally Broken Test" \
    --body "This PR is an automated end-to-end test for the CI Triage Agent.

**Expected behavior:**
1. CI runs and the broken test \`test_calculate_total_zero_quantity\` fails
2. The CI Triage Agent triggers on failure
3. The agent posts a PR comment identifying the root cause and suggesting a fix

If you see a comment from the CI Triage Agent on this PR, the system is working correctly.

**To clean up:** Close this PR without merging and delete the branch \`$BRANCH\`."
)

echo "PR created: $PR_URL"

# ── Step 3: Wait for CI to run ──
echo ""
echo ">>> Waiting for CI to complete (max 5 minutes)..."
echo "    Check $PR_URL for results"

# Wait for CI checks to appear
sleep 30

MAX_WAIT=300  # 5 minutes
INTERVAL=30
elapsed=0
comment_found=false

while [ $elapsed -lt $MAX_WAIT ]; do
    echo "    Checking for triage comment... (${elapsed}s elapsed)"

    # Check if the triage agent has posted a comment
    COMMENTS=$(gh api "/repos/$REPO/issues/$(echo "$PR_URL" | grep -oP '\d+$')/comments" \
        --jq '.[] | select(.user.login | test("(?i)(triage|bot|agent|github-actions)")) | .body' 2>/dev/null || echo "")

    if [ -n "$COMMENTS" ]; then
        echo ""
        echo "✓ SUCCESS: CI Triage Agent comment detected!"
        echo ""
        echo "=== Comment Preview ==="
        echo "$COMMENTS" | head -20
        echo "..."
        comment_found=true
        break
    fi

    sleep $INTERVAL
    elapsed=$((elapsed + INTERVAL))
done

# ── Step 4: Report result ──
if [ "$comment_found" = false ]; then
    echo ""
    echo "✗ TIMEOUT: No triage comment found within $MAX_WAIT seconds."
    echo "  Possible issues:"
    echo "  - CI workflow not triggered (check Actions tab)"
    echo "  - LLM_API_KEY secret not set"
    echo "  - Triage agent step not included in workflow"
    echo "  - if: failure() gate not matching"
    echo ""
    echo "  PR URL: $PR_URL"
fi

# ── Step 5: Cleanup ──
echo ""
echo ">>> Cleaning up..."

# Close the PR without merging
gh pr close "$PR_URL" --comment "E2E validation complete" 2>/dev/null || true

# Delete the remote branch
git push origin --delete "$BRANCH" 2>/dev/null || true

# Switch back to base branch
git checkout "$BASE_BRANCH" 2>/dev/null || true

# Delete local branch
git branch -D "$BRANCH" 2>/dev/null || true

# Remove the test file
rm -f "$PROJECT_DIR/test_failure_example.py"

echo ""
echo "=== E2E Validation Complete ==="

if [ "$comment_found" = true ]; then
    echo "Result: ✓ PASS — CI Triage Agent is working correctly"
    exit 0
else
    echo "Result: ✗ FAIL — Check CI logs for details"
    exit 1
fi
