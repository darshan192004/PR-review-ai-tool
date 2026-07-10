import os


class AppSettings:
    """Application settings loaded from environment variables."""

    LLM_API_KEY: str | None = None
    LLM_PROVIDER: str = "gemini"
    CI_PROVIDER: str | None = None

    GITHUB_TOKEN: str | None = None
    GITEA_TOKEN: str | None = None

    REPO_OWNER: str | None = None
    REPO_NAME: str | None = None
    PR_NUMBER: str | None = None
    COMMIT_SHA: str | None = None

    GITHUB_API_URL: str = "https://api.github.com"
    FORGEJO_API_URL: str | None = None

    GEMINI_API_URL: str = "https://generativelanguage.googleapis.com/v1beta/models"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OPENAI_API_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_URL: str = "https://api.anthropic.com/v1"
    ANTHROPIC_MODEL: str = "claude-3-5-haiku-20241022"

    LOG_LINES: int = 200
    LLM_TIMEOUT: int = 60
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_DELAY: float = 2.0

    LOG_LEVEL: str = "INFO"

    @classmethod
    def load(cls) -> "AppSettings":
        """Load settings from environment variables, applying defaults for optional fields."""
        cfg = cls()
        cfg.LLM_API_KEY = os.environ.get("LLM_API_KEY")
        cfg.LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()
        cfg.CI_PROVIDER = os.environ.get("CI_PROVIDER")

        cfg.GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get(
            "GH_TOKEN"
        )
        cfg.GITEA_TOKEN = os.environ.get("GITEA_TOKEN")
        cfg.REPO_OWNER = os.environ.get("REPO_OWNER")
        cfg.REPO_NAME = os.environ.get("REPO_NAME")
        cfg.PR_NUMBER = os.environ.get("PR_NUMBER")
        cfg.COMMIT_SHA = os.environ.get("COMMIT_SHA")
        cfg.GITHUB_API_URL = os.environ.get(
            "GITHUB_API_URL", "https://api.github.com"
        )
        cfg.FORGEJO_API_URL = os.environ.get("FORGEJO_API_URL")

        log_lines_str = os.environ.get("LOG_LINES", "200")
        try:
            cfg.LOG_LINES = int(log_lines_str)
        except ValueError:
            cfg.LOG_LINES = 200

        timeout_str = os.environ.get("LLM_TIMEOUT", "60")
        try:
            cfg.LLM_TIMEOUT = int(timeout_str)
        except ValueError:
            cfg.LLM_TIMEOUT = 60

        retries_str = os.environ.get("LLM_MAX_RETRIES", "3")
        try:
            cfg.LLM_MAX_RETRIES = int(retries_str)
        except ValueError:
            cfg.LLM_MAX_RETRIES = 3

        cfg.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

        return cfg

    def detect_ci_provider(self) -> str:
        """Detect the CI platform from environment variables or explicit config."""
        if self.CI_PROVIDER:
            return self.CI_PROVIDER.lower()
        if os.environ.get("GITHUB_ACTIONS") == "true":
            return "github"
        if os.environ.get("GITEA_ACTIONS") == "true":
            return "forgejo"
        return "unknown"

    def get_ci_token(self) -> str | None:
        """Return the CI platform token matching the detected provider."""
        provider = self.detect_ci_provider()
        if provider == "github":
            return self.GITHUB_TOKEN
        if provider == "forgejo":
            return self.GITEA_TOKEN
        return None
