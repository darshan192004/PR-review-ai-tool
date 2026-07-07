import logging
import re

logger = logging.getLogger(__name__)


class ParsedResponse:
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


def _extract_section(text: str, heading: str) -> str | None:
    pattern = rf"##\s*{re.escape(heading)}\s*\n(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def parse_response(raw: str) -> ParsedResponse:
    if not raw:
        return ParsedResponse(raw=raw)

    root_cause = _extract_section(raw, "Root Cause")
    affected_file = _extract_section(raw, "Affected File")
    code_patch = _extract_section(raw, "Code Patch")
    fix_description = _extract_section(raw, "Suggested Fix Description")

    if code_patch:
        code_patch = code_patch.strip()
        if code_patch.startswith("```"):
            first_newline = code_patch.find("\n")
            if first_newline != -1:
                code_patch = code_patch[first_newline + 1 :]
            if code_patch.endswith("```"):
                code_patch = code_patch[:-3].strip()

    if root_cause and "Unable to determine root cause" in root_cause:
        logger.info("LLM indicated it cannot determine root cause")

    return ParsedResponse(
        root_cause=root_cause,
        affected_file=affected_file,
        code_patch=code_patch,
        fix_description=fix_description,
        raw=raw,
    )
