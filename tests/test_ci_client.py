import os

import responses
import pytest

from ci_triage_agent.config import EnvConfig
from ci_triage_agent.ci_client import post_pr_comment


def _make_config(**overrides) -> EnvConfig:
    cfg = EnvConfig.load()
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
