class Diagnosis:
    """Structured diagnosis result parsed from an LLM response."""

    def __init__(
        self,
        root_cause: str | None = None,
        affected_file: str | None = None,
        code_patch: str | None = None,
        fix_description: str | None = None,
        raw: str | None = None,
    ) -> None:
        self.root_cause = root_cause
        self.affected_file = affected_file
        self.code_patch = code_patch
        self.fix_description = fix_description
        self.raw = raw

    def format_markdown(self) -> str:
        """Render the diagnosis as a formatted Markdown comment suitable for PR posting."""
        parts: list[str] = []

        if self.root_cause:
            parts.append(f"## 🤖 AI Triage: Root Cause\n\n{self.root_cause.strip()}")

        if self.affected_file:
            parts.append(f"\n\n**Affected File:** `{self.affected_file.strip()}`")

        if self.code_patch:
            code = self.code_patch.strip()
            if code.startswith("```"):
                parts.append(f"\n\n## Code Patch\n\n{code}")
            else:
                parts.append(f"\n\n## Code Patch\n\n```diff\n{code}\n```")

        if self.fix_description:
            parts.append(f"\n\n## Suggested Fix Description\n\n{self.fix_description.strip()}")

        if not parts:
            parts.append(
                "## 🤖 AI Triage\n\nUnable to parse failure analysis from LLM response."
            )

        return "".join(parts)
