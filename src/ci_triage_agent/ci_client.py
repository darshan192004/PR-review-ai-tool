import logging
import os

import requests

from .config import EnvConfig

logger = logging.getLogger(__name__)


def _get_repo_context(
    cfg: EnvConfig,
) -> dict | None:
    owner = cfg.REPO_OWNER
    repo = cfg.REPO_NAME
    pr_number = cfg.PR_NUMBER
    commit_sha = cfg.COMMIT_SHA

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
    if not commit_sha:
        commit_sha = os.environ.get("GITHUB_SHA") or os.environ.get("GITEA_SHA")

    if not all([owner, repo]):
        logger.warning(
            "Missing repo context. owner=%s repo=%s", owner, repo,
        )
        return None

    return {
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "commit_sha": commit_sha,
        "provider": cfg.detect_ci_provider(),
    }


def _get_pr_context(
    cfg: EnvConfig,
) -> tuple[str, str, str, str] | None:
    context = _get_repo_context(cfg)
    if context is None or not context["pr_number"]:
        return None
    return (context["owner"], context["repo"], context["pr_number"], context["provider"])


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


def _build_headers(cfg: EnvConfig, token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "ci-triage-agent/0.1.0",
    }


def _post_comment(url: str, token: str, body: str, cfg: EnvConfig) -> bool:
    if not token:
        logger.error("No CI token available")
        return False

    try:
        resp = requests.post(
            url,
            json={"body": body},
            headers=_build_headers(cfg, token),
            timeout=30,
        )
        resp.raise_for_status()
        logger.info("Comment posted (status %d)", resp.status_code)
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(
            "Failed to post comment: %s — %s",
            e,
            e.response.text if e.response is not None else "",
        )
        return False
    except requests.exceptions.ConnectionError as e:
        logger.error("Connection error posting comment: %s", e)
        return False
    except requests.exceptions.Timeout:
        logger.error("Timeout posting comment")
        return False
    except Exception as e:
        logger.error("Unexpected error posting comment: %s", e)
        return False


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

    return _post_comment(url, token, body, cfg)


def detect_pr_from_commit(
    cfg: EnvConfig, owner: str, repo: str, commit_sha: str
) -> str | None:
    if not commit_sha:
        logger.warning("No commit SHA provided for PR detection")
        return None

    token = cfg.get_ci_token()
    if not token:
        logger.warning("No CI token available for PR detection")
        return None

    url = f"{cfg.GITHUB_API_URL}/repos/{owner}/{repo}/commits/{commit_sha}/pulls"
    logger.info("Checking for open PRs at %s", url)

    try:
        resp = requests.get(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "ci-triage-agent/0.1.0",
            },
            timeout=30,
        )
        resp.raise_for_status()
        pulls = resp.json()
        if isinstance(pulls, list) and len(pulls) > 0:
            pr_number = str(pulls[0]["number"])
            logger.info("Detected PR #%s for commit %s", pr_number, commit_sha[:7])
            return pr_number

        logger.info("No open PR found for commit %s", commit_sha[:7])
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(
            "PR detection HTTP error: %s — %s",
            e,
            e.response.text if e.response is not None else "",
        )
        return None
    except requests.exceptions.RequestException as e:
        logger.error("PR detection request failed: %s", e)
        return None
    except (KeyError, TypeError, ValueError) as e:
        logger.error("PR detection parse error: %s", e)
        return None


def post_commit_comment(
    cfg: EnvConfig, owner: str, repo: str, commit_sha: str, body: str
) -> bool:
    if not commit_sha:
        logger.error("Cannot post commit comment — no commit SHA")
        return False

    token = cfg.get_ci_token()
    if not token:
        logger.error("No CI token available for commit comment")
        return False

    url = f"{cfg.GITHUB_API_URL}/repos/{owner}/{repo}/commits/{commit_sha}/comments"
    logger.info(
        "Posting commit comment to %s/%s@%s", owner, repo, commit_sha[:7]
    )
    logger.debug("Commit comment URL: %s", url)

    return _post_comment(url, token, body, cfg)


def post_diagnosis(cfg: EnvConfig, body: str) -> bool:
    context = _get_repo_context(cfg)
    if context is None:
        logger.error("Cannot determine repo context — check environment variables")
        return False

    owner = context["owner"]
    repo = context["repo"]
    pr_number = context["pr_number"]
    commit_sha = context["commit_sha"]
    provider = context["provider"]

    if provider == "forgejo":
        if not pr_number:
            logger.error("Forgejo requires a PR number — cannot route to commit comments")
            return False
        url, token = _build_comment_url(owner, repo, pr_number, provider, cfg)
        return _post_comment(url, token, body, cfg)

    if pr_number:
        url, token = _build_comment_url(owner, repo, pr_number, provider, cfg)
        return _post_comment(url, token, body, cfg)

    if commit_sha:
        detected_pr = detect_pr_from_commit(cfg, owner, repo, commit_sha)
        if detected_pr:
            url, token = _build_comment_url(owner, repo, detected_pr, provider, cfg)
            return _post_comment(url, token, body, cfg)
        return post_commit_comment(cfg, owner, repo, commit_sha, body)

    logger.error(
        "No PR number or commit SHA available — cannot route diagnosis"
    )
    return False
