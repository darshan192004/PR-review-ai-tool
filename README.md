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
```

## How It Works

```
┌──────────────────────────────────────────────────────────────────┐
│  HOST MACHINE                                                     │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  forgejo/ci-triage-runner (Docker container)              │    │
│  │                                                           │    │
│  │  ┌──────────────────────┐  ┌──────────────────────────┐  │    │
│  │  │  act_runner daemon    │  │  ci-triage-watcher       │  │    │
│  │  │  (unmodified)         │  │  (Python daemon)         │  │    │
│  │  │                       │  │                          │  │    │
│  │  │  Polls Forgejo for   │  │  docker events --filter   │  │    │
│  │  │  jobs → spawns       │  │  'event=die'             │  │    │
│  │  │  job containers      │  │                          │  │    │
│  │  └─────────┬────────────┘  │  → inspect container     │  │    │
│  │            │               │  → docker logs --tail 200 │  │    │
│  │            │               │  → call Gemini API        │  │    │
│  │            │               │  → POST comment to PR    │  │    │
│  │            │               └──────────┬───────────────┘  │    │
│  └────────────┼──────────────────────────┼──────────────────┘    │
│               │                          │                        │
│               ▼                          │                        │
│  ┌──────────────────────────┐             │                       │
│  │  Job Container            │             │                       │
│  │  (user's CI scripts)      │             │                       │
│  │                           │             │                       │
│  │  Runs: pytest, build,     │             │                       │
│  │  lint, etc.               │             │                       │
│  │                           │             │                       │
│  │  Env: GITHUB_ACTIONS=true │             │                       │
│  │       GITHUB_REPOSITORY=X │             │                       │
│  │       GITHUB_REF=pull/42  │             │                       │
│  └──────────┬────────────────┘             │                       │
│             │                              │                       │
│             └── exits with code ≠ 0 ───────┘                       │
│                                                                    │
│  Docker Socket (/var/run/docker.sock)                              │
└────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- A Forgejo server (v1.21+ with Actions enabled)
- A machine to host the runner (can be the same as the Forgejo server)
- Docker installed on the host machine

### Step 1 — Get a Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Click **Get API Key** → **Create API Key**
3. Copy the key (starts with `AIzaSy...` or `AQ.`)

### Step 2 — Create a Bot User on Forgejo

```
1. Forgejo Settings → Users → Create New User
   Username: ci-triage-bot
   Email: ci-triage-bot@yourcompany.com
   Password: (generate a strong one)

2. Log in as ci-triage-bot → Settings → Applications
   → Generate Token
   Name: ci-triage-agent
   Scope: write:repository, read:repository
   → Copy the token (starts with AQ.)
```

### Step 3 — Configure and Run

```bash
# Clone the repo
git clone https://github.com/your-org/ci-triage-agent.git
cd ci-triage-agent

# Set environment variables
export LLM_API_KEY="AIzaSy..."           # Gemini API key
export GITEA_TOKEN="AQ..."                # Forgejo bot token
export FORGEJO_URL="https://forgejo.yourcompany.com"

# Register the runner with your Forgejo instance
docker compose run --rm ci-triage-runner \
  act_runner register \
    --instance $FORGEJO_URL \
    --token <runner-registration-token> \
    --name ci-triage-runner \
    --labels ubuntu-latest:docker://node:20-bookworm

# Start the runner
docker compose up -d
```

That's it. The runner will:
1. Connect to your Forgejo instance
2. Pick up CI jobs from ANY repo on that instance
3. When a job fails → watcher detects it → runs AI triage → posts PR comment

```
┌─── Any developer pushes to ANY repo on your Forgejo ─────────┐
│                                                                │
│  No YAML files needed. No workflow changes.                    │
│  The runner handles everything automatically.                  │
│                                                                │
│  PR comment appears as "ci-triage-bot" —                      │
│  everyone knows it's the AI agent, not a person.              │
└────────────────────────────────────────────────────────────────┘
```

## GitHub Actions Setup (No Forgejo Required)

If you use GitHub Actions (self-hosted runners), the watcher works the same way — just with a GitHub token instead of a Forgejo token.

```
┌─────────────────────────────────────────────────────────┐
│  HOST MACHINE (your self-hosted runner server)           │
│                                                          │
│  ┌────────────────────┐   ┌──────────────────────────┐  │
│  │ GitHub Runner       │   │ ci-triage-watcher        │  │
│  │ (existing)          │   │ (standalone container)   │  │
│  │                     │   │                          │  │
│  │ Runs jobs sent      │   │ docker events --filter   │  │
│  │ from GitHub         │   │ 'event=die'              │  │
│  └─────────┬──────────┘   │                          │  │
│            │              │ → inspect container      │  │
│            ▼              │ → docker logs --tail 200 │  │
│  ┌──────────────────┐    │ → call Gemini API         │  │
│  │ Job Container     │    │ → POST to GitHub PR      │  │
│  └──────────┬────────┘    └──────────┬───────────────┘  │
│             │                        │                  │
│             └── exit code ≠ 0 ───────┘                  │
│                                                          │
│  Docker Socket (/var/run/docker.sock)                    │
└──────────────────────────────────────────────────────────┘
```

### Step 1 — Set up the watcher

```bash
# Clone the repo
git clone https://github.com/your-org/ci-triage-agent.git
cd ci-triage-agent

# Set environment variables
export LLM_API_KEY="AIzaSy..."           # Gemini API key
export GITHUB_TOKEN="ghp_..."             # GitHub PAT with write:issues scope

# Build and start the watcher
docker compose -f docker-compose.watcher.yml up -d --build
```

### Step 2 — Create a GitHub Token

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Generate new token
3. Repository access: `All repositories`
4. Permissions: `Issues: Write` (for posting PR comments)
5. Copy the token

For a bot identity, create a dedicated GitHub App or machine user account.

### Step 3 — How it works

```
Developer pushes PR → GitHub assigns to your self-hosted runner
  → Runner spawns container → tests fail (exit code ≠ 0)
  → Watcher detects: GITHUB_ACTIONS=true in container env
  → docker inspect → gets GITHUB_REPOSITORY, GITHUB_REF (pull/42)
  → docker logs --tail 200 → capture error output
  → calls Gemini API → parses root cause + code patch
  → POST to api.github.com/repos/.../issues/42/comments
  → Comment appears on the PR
```

No YAML changes in any repo. The watcher runs as a sidecar alongside your existing self-hosted GitHub runner.

### Step 4 — Migrate to Forgejo later

When you get Forgejo admin rights, the only changes are environment variables:

```bash
# Before (GitHub)
export GITHUB_TOKEN="ghp_..."

# After (Forgejo)
export GITEA_TOKEN="AQ..."
export FORGEJO_URL="https://forgejo.yourcompany.com"
```

The watcher auto-detects the provider. No code changes needed.

## Local Testing

### Test the triage pipeline (CLI)

```bash
source .venv/bin/activate
export LLM_API_KEY="AIzaSy..."

# Test with a sample log — calls Gemini and prints diagnosis
ci-triage-agent --print --log-file tests/fixtures/sample_error_log.txt

# Test with a live failure
python -c "x = undefined_name" 2>&1 | ci-triage-agent --print

# See the prompt without calling Gemini (dry-run)
ci-triage-agent --dry-run --log-file tests/fixtures/sample_error_log.txt
```

The `--print` flag runs the full pipeline (extract → LLM → parse) and prints the
formatted diagnosis to stdout without posting to a PR — perfect for local testing.

### Test the watcher

```bash
# Start the watcher in dry-run mode (won't call Gemini or post)
python -m ci_triage_agent.cli.watcher_entry --dry-run

# In another terminal, simulate a CI container failure:
docker run --rm -e GITHUB_ACTIONS=true \
  -e GITHUB_REPOSITORY=test/test \
  -e GITHUB_REF=refs/pull/1/head \
  alpine sh -c "echo 'test error' && exit 1"
# → Watcher detects it, prints the prompt it would send
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

runner/
├── Dockerfile           # Custom Forgejo runner image
├── entrypoint.sh        # Starts watcher + act_runner
├── config.yml           # act_runner config template
└── .env.example         # Environment variables template
```

## Configuration

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `LLM_API_KEY` | — | ✅ | Gemini/OpenAI/Anthropic API key |
| `GITEA_TOKEN` | — | ✅ | Forgejo bot token (PR comment API) |
| `FORGEJO_URL` | — | ✅ | Your Forgejo server URL |
| `LLM_PROVIDER` | `gemini` | — | LLM backend: `gemini`, `openai`, `anthropic` |
| `LOG_LINES` | `200` | — | Log lines to analyze |
| `LLM_TIMEOUT` | `60` | — | LLM API timeout (seconds) |
| `LLM_MAX_RETRIES` | `3` | — | Retries on transient API errors |
| `LOG_LEVEL` | `INFO` | — | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Production Deployment

### Standalone container

```bash
docker run -d \
  --name ci-triage-runner \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v runner-data:/data \
  -e LLM_API_KEY=$LLM_API_KEY \
  -e GITEA_TOKEN=$GITEA_TOKEN \
  -e FORGEJO_URL=$FORGEJO_URL \
  ci-triage-runner:latest
```

### Systemd (without Docker Compose)

```
[Unit]
Description=CI Triage Runner
After=docker.service

[Service]
Restart=always
ExecStart=docker run --rm ...
ExecStop=docker stop ci-triage-runner

[Install]
WantedBy=multi-user.target
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

## Security

- API keys injected via environment variables only — never written to disk
- The agent is **read-only** — it never modifies code, only reads logs and posts comments
- LLM responses are validated before posting (must contain expected sections)
- Bot token scoped to `write:repository` only — minimal permission
- The watcher only inspects containers with `GITHUB_ACTIONS=true` — ignores unrelated containers

## FAQ

**Q: Does this work with GitHub Actions too?**  
Yes. The same code detects `GITHUB_ACTIONS=true` and posts via GitHub API. Set `GITHUB_TOKEN` instead of `GITEA_TOKEN`.

**Q: What if the LLM is wrong?**  
The agent posts as a bot comment — it's advisory. Developers review and decide. The prompt is engineered for precision (zero-shot, strict format, low temperature).

**Q: Does every repo need setup?**  
No. The runner is installed once on your infrastructure. It automatically handles every repo on the Forgejo instance.

**Q: What if the runner can't reach the internet?**  
The Gemini API requires internet access. For air-gapped setups, deploy a local Ollama instance and set `LLM_PROVIDER=ollama`.
