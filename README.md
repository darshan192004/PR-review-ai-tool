# CI Triage Agent

AI-driven CI failure & bug triage agent. Deploys as a **custom Forgejo runner** — zero YAML in any repo. When CI fails, it automatically diagnoses the root cause and posts a fix suggestion to the PR.

```
┌─ Developer pushes PR ──→ Forgejo runner starts ──→ CI fails ──→ ─┐
│  docker_watcher.py detects exit code ≠ 0                           │
│  → extracts build log                                              │
│  → calls Gemini API                                                 │
│  → parses root cause + code patch                                   │
│  → posts diagnosis to PR timeline                                   │
└────────────────────────────────────────────────────────────────────┘
AI-driven CI failure & bug triage agent. Deploys as a **self-hosted GitHub Actions runner** with Docker-in-Docker. When CI fails, it automatically diagnoses the root cause and posts a fix suggestion as a commit or PR comment.

```mermaid
flowchart LR
    A[Developer pushes PR] --> B[GitHub Actions triggers workflow]
    B --> C[Self-hosted runner executes job]
    C --> D{CI fails?}
    D -- Yes --> E[ci-triage-agent extracts logs]
    E --> F[LLM diagnoses root cause]
    F --> G[Posts fix suggestion to PR / commit]
    D -- No --> H[✅ Success - no action]
