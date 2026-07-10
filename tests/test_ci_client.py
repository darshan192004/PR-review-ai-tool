import os

import responses
import pytest

from ci_triage_agent.config.settings import AppSettings
from ci_triage_agent.ci.platform import (
    post_pr_comment,
    detect_pr_from_commit,
    post_commit_comment,
    post_diagnosis,
)


def _make_config(**overrides) -> AppSettings:
    cfg = AppSettings.load()
    cfg.CI_PROVIDER = "github"
    cfg.GITHUB_TOKEN = "gh-test-token"
    cfg.REPO_OWNER = "test-owner"
    cfg.REPO_NAME = "test-repo"
    cfg.PR_NUMBER = "42"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


@responses.activate
def test_posts_github_comment_success():
    cfg = _make_config()
    responses.post(
        f"{cfg.GITHUB_API_URL}/repos/test-owner/test-repo/issues/42/comments",
        json={"id": 123},
        status=201,
    )

    result = post_pr_comment(cfg, "## Root Cause\nTest error")
    assert result is True
    assert len(responses.calls) == 1


@responses.activate
def test_posts_forgejo_comment_success():
    cfg = _make_config(
        CI_PROVIDER="forgejo",
        GITEA_TOKEN="forgejo-test-token",
        GITHUB_TOKEN=None,
        FORGEJO_API_URL="https://git.example.com",
    )
    responses.post(
        "https://git.example.com/api/v1/repos/test-owner/test-repo/issues/42/comments",
        json={"id": 456},
        status=201,
    )

    result = post_pr_comment(cfg, "## Root Cause\nTest error")
    assert result is True
    assert len(responses.calls) == 1


@responses.activate
def test_missing_pr_context_returns_false():
    cfg = _make_config(REPO_OWNER=None, REPO_NAME=None, PR_NUMBER=None)
    result = post_pr_comment(cfg, "comment")
    assert result is False


@responses.activate
def test_missing_token_returns_false():
    cfg = _make_config(GITHUB_TOKEN=None)
    result = post_pr_comment(cfg, "comment")
    assert result is False


@responses.activate
def test_http_error_returns_false():
    cfg = _make_config()
    responses.post(
        f"{cfg.GITHUB_API_URL}/repos/test-owner/test-repo/issues/42/comments",
        status=403,
        body='{"message": "Forbidden"}',
    )

    result = post_pr_comment(cfg, "comment")
    assert result is False


@responses.activate
def test_forgejo_falls_back_to_env_vars(monkeypatch):
    monkeypatch.setenv("GITEA_REPOSITORY", "org/forgejo-repo")
    monkeypatch.setenv("GITEA_REPOSITORY_OWNER", "org")

    cfg = _make_config(
        CI_PROVIDER="forgejo",
        GITEA_TOKEN="ftoken",
        REPO_OWNER=None,
        REPO_NAME=None,
        PR_NUMBER="7",
        FORGEJO_API_URL="https://git.example.com",
    )
    responses.post(
        "https://git.example.com/api/v1/repos/org/forgejo-repo/issues/7/comments",
        json={"id": 789},
        status=201,
    )

    result = post_pr_comment(cfg, "comment")
    assert result is True


@responses.activate
def test_detect_pr_from_commit_found():
    cfg = _make_config()
    responses.get(
        f"{cfg.GITHUB_API_URL}/repos/test-owner/test-repo/commits/abc123def456/pulls",
        json=[{"number": 42, "title": "Fix bug", "state": "open"}],
        status=200,
    )

    result = detect_pr_from_commit(cfg, "test-owner", "test-repo", "abc123def456")
    assert result == "42"
    assert len(responses.calls) == 1


@responses.activate
def test_detect_pr_from_commit_not_found():
    cfg = _make_config()
    responses.get(
        f"{cfg.GITHUB_API_URL}/repos/test-owner/test-repo/commits/abc123def456/pulls",
        json=[],
        status=200,
    )

    result = detect_pr_from_commit(cfg, "test-owner", "test-repo", "abc123def456")
    assert result is None


@responses.activate
def test_detect_pr_from_commit_no_sha():
    cfg = _make_config()
    result = detect_pr_from_commit(cfg, "test-owner", "test-repo", "")
    assert result is None
    assert len(responses.calls) == 0


@responses.activate
def test_detect_pr_from_commit_no_token():
    cfg = _make_config(GITHUB_TOKEN=None)
    result = detect_pr_from_commit(cfg, "test-owner", "test-repo", "abc123")
    assert result is None
    assert len(responses.calls) == 0


@responses.activate
def test_post_commit_comment_success():
    cfg = _make_config()
    responses.post(
        f"{cfg.GITHUB_API_URL}/repos/test-owner/test-repo/commits/abc123def456/comments",
        json={"id": 789},
        status=201,
    )

    result = post_commit_comment(
        cfg, "test-owner", "test-repo", "abc123def456", "## Root Cause\nTest"
    )
    assert result is True
    assert len(responses.calls) == 1


@responses.activate
def test_post_commit_comment_no_sha():
    cfg = _make_config()
    result = post_commit_comment(cfg, "test-owner", "test-repo", "", "body")
    assert result is False


@responses.activate
def test_post_diagnosis_routes_to_pr():
    cfg = _make_config(PR_NUMBER="42", COMMIT_SHA="abc123")
    responses.post(
        f"{cfg.GITHUB_API_URL}/repos/test-owner/test-repo/issues/42/comments",
        json={"id": 1},
        status=201,
    )

    result = post_diagnosis(cfg, "## Root Cause\nTest")
    assert result is True
    assert len(responses.calls) == 1


@responses.activate
def test_post_diagnosis_routes_to_commit_when_no_pr():
    cfg = _make_config(PR_NUMBER=None, COMMIT_SHA="abc123def456")
    responses.get(
        f"{cfg.GITHUB_API_URL}/repos/test-owner/test-repo/commits/abc123def456/pulls",
        json=[],
        status=200,
    )
    responses.post(
        f"{cfg.GITHUB_API_URL}/repos/test-owner/test-repo/commits/abc123def456/comments",
        json={"id": 2},
        status=201,
    )

    result = post_diagnosis(cfg, "## Root Cause\nTest")
    assert result is True
    assert len(responses.calls) == 2


@responses.activate
def test_post_diagnosis_detects_pr_via_api():
    cfg = _make_config(PR_NUMBER=None, COMMIT_SHA="abc123def456")
    responses.get(
        f"{cfg.GITHUB_API_URL}/repos/test-owner/test-repo/commits/abc123def456/pulls",
        json=[{"number": 99, "title": "Hotfix", "state": "open"}],
        status=200,
    )
    responses.post(
        f"{cfg.GITHUB_API_URL}/repos/test-owner/test-repo/issues/99/comments",
        json={"id": 3},
        status=201,
    )

    result = post_diagnosis(cfg, "## Root Cause\nTest")
    assert result is True
    assert len(responses.calls) == 2


@responses.activate
def test_post_diagnosis_no_pr_no_sha():
    cfg = _make_config(PR_NUMBER=None, COMMIT_SHA=None)
    result = post_diagnosis(cfg, "## Root Cause\nTest")
    assert result is False


@responses.activate
def test_post_diagnosis_no_context():
    cfg = _make_config(REPO_OWNER=None, REPO_NAME=None, PR_NUMBER=None)
    result = post_diagnosis(cfg, "body")
    assert result is False
