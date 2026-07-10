import argparse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Build and parse the CLI argument parser for the triage agent."""
    parser = argparse.ArgumentParser(
        prog="ci-triage-agent",
        description="AI-Driven CI Failure & Bug Triage Agent",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to log file (reads stdin if not provided)",
    )
    parser.add_argument(
        "--lines",
        type=int,
        default=None,
        help="Number of trailing log lines to analyze (default: 200)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        choices=["gemini", "openai", "anthropic"],
        help="LLM provider override",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Print prompt only — skip LLM call and PR comment",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_mode",
        default=None,
        help="Run full pipeline (extract → LLM → parse) and print diagnosis to stdout — skip PR comment",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    return parser.parse_args(argv)