```

## How It Works

```mermaid
flowchart TB
    subgraph Host[Machine - Docker Host]
        subgraph Container[ci-triage-runner Container]
            direction TB
            R[GitHub Actions Runner<br/>listens for jobs] --> J[Job container<br/>runs user's CI scripts]
            W[ci-triage-agent watcher<br/>monitors Docker events]
            J -- exit code ≠ 0 --> W
            W --> L[LLM diagnoses failure]
            L --> C[Posts comment via GitHub API]
        end
        DS[Docker Socket<br/>/var/run/docker.sock]
    end
    GH[GitHub] -->|assigns job| R
    C -->|POST /repos/.../issues/.../comments| GH
```

```
┌──────────────────────────────────────────────────────────────────────┐
│  Developer pushes PR ───────────────→ CI fails ──────────────────────┤
│  ci-triage-agent extracts build log → calls LLM → posts to PR/commit │
└──────────────────────────────────────────────────────────────────────┘
```

```
┌───────────────────────────────────────────────────────────────────────┐
│  HOST MACHINE                                                         │
│                                                                       │
│  ┌───────────────────────────────────────────────────────────┐        │
│  │  ci-triage-runner (Docker container)                      │        │
│  │                                                           │        │
│  │  ┌──────────────────────┐  ┌────────────────────────────┐ │        │
│  │  │  GitHub Runner       │  │  ci-triage-agent watcher   │ │        │
│  │  │  (unmodified)        │  │  (Python daemon)           │ │        │
│  │  │                      │  │                            │ │        │
│  │  │  Listens for jobs    │  │  docker events --filter    │ │        │
│  │  │  from GitHub         │  │  'event=die'               │ │        │
│  │  └─────────┬───────────┘  │                             │ │        │
│  │            │              │  → inspect container        │ │        │
│  │            │              │  → docker logs --tail 200   │ │        │
│  │            │              │  → call LLM API             │ │        │
│  │            │              │  → POST comment to PR       │ │        │
│  │            │              └──────────┬──────────────────┘ │        │
│  └────────────┼─────────────────────────┼────────────────────┘        │
│               │                         │                             │
│               ▼                         │                             │
│  ┌─────────────────────────┐            │                             │
│  │  Job Container           │           │                             │
│  │  (user's CI scripts)     │           │                             │
│  │                          │           │                             │
│  │  Runs: pytest, build,    │           │                             │
│  │  lint, etc.              │           │                             │
│  │                          │           │                             │
│  │  Env: GITHUB_ACTIONS=true│           │                             │
│  │       GITHUB_REPOSITORY=X│           │                             │
│  └──────────┬───────────────┘           │                             │
│             │                           │                             │
│             └── exits with code ≠ 0 ────┘                             │
│                                                                       │
│  Docker Socket (/var/run/docker.sock)                                 │
└───────────────────────────────────────────────────────────────────────┘
```

## Screenshots

### Commit Comment
<!-- TODO: Insert screenshot of bot posting a diagnosis on a commit -->
![Commit Comment Screenshot]()

### PR Comment
<!-- TODO: Insert screenshot of bot posting a diagnosis on a PR -->
![PR Comment Screenshot]()

## Quick Start

### Prerequisites

- A machine with Docker installed
- A GitHub repository with Actions enabled
- An LLM API key (Gemini / OpenAI / Anthropic)

### Step 1 — Get an LLM API Key

| Provider | Where to get it |
|----------|----------------|
| **Gemini** | [Google AI Studio](https://aistudio.google.com/apikey) |
| **OpenAI** | [OpenAI Platform](https://platform.openai.com/api-keys) |
| **Anthropic** | [Anthropic Console](https://console.anthropic.com/) |

### Step 2 — Build the runner image

```bash
git clone https://github.com/your-org/PR-review-ai-tool.git
cd PR-review-ai-tool
sudo docker build -t ci-triage-runner-github:latest -f runner-github/Dockerfile .
```

### Step 3 — Register and run

1. Go to your repo: **Settings → Actions → Runners → New runner**
2. Copy the registration token
3. Run the container:

```bash
sudo docker run -d \
  --name ci-triage-runner \
  --restart unless-stopped \
  --privileged \
  -e GITHUB_OWNER=your-org \
  -e GITHUB_REPO=your-repo \
  -e RUNNER_TOKEN=<token-from-step-2> \
  -e GH_TOKEN=<github-pat-with-repo-scope> \
  -e LLM_API_KEY=<your-llm-api-key> \
  -e LLM_PROVIDER=gemini \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ci-triage-runner-github:latest
```

### Step 4 — Add the workflow to your repo

Create `.github/workflows/ci-triage.yml` in your repository:

```yaml
name: CI Triage Agent

"on":
  push:
  pull_request:
    types: [opened, synchronize]
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  test:
    runs-on: [self-hosted, ci-triage]
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: |
          # Your test commands here
          pytest || exit 1
      - name: Upload build log
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: build-log
          path: build.log
          retention-days: 1

  triage:
    if: failure()
    needs: [test]
    runs-on: [self-hosted, ci-triage]
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - name: Download build log
        uses: actions/download-artifact@v4
        with:
          name: build-log
      - name: Install ci-triage-agent
        run: pip install .
      - name: Run AI Triage
        env:
          LLM_PROVIDER: ${{ vars.LLM_PROVIDER || 'gemini' }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO_OWNER: ${{ github.repository_owner }}
          REPO_NAME: ${{ github.event.repository.name }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          COMMIT_SHA: ${{ github.sha }}
          LOG_LINES: "200"
          LLM_TIMEOUT: "60"
        run: ci-triage-agent --log-file build.log
```

That's it. The runner will:
1. Connect to GitHub
2. Pick up CI jobs labeled `self-hosted` + `ci-triage`
3. When a job fails → triage job runs → AI posts diagnosis to PR or commit

### How routing works

```mermaid
flowchart TD
    A[CI fails] --> B{Has PR number?}
    B -- Yes --> C[Post PR comment]
    B -- No --> D{Can detect PR<br/>from commit SHA?}
    D -- Yes --> C
    D -- No --> E[Post commit comment]
```

## Local Testing

### Test the triage pipeline (CLI)

```bash
pip install -e .

export LLM_API_KEY="your-key"

# Test with a sample log — calls LLM and prints diagnosis
ci-triage-agent --print --log-file tests/fixtures/sample_error_log.txt

# Test with a live failure
python -c "x = undefined_name" 2>&1 | ci-triage-agent --print

# See the prompt without calling LLM (dry-run)
ci-triage-agent --dry-run --log-file tests/fixtures/sample_error_log.txt
```

### Test the watcher

```bash
# Start the watcher in dry-run mode (won't call Gemini or post)
python -m ci_triage_agent.cli.watcher_entry --dry-run

# In another terminal, simulate a CI container failure:
docker run --rm -e GITHUB_ACTIONS=true \
  -e GITHUB_REPOSITORY=test/test \
  -e GITHUB_REF=refs/pull/1/head \
  alpine sh -c "echo 'test error' && exit 1"
```

## Architecture

```
src/ci_triage_agent/
├── __init__.py              # Package exports
├── __main__.py              # CLI entry point
├── cli/
│   ├── __init__.py
│   ├── parser.py            # CLI argument definitions
│   ├── orchestrator.py      # Triage pipeline orchestration
│   └── watcher_entry.py     # Watcher daemon entry point
├── config/
│   ├── __init__.py
│   └── settings.py          # AppSettings — environment config
├── models/
│   ├── __init__.py
│   └── diagnosis.py         # Diagnosis domain model
├── llm/
│   ├── __init__.py
│   └── client.py            # LLMClient (Gemini/OpenAI/Anthropic)
├── ci/
│   ├── __init__.py
│   └── platform.py          # CI platform integration (GitHub/Forgejo)
├── pipeline/
│   ├── __init__.py
│   ├── log_context.py       # Log tail extraction
│   ├── diagnosis_prompt.py  # System prompt assembly
│   └── diagnosis_parser.py  # LLM response → Diagnosis model
└── monitoring/
    ├── __init__.py
    └── docker_watcher.py    # Docker event watcher daemon

runner-github/
├── Dockerfile           # DinD runner image
├── dind-entrypoint.sh   # Starts dockerd + watcher + runner
├── configure.sh         # Runner registration helper
└── entrypoint.sh        # Non-DinD entrypoint
```

## Configuration

### Agent environment variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `LLM_API_KEY` | — | ✅ | Gemini / OpenAI / Anthropic API key |
| `LLM_PROVIDER` | `gemini` | — | `gemini`, `openai`, or `anthropic` |
| `GITHUB_TOKEN` | — | ✅ | GitHub token for posting comments |
| `GH_TOKEN` | — | — | Fallback for GITHUB_TOKEN |
| `REPO_OWNER` | — | ✅ | GitHub repo owner |
| `REPO_NAME` | — | ✅ | GitHub repo name |
| `PR_NUMBER` | — | — | PR number (auto-detected for PR events) |
| `COMMIT_SHA` | — | — | Commit SHA (auto-detected) |
| `LOG_LINES` | `200` | — | Log lines to analyze |
| `LLM_TIMEOUT` | `60` | — | LLM API timeout (seconds) |
| `LLM_MAX_RETRIES` | `3` | — | Retries on transient API errors |
| `LOG_LEVEL` | `INFO` | — | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Runner container environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_OWNER` | ✅ | GitHub org/user that owns the repo |
| `GITHUB_REPO` | ✅ | Repository name |
| `RUNNER_TOKEN` | ✅ | Runner registration token from GitHub |
| `GH_TOKEN` | ✅ | GitHub PAT with `repo` scope |
| `LLM_API_KEY` | ✅ | LLM provider API key |
| `LLM_PROVIDER` | — | LLM provider (default: `gemini`) |
| `CI_TRIAGE_WATCHER` | — | Set to `true` to enable watcher daemon |
| `GITHUB_ACTIONS_RUNNER` | — | Set to `true` to enable runner |

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Production Deployment

### Monitor the runner

```bash
# Live logs
sudo docker logs ci-triage-runner --follow

# Check status
sudo docker ps --filter name=ci-triage-runner

# Resource usage
sudo docker stats ci-triage-runner --no-stream
```

### Rolling update

```bash
sudo docker build -t ci-triage-runner-github:latest -f runner-github/Dockerfile .
sudo docker rm -f ci-triage-runner
sudo docker run -d \
  --name ci-triage-runner \
  --restart unless-stopped \
  --privileged \
  -e GITHUB_OWNER=your-org \
  -e GITHUB_REPO=your-repo \
  -e RUNNER_TOKEN=<fresh-token> \
  -e GH_TOKEN=<pat> \
  -e LLM_API_KEY=<key> \
  -e LLM_PROVIDER=gemini \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ci-triage-runner-github:latest
```

## Deployment on Existing Runners

### Option A: Forgejo (Self-Hosted Runner)

You need: a Forgejo server with Actions enabled, a host with Docker, and a bot token.

#### 1. Create a bot user and token

```
Forgejo Settings → Users → Create New User
  Username: ci-triage-bot
  Email: ci-triage-bot@yourcompany.com
  Password: (generate a strong one)

Log in as ci-triage-bot → Settings → Applications → Generate Token
  Name: ci-triage-agent
  Scope: write:repository, read:repository
  → Copy the token (starts with AQ.)
```

#### 2. Set up environment

```bash
export LLM_API_KEY="AIzaSy..."                  # Gemini API key
export GITEA_TOKEN="AQ..."                       # Forgejo bot token
export FORGEJO_URL="https://forgejo.yourcompany.com"
```

#### 3. Register the runner

```bash
docker compose run --rm ci-triage-runner \
  act_runner register \
    --instance $FORGEJO_URL \
    --token <runner-registration-token> \
    --name ci-triage-runner \
    --labels ubuntu-latest:docker://node:20-bookworm
```

The registration token is found at your Forgejo instance under:
`Site Admin → Actions → Runners → Create New Runner`

#### 4. Start the runner stack

```bash
docker compose up -d
```

This starts both the `act_runner` daemon (picks up CI jobs) and the `ci-triage-watcher` daemon (monitors for failures).

To verify the watcher is running:

```bash
docker compose logs -f ci-triage-runner | grep "CI Triage Watcher"
```

---

### Option B: GitHub (Self-Hosted Runner)

You need: a GitHub account with a self-hosted runner, a host with Docker, and a PAT.

#### 1. Create a GitHub Personal Access Token

```
GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
  Repository access: All repositories
  Permissions: Issues: Write
  → Copy the token (ghp_...)
```

#### 2. Set up environment

```bash
export LLM_API_KEY="AIzaSy..."                  # Gemini API key
export GITHUB_TOKEN="ghp_..."                    # GitHub PAT
```

#### 3. Build and start the watcher sidecar

```bash
docker compose -f docker-compose.watcher.yml up -d --build
```

This starts only the `ci-triage-watcher` as a standalone container. It assumes you already have a GitHub self-hosted runner running on the same host.

#### 4. Add watcher to an existing GitHub runner host

If you already have a GitHub Actions runner installed directly on the host (not in Docker), run the watcher as a companion container:

```bash
docker run -d \
  --name ci-triage-watcher \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e LLM_API_KEY=$LLM_API_KEY \
  -e GITHUB_TOKEN=$GITHUB_TOKEN \
  ci-triage-watcher:latest
```

---

### Option C: Deploy Without Docker (Bare Metal)

For environments where Docker-in-Docker is not available, or for debugging:

#### 1. Install the package

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

#### 2. Run the CLI triage

```bash
export LLM_API_KEY="AIzaSy..."
ci-triage-agent --print --log-file tests/fixtures/sample_error_log.txt
```

#### 3. Run the watcher daemon directly

```bash
export LLM_API_KEY="AIzaSy..."
export GITHUB_TOKEN="ghp_..."   # or GITEA_TOKEN="AQ..."
ci-triage-watcher
```

---

### Required Environment Variables Reference

| Variable | Required | Forgejo | GitHub | Description |
|---|---|---|---|---|
| `LLM_API_KEY` | ✅ | ✅ | ✅ | Gemini/OpenAI/Anthropic API key |
| `GITEA_TOKEN` | ✅* | ✅ | — | Forgejo bot token |
| `GITHUB_TOKEN` | ✅* | — | ✅ | GitHub PAT with `issues: write` |
| `FORGEJO_URL` | ✅ | ✅ | — | Your Forgejo instance URL |
| `LLM_PROVIDER` | — | optional | optional | `gemini` (default), `openai`, `anthropic` |
| `LOG_LINES` | — | optional | optional | Tail lines to analyze (default: 200) |
| `LOG_LEVEL` | — | optional | optional | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

*One of `GITEA_TOKEN` or `GITHUB_TOKEN` is required depending on your CI provider.

---

### Verifying the Deployment

#### Test the pipeline without posting

```bash
ci-triage-agent --dry-run --log-file tests/fixtures/sample_error_log.txt
```

Expected output: the full prompt that would be sent to the LLM, ending with `=== END PROMPT ===`.

#### Test end-to-end with a sample log

```bash
ci-triage-agent --print --log-file tests/fixtures/sample_error_log.txt
```

Expected output: a formatted Markdown diagnosis with root cause, affected file, and code patch.

#### Test the watcher

```bash
# In terminal 1: start watcher in dry-run mode
ci-triage-watcher --dry-run

# In terminal 2: simulate a CI failure
docker run --rm \
  -e GITHUB_ACTIONS=true \
  -e GITHUB_REPOSITORY=test-org/test-repo \
  -e GITHUB_REF=refs/pull/1/head \
  alpine sh -c "echo 'intentional failure' && exit 1"
```

Terminal 1 should log the detection and print the prompt.

---
## Forgejo / Gitea Setup

The same agent also works with Forgejo / Gitea Actions. Set `GITEA_TOKEN` and `FORGEJO_URL` instead of `GITHUB_TOKEN`. The agent auto-detects the provider.

## Security

- API keys injected via environment variables only — never written to disk
- The agent is **read-only** — it never modifies code, only reads logs and posts comments
- LLM responses are validated before posting (must contain expected sections)
- Bot token scoped to minimal permissions
- The watcher only inspects containers with `CI_PROVIDER` labels — ignores unrelated containers

## FAQ

**Q: Does this work with GitHub Actions?**  
Yes. The default setup uses GitHub Actions with a self-hosted runner.

**Q: Does this work with Forgejo / Gitea?**  
Yes. Set `GITEA_TOKEN` and `FORGEJO_URL` instead of `GITHUB_TOKEN`.

**Q: What if the LLM is wrong?**  
The agent posts as a bot comment — it's advisory. Developers review and decide.

**Q: What if the runner machine goes offline?**  
Jobs queue on GitHub and run when the machine comes back. The container auto-starts if Docker is configured with `--restart unless-stopped`.

**Q: What if the runner can't reach the internet?**  
The LLM API requires internet access. For air-gapped setups, deploy a local Ollama instance.

**Q: Does every repo need setup?**  
The runner is registered once per repo. The workflow YAML must be present in each repo that wants triage.
