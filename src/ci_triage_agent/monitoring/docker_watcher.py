"""
Docker event watcher daemon for CI Triage Agent.

Runs inside a Forgejo/GitHub Actions runner container.
Monitors Docker events for failed job containers, extracts
logs, runs AI triage, and posts comments to PRs.

Usage:
  python -m ci_triage_agent.monitoring.docker_watcher
  python -m ci_triage_agent.cli.watcher_entry
"""

import json
import logging
import re
import signal
import subprocess
import time

from ..config.settings import AppSettings
from ..pipeline.log_context import extract_log_context
from ..pipeline.diagnosis_prompt import build_prompt
from ..llm.client import LLMClient
from ..pipeline.diagnosis_parser import parse_response
from ..ci.platform import post_diagnosis

logger = logging.getLogger(__name__)


class DockerWatcher:
    """Daemon that monitors Docker events for failed CI containers and triggers diagnosis."""

    def __init__(self, config: AppSettings, dry_run: bool = False) -> None:
        self.config = config
        self.dry_run = dry_run
        self._running = False

    def run(self) -> None:
        """Enter the main event loop, streaming Docker die events until signalled to stop."""
        self._running = True
        logger.info("CI Triage Watcher started (dry_run=%s)", self.dry_run)
        logger.info(
            "Watching Docker events: event=die, exitCode!=0"
        )

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        cmd = [
            "docker", "events",
            "--filter", "event=die",
            "--format", "{{json .}}",
        ]

        while self._running:
            try:
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1
                )
                for line in process.stdout:
                    if not self._running:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        self._process_container_exit(event)
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.error("Error handling event: %s", e)

                process.wait()
                if self._running:
                    logger.warning("Docker events stream ended, reconnecting...")
                    time.sleep(2)
            except FileNotFoundError:
                logger.error(
                    "Docker not found. Is this running inside a container "
                    "with the Docker socket mounted?"
                )
                break
            except Exception as e:
                logger.error("Watcher error: %s", e)
                if self._running:
                    time.sleep(5)

        logger.info("CI Triage Watcher stopped")

    def _handle_signal(self, signum: int, _frame) -> None:
        logger.info("Received signal %d, shutting down...", signum)
        self._running = False

    def _process_container_exit(self, event: dict) -> None:
        actor = event.get("Actor", {})
        attrs = actor.get("Attributes", {})
        exit_code = attrs.get("exitCode", "0")

        if exit_code == "0":
            return

        container_id = actor.get("ID", "")
        if not container_id:
            return

        if not self._is_ci_container(container_id):
            return

        logger.info(
            "Detected failed CI container: %s (exit code: %s)",
            container_id[:12], exit_code,
        )

        context = self._resolve_ci_environment(container_id)
        if not context:
            return

        logs = self._get_container_logs(container_id)
        if not logs:
            return

        self._execute_diagnosis(context, logs)

    def _is_ci_container(self, container_id: str) -> bool:
        try:
            result = subprocess.run(
                [
                    "docker", "inspect", container_id,
                    "--format", "{{json .Config.Env}}",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return False

            env_vars = json.loads(result.stdout)
            for env in env_vars:
                if env == "GITHUB_ACTIONS=true" or env == "GITEA_ACTIONS=true":
                    return True
            return False
        except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
            return False

    def _resolve_ci_environment(self, container_id: str) -> dict | None:
        try:
            result = subprocess.run(
                [
                    "docker", "inspect", container_id,
                    "--format", "{{json .Config.Env}}",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return None

            env_vars = json.loads(result.stdout)
            env_dict: dict[str, str] = {}
            for env in env_vars:
                if "=" in env:
                    key, value = env.split("=", 1)
                    env_dict[key] = value
        except (json.JSONDecodeError, ValueError, subprocess.TimeoutExpired):
            return None

        repo = env_dict.get("GITHUB_REPOSITORY") or env_dict.get("GITEA_REPOSITORY", "")
        ref = env_dict.get("GITHUB_REF") or env_dict.get("GITEA_REF", "")
        sha = env_dict.get("GITHUB_SHA") or env_dict.get("GITEA_SHA", "")
        api_url = env_dict.get("GITHUB_API_URL") or env_dict.get("GITEA_API_URL", "")

        pr_match = re.search(r"refs/pull/(\d+)/", ref)
        pr_number = pr_match.group(1) if pr_match else ""

        if not repo:
            logger.warning(
                "Cannot determine repo context: repo=%s", repo
            )
            return None

        if "/" in repo:
            owner, repo_name = repo.split("/", 1)
        else:
            owner, repo_name = "", repo

        target = f"PR #{pr_number}" if pr_number else f"commit {sha[:7]}" if sha else "unknown"
        logger.info("Repo context: %s/%s (%s)", owner, repo_name, target)

        return {
            "owner": owner,
            "repo": repo_name,
            "pr_number": pr_number,
            "sha": sha,
            "api_url": api_url,
        }

    def _get_container_logs(self, container_id: str) -> str | None:
        try:
            result = subprocess.run(
                [
                    "docker", "logs", container_id,
                    "--tail", str(self.config.LOG_LINES),
                ],
                capture_output=True, text=True, timeout=30,
            )
            output = result.stdout + result.stderr
            return output if output.strip() else None
        except subprocess.TimeoutExpired:
            logger.error("Timeout reading container logs")
            return None
        except OSError as e:
            logger.error("Error reading container logs: %s", e)
            return None

    def _execute_diagnosis(self, context: dict, logs: str) -> None:
        target = context["pr_number"] or context["sha"][:7] if context["sha"] else "unknown"
        logger.info(
            "Running triage for %s/%s (target: %s)",
            context["owner"], context["repo"], target,
        )

        prompt = build_prompt(logs)
        logger.debug("Prompt built (%d chars)", len(prompt))

        if self.dry_run:
            logger.info("DRY RUN — skipping LLM call and PR comment")
            print("=== PROMPT ===")
            print(prompt)
            print("=== END PROMPT ===")
            return

        if not self.config.LLM_API_KEY:
            logger.error("LLM_API_KEY not configured — skipping triage")
            return

        client = LLMClient(self.config)
        raw_response = client.analyze(prompt)
        if not raw_response:
            logger.error("LLM returned no response — skipping")
            return

        logger.info("LLM response received (%d chars)", len(raw_response))

        parsed = parse_response(raw_response)
        comment_body = parsed.format_markdown()

        if context["api_url"]:
            is_forgejo = any(
                word in context["api_url"].lower()
                for word in ("gitea", "forgejo", "codeberg")
            )
            if is_forgejo:
                self.config.CI_PROVIDER = "forgejo"
                self.config.FORGEJO_API_URL = context["api_url"]

        self.config.REPO_OWNER = context["owner"]
        self.config.REPO_NAME = context["repo"]
        self.config.PR_NUMBER = context["pr_number"]
        self.config.COMMIT_SHA = context["sha"]

        success = post_diagnosis(self.config, comment_body)
        if success:
            target = context["pr_number"] or context["sha"][:7]
            logger.info(
                "Triage complete — comment posted to %s/%s (target: %s)",
                context["owner"], context["repo"], target,
            )
        else:
            logger.error("Failed to post triage comment")


if __name__ == "__main__":
    from ..cli.watcher_entry import main as watcher_main
    watcher_main()
