import json
import logging
import time
from typing import Any

import requests

from ..config.settings import AppSettings

logger = logging.getLogger(__name__)


class LLMClient:
    """Provider-agnostic client for LLM inference with retry logic."""

    def __init__(self, config: AppSettings) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "ci-triage-agent/0.1.0"})

    def analyze(self, prompt: str) -> str | None:
        """Send a prompt to the configured LLM provider with automatic retries on transient failures."""
        provider = self.config.LLM_PROVIDER
        logger.info("Calling LLM provider: %s", provider)

        for attempt in range(1, self.config.LLM_MAX_RETRIES + 1):
            try:
                if provider == "gemini":
                    return self._call_gemini(prompt)
                elif provider == "openai":
                    return self._call_openai(prompt)
                elif provider == "anthropic":
                    return self._call_anthropic(prompt)
                else:
                    logger.error("Unknown LLM provider: %s", provider)
                    return None
            except requests.exceptions.Timeout:
                logger.warning(
                    "LLM request timed out (attempt %d/%d)",
                    attempt,
                    self.config.LLM_MAX_RETRIES,
                )
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status in (429, 502, 503, 504) and attempt < self.config.LLM_MAX_RETRIES:
                    delay = self.config.LLM_RETRY_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "LLM returned %d, retrying in %.1fs (attempt %d/%d)",
                        status,
                        delay,
                        attempt,
                        self.config.LLM_MAX_RETRIES,
                    )
                    time.sleep(delay)
                    continue
                logger.error("LLM HTTP error: %s", e)
                return None
            except requests.exceptions.ConnectionError as e:
                logger.error("LLM connection error: %s", e)
                return None
            except Exception as e:
                logger.error("Unexpected LLM error: %s", e)
                return None

        logger.error("LLM request failed after %d attempts", self.config.LLM_MAX_RETRIES)
        return None

    def _call_gemini(self, prompt: str) -> str:
        api_key = self.config.LLM_API_KEY
        model = self.config.GEMINI_MODEL
        url = f"{self.config.GEMINI_API_URL}/{model}:generateContent?key={api_key}"

        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "topP": 0.95,
                "maxOutputTokens": 4096,
            },
        }

        resp = self._session.post(
            url,
            json=payload,
            timeout=self.config.LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            logger.warning("Gemini returned no candidates: %s", data)
            return None

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            logger.warning("Gemini response has no parts: %s", data)
            return None

        text = parts[0].get("text", "")
        if not text:
            logger.warning("Gemini response text is empty")
            return None

        return text

    def _call_openai(self, prompt: str) -> str:
        api_key = self.config.LLM_API_KEY
        model = self.config.OPENAI_MODEL
        url = f"{self.config.OPENAI_API_URL}/chat/completions"

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        resp = self._session.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=self.config.LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            logger.warning("OpenAI returned no choices: %s", data)
            return None

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            logger.warning("OpenAI response content is empty")
            return None

        return content

    def _call_anthropic(self, prompt: str) -> str:
        api_key = self.config.LLM_API_KEY
        model = self.config.ANTHROPIC_MODEL
        url = f"{self.config.ANTHROPIC_API_URL}/messages"

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }

        resp = self._session.post(
            url,
            json=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=self.config.LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        content_list = data.get("content", [])
        text_parts = [
            block.get("text", "")
            for block in content_list
            if block.get("type") == "text"
        ]
        result = "\n".join(text_parts)
        if not result:
            logger.warning("Anthropic response text is empty")
            return None

        return result
