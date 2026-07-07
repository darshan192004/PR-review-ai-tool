import logging
import sys

logger = logging.getLogger(__name__)


def extract_log_context(
    log_file: str | None = None,
    num_lines: int = 200,
) -> str:
    if log_file:
        try:
            with open(log_file, "r", errors="replace") as f:
                lines = f.readlines()
        except FileNotFoundError:
            logger.error("Log file not found: %s", log_file)
            return ""
        except PermissionError:
            logger.error("Permission denied reading log file: %s", log_file)
            return ""
    else:
        lines = sys.stdin.readlines() if not sys.stdin.isatty() else []

    if not lines:
        logger.warning("No input received (stdin was empty or a TTY)")
        return ""

    tail = lines[-num_lines:] if num_lines < len(lines) else lines
    total = len(lines)
    extracted = len(tail)

    context = "".join(tail)

    if extracted < total:
        header = (
            f"[--- TRUNCATED: showing last {extracted} of {total} lines ---]\n"
        )
        context = header + context

    return context
