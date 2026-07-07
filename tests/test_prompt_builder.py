from ci_triage_agent.prompt_builder import build_prompt, SYSTEM_INSTRUCTION


def test_prompt_contains_system_instruction():
    prompt = build_prompt("some log content")
    assert SYSTEM_INSTRUCTION in prompt


def test_prompt_contains_log_context():
    log = "Traceback (most recent call last):\n  File \"test.py\", line 5, in <module>\n    foo()\nNameError: name 'foo' is not defined"
    prompt = build_prompt(log)
    assert log in prompt


def test_prompt_wraps_log_in_code_block():
    prompt = build_prompt("error line 1\nerror line 2")
    assert "```\nerror line 1\nerror line 2\n```" in prompt or "```\nerror line 1\nerror line 2" in prompt


def test_truncates_very_long_logs():
    long_log = "x\n" * 100_000
    prompt = build_prompt(long_log)
    assert len(prompt) < 100_000
    assert "TRUNCATED DUE TO TOKEN LIMIT" in prompt


def test_short_log_not_truncated():
    short_log = "short error\n"
    prompt = build_prompt(short_log)
    assert short_log in prompt
    assert "TRUNCATED" not in prompt


def test_prompt_starts_with_system_instruction():
    prompt = build_prompt("error")
    assert prompt.startswith("You are an AI-driven")
