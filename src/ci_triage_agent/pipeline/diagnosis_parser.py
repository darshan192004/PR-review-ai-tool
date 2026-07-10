import logging
import re

from ..models.diagnosis import Diagnosis

logger = logging.getLogger(__name__)


def _extract_section(text: str, heading: str) -> str | None:
    pattern = rf"##\s*{re.escape(heading)}\s*\n(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def parse_response(raw: str) -> Diagnosis:
    """Parse an LLM Markdown response into a structured Diagnosis object by extracting each section."""
    if not raw:
        return Diagnosis(raw=raw)

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

    return Diagnosis(
        root_cause=root_cause,
        affected_file=affected_file,
        code_patch=code_patch,
        fix_description=fix_description,
        raw=raw,
    )
