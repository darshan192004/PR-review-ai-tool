from pathlib import Path

from ci_triage_agent.response_parser import parse_response, ParsedResponse

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parses_valid_response():
    raw = _load("sample_llm_response.md")
    parsed = parse_response(raw)

    assert parsed.root_cause is not None
    assert "calculate_total" in parsed.root_cause
    assert parsed.affected_file is not None
    assert "src/app.py" in parsed.affected_file
    assert parsed.code_patch is not None
    assert "quantity" in parsed.code_patch
    assert parsed.fix_description is not None
    assert parsed.raw == raw


def test_parses_unable_to_determine():
    raw = _load("sample_llm_response_unable.md")
    parsed = parse_response(raw)

    assert parsed.root_cause is not None
    assert "Unable to determine" in parsed.root_cause
    assert parsed.affected_file == "Unknown"
    assert parsed.code_patch == "Unable to generate"
    assert parsed.fix_description == "No suggested fix available"


def test_returns_empty_for_empty_input():
    parsed = parse_response("")
    assert parsed.root_cause is None
    assert parsed.affected_file is None
    assert parsed.code_patch is None


def test_returns_empty_for_none():
    parsed = parse_response("")
    assert parsed.root_cause is None


def test_format_markdown_includes_all_sections():
    parsed = ParsedResponse(
        root_cause="Division by zero",
        affected_file="src/calc.py:42",
        code_patch="- x / 0\n+ x / 1",
        fix_description="Avoid division by zero",
    )
    md = parsed.format_markdown()
    assert "Division by zero" in md
    assert "src/calc.py:42" in md
    assert "x / 0" in md
    assert "x / 1" in md


def test_format_markdown_fallback_when_missing():
    parsed = ParsedResponse()
    md = parsed.format_markdown()
    assert "Unable to parse" in md


def test_parses_partial_response():
    raw = "## Root Cause\nMissing semicolon\n## Affected File\nsrc/index.js:10\n"
    parsed = parse_response(raw)
    assert parsed.root_cause == "Missing semicolon"
    assert parsed.affected_file == "src/index.js:10"
    assert parsed.code_patch is None


def test_strips_code_fence_from_patch():
    raw = "## Root Cause\nSyntax error\n## Affected File\ntest.py:5\n## Code Patch\n```diff\n-print(\"hello\"\n+print(\"hello\")\n```\n"
    parsed = parse_response(raw)
    assert parsed.code_patch is not None
    assert "```" not in parsed.code_patch
    assert parsed.code_patch == '-print("hello"\n+print("hello")'
