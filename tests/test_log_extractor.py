import tempfile
from pathlib import Path

from ci_triage_agent.pipeline.log_context import extract_log_context


def test_reads_from_file():
    content = "line1\nline2\nline3\n"
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write(content)
        f.flush()
        path = f.name

    try:
        result = extract_log_context(path, num_lines=10)
        assert result == content
    finally:
        Path(path).unlink()


def test_reads_tail_only():
    lines = "\n".join(f"line{i}" for i in range(100)) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write(lines)
        f.flush()
        path = f.name

    try:
        result = extract_log_context(path, num_lines=3)
        assert "line97" in result
        assert "line99" in result
        assert "line0" not in result
        assert "TRUNCATED" in result
    finally:
        Path(path).unlink()


def test_returns_empty_for_missing_file():
    result = extract_log_context("/nonexistent/path.log", num_lines=200)
    assert result == ""


def test_returns_empty_when_stdin_is_tty(monkeypatch):
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    result = extract_log_context(None, num_lines=200)
    assert result == ""


def test_handles_empty_file():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write("")
        f.flush()
        path = f.name

    try:
        result = extract_log_context(path, num_lines=200)
        assert result == ""
    finally:
        Path(path).unlink()


def test_truncation_header_shows_counts():
    lines = "\n".join(f"line{i}" for i in range(50)) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write(lines)
        f.flush()
        path = f.name

    try:
        result = extract_log_context(path, num_lines=10)
        assert "TRUNCATED" in result
        assert "10 of 50" in result
    finally:
        Path(path).unlink()


def test_binary_content_does_not_crash():
    binary_data = b"\x00\x01\x02\xff\xfe\xfdline\n"
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".log") as f:
        f.write(binary_data)
        f.flush()
        path = f.name

    try:
        result = extract_log_context(path, num_lines=200)
        assert isinstance(result, str)
    finally:
        Path(path).unlink()


def test_num_lines_larger_than_file_returns_all():
    lines = "a\nb\nc\n"
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        f.write(lines)
        f.flush()
        path = f.name

    try:
        result = extract_log_context(path, num_lines=1000)
        assert result == lines
        assert "TRUNCATED" not in result
    finally:
        Path(path).unlink()
