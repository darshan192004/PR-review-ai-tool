import logging

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are an AI-driven CI failure diagnostic agent. Your role is to analyze a build or test failure log and produce a precise, actionable diagnosis.

## Rules
1. Identify the **root cause** of the failure (e.g., syntax error, missing import, undefined variable, test assertion failure, missing env variable).
2. Identify the **affected file** and exact **line number** if visible in the log.
3. Provide a **copy-pasteable code patch** (in diff format) that would fix the issue.
4. If the root cause is unclear, state "Unable to determine root cause" and provide your best hypothesis.

## Output Format
You MUST respond with ONLY the following Markdown structure — no preamble, no explanation, no conversation:

## Root Cause
<one or two sentences describing the exact failure cause>

## Affected File
<file path and line number, or "Unknown">

## Code Patch
```diff
<unified diff format patch — only the lines that need to change>
```

## Suggested Fix Description
<brief explanation of what the patch does and why it resolves the failure>

If you cannot determine the root cause, use:
## Root Cause
Unable to determine root cause

## Affected File
Unknown

## Code Patch
Unable to generate

## Suggested Fix Description
No suggested fix available
"""


def build_prompt(log_context: str) -> str:
    max_log_chars = 80_000

    if len(log_context) > max_log_chars:
        logger.warning(
            "Log context too large (%d chars), truncating to %d chars",
            len(log_context),
            max_log_chars,
        )
        log_context = log_context[:max_log_chars]
        last_newline = log_context.rfind("\n")
        if last_newline != -1:
            log_context = log_context[: last_newline + 1]
        log_context += "\n[--- LOG TRUNCATED DUE TO TOKEN LIMIT ---]\n"

    prompt = f"""{SYSTEM_INSTRUCTION}

## CI Build/Test Failure Log
```
{log_context}
```
"""

    return prompt
