"""
ci-triage-watcher — Docker event watcher daemon.

Runs inside a Forgejo/GitHub Actions runner container.
Monitors Docker events for failed job containers, extracts
logs, runs AI triage, and posts comments to PRs.

Usage:
  python -m ci_triage_agent.watcher
  python -m ci_triage_agent.watcher --dry-run
"""

import argparse
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time

from .config import EnvConfig
from .log_extractor import extract_log_context
from .prompt_builder import build_prompt
from .llm_client import LLMClient
from .response_parser import parse_response
from .ci_client import post_pr_comment

logger = logging.getLogger(__name__)


class ForgejoWatcher:
    def __init__(self, config: EnvConfig, dry_run: bool = False) -> None:
        self.config = config
        self.dry_run = dry_run
        self._running = False

    def run(self) -> None:
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
                        self._handle_event(event)
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

    def _handle_event(self, event: dict) -> None:
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

        context = self._extract_context(container_id)
        if not context:
            return

        logs = self._get_container_logs(container_id)
        if not logs:
            return

        self._run_triage(context, logs)

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

    def _extract_context(self, container_id: str) -> dict | None:
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

        if not repo or not pr_number:
            logger.warning(
                "Cannot determine PR context: repo=%s pr=%s", repo, pr_number
            )
            return None

        if "/" in repo:
            owner, repo_name = repo.split("/", 1)
        else:
            owner, repo_name = "", repo

        logger.info("PR context: %s/%s PR #%s", owner, repo_name, pr_number)

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

    def _run_triage(self, context: dict, logs: str) -> None:
        logger.info(
            "Running triage for %s/%s PR #%s",
            context["owner"], context["repo"], context["pr_number"],
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

        success = post_pr_comment(self.config, comment_body)
        if success:
            logger.info(
                "Triage complete — comment posted to %s/%s PR #%s",
                context["owner"], context["repo"], context["pr_number"],
            )
        else:
            logger.error("Failed to post triage comment")


def parse_watcher_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ci-triage-watcher",
        description="Docker event watcher for CI Triage Agent",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompt without calling LLM or posting comments",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_watcher_args()
    cfg = EnvConfig.load()

    if args.log_level:
        cfg.LOG_LEVEL = args.log_level

    logging.basicConfig(
        level=getattr(logging, cfg.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    watcher = ForgejoWatcher(config=cfg, dry_run=args.dry_run)
    try:
        watcher.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
