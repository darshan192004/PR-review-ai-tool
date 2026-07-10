import responses

from ci_triage_agent.config.settings import AppSettings
from ci_triage_agent.llm.client import LLMClient


def _make_config(**overrides) -> AppSettings:
    cfg = AppSettings.load()
    cfg.LLM_API_KEY = "test-key"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


@responses.activate
def test_gemini_success():
    cfg = _make_config(LLM_PROVIDER="gemini")
    responses.post(
        f"{cfg.GEMINI_API_URL}/{cfg.GEMINI_MODEL}:generateContent?key=test-key",
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "## Root Cause\nTest error"}]
                    }
                }
            ]
        },
        status=200,
    )

    client = LLMClient(cfg)
    result = client.analyze("test prompt")

    assert result is not None
    assert "Root Cause" in result


@responses.activate
def test_gemini_no_candidates():
    cfg = _make_config(LLM_PROVIDER="gemini")
    responses.post(
        f"{cfg.GEMINI_API_URL}/{cfg.GEMINI_MODEL}:generateContent?key=test-key",
        json={"candidates": []},
        status=200,
    )

    client = LLMClient(cfg)
    result = client.analyze("test prompt")
    assert result is None


@responses.activate
def test_openai_success():
    cfg = _make_config(LLM_PROVIDER="openai")
    responses.post(
        f"{cfg.OPENAI_API_URL}/chat/completions",
        json={
            "choices": [
                {"message": {"content": "## Root Cause\nOpenAI error"}}
            ]
        },
        status=200,
    )

    client = LLMClient(cfg)
    result = client.analyze("test prompt")

    assert result is not None
    assert "Root Cause" in result


@responses.activate
def test_anthropic_success():
    cfg = _make_config(LLM_PROVIDER="anthropic")
    responses.post(
        f"{cfg.ANTHROPIC_API_URL}/messages",
        json={
            "content": [{"type": "text", "text": "## Root Cause\nClaude error"}]
        },
        status=200,
    )

    client = LLMClient(cfg)
    result = client.analyze("test prompt")

    assert result is not None
    assert "Root Cause" in result


@responses.activate
def test_retry_on_http_429():
    cfg = _make_config(LLM_PROVIDER="gemini", LLM_MAX_RETRIES=2, LLM_RETRY_DELAY=0.01)
    url = f"{cfg.GEMINI_API_URL}/{cfg.GEMINI_MODEL}:generateContent?key=test-key"

    responses.add(responses.POST, url, status=429)
    responses.add(
        responses.POST,
        url,
        json={
            "candidates": [
                {"content": {"parts": [{"text": "## Root Cause\nAfter retry"}]}}
            ]
        },
        status=200,
    )

    client = LLMClient(cfg)
    result = client.analyze("test prompt")

    assert result is not None
    assert len(responses.calls) == 2


@responses.activate
def test_unknown_provider():
    cfg = _make_config(LLM_PROVIDER="unknown")
    client = LLMClient(cfg)
    result = client.analyze("test prompt")
    assert result is None


@responses.activate
def test_timeout_returns_none():
    cfg = _make_config(LLM_PROVIDER="gemini", LLM_MAX_RETRIES=1)
    url = f"{cfg.GEMINI_API_URL}/{cfg.GEMINI_MODEL}:generateContent?key=test-key"

    responses.add(responses.POST, url, body=Exception("timeout"))

    client = LLMClient(cfg)
    result = client.analyze("test prompt")
    assert result is None
