import logging
import os

import requests

from .config import EnvConfig

logger = logging.getLogger(__name__)


def _get_pr_context(
    cfg: EnvConfig,
) -> tuple[str, str, str, str] | None:
    owner = cfg.REPO_OWNER
    repo = cfg.REPO_NAME
    pr_number = cfg.PR_NUMBER

    if not owner:
        owner = os.environ.get("GITHUB_REPOSITORY_OWNER") or os.environ.get(
            "GITEA_REPOSITORY_OWNER"
        )
    if not repo:
        full_repo = os.environ.get("GITHUB_REPOSITORY") or os.environ.get(
            "GITEA_REPOSITORY"
        )
        if full_repo and "/" in full_repo:
            parts = full_repo.split("/", 1)
            owner = owner or parts[0]
            repo = parts[1]
    if not pr_number:
        pr_number = os.environ.get("GITHUB_PR_NUMBER")

    if not all([owner, repo, pr_number]):
        logger.warning(
            "Missing PR context. owner=%s repo=%s pr_number=%s",
            owner,
            repo,
            pr_number,
        )
        return None

    return (owner, repo, pr_number, cfg.detect_ci_provider())


def _build_comment_url(
    owner: str, repo: str, pr_number: str, provider: str, cfg: EnvConfig
) -> tuple[str, str]:
    if provider == "forgejo":
        base_url = cfg.FORGEJO_API_URL or os.environ.get(
            "GITEA_BASE_URL", "https://codeberg.org"
        )
        url = f"{base_url.rstrip('/')}/api/v1/repos/{owner}/{repo}/issues/{pr_number}/comments"
        token = cfg.get_ci_token()
        return url, token or ""

    url = f"{cfg.GITHUB_API_URL}/repos/{owner}/{repo}/issues/{pr_number}/comments"
    token = cfg.get_ci_token()
    return url, token or ""


def post_pr_comment(cfg: EnvConfig, body: str) -> bool:
    context = _get_pr_context(cfg)
    if context is None:
        logger.error("Cannot determine PR context — check environment variables")
        return False

    owner, repo, pr_number, provider = context
    url, token = _build_comment_url(owner, repo, pr_number, provider, cfg)

    if not token:
        logger.error(
            "No CI token found for provider '%s'. "
            "Set GITHUB_TOKEN or GITEA_TOKEN environment variable.",
            provider,
        )
        return False

    logger.info(
        "Posting PR comment to %s/%s PR #%s via %s",
        owner,
        repo,
        pr_number,
        provider,
    )
    logger.debug("Comment URL: %s", url)

    try:
        resp = requests.post(
            url,
            json={"body": body},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "ci-triage-agent/0.1.0",
            },
            timeout=30,
        )
        resp.raise_for_status()
        logger.info("PR comment posted (status %d)", resp.status_code)
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(
            "Failed to post PR comment: %s — %s",
            e,
            e.response.text if e.response is not None else "",
        )
        return False
    except requests.exceptions.ConnectionError as e:
        logger.error("Connection error posting PR comment: %s", e)
        return False
    except requests.exceptions.Timeout:
        logger.error("Timeout posting PR comment")
        return False
    except Exception as e:
        logger.error("Unexpected error posting PR comment: %s", e)
        return False
