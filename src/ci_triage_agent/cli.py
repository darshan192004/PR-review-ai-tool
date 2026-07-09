import argparse
import logging
import sys

from .config import EnvConfig
from .log_extractor import extract_log_context
from .prompt_builder import build_prompt
from .llm_client import LLMClient
from .response_parser import parse_response
from .ci_client import post_diagnosis


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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


def run(args: argparse.Namespace) -> int:
    cfg = EnvConfig.load()

    is_dry_run = bool(args.dry_run)
    is_print_mode = bool(args.print_mode)

    if args.lines is not None:
        cfg.LOG_LINES = args.lines
    if args.provider is not None:
        cfg.LLM_PROVIDER = args.provider
    if args.log_level is not None:
        cfg.LOG_LEVEL = args.log_level

    logging.basicConfig(
        level=getattr(logging, cfg.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger(__name__)

    ci_provider = cfg.detect_ci_provider()
    logger.info("CI provider detected: %s", ci_provider)
    logger.info("LLM provider: %s", cfg.LLM_PROVIDER)

    log_context = extract_log_context(args.log_file, cfg.LOG_LINES)
    if not log_context:
        logger.warning("No log content extracted — nothing to analyze")
        return 1

    logger.info("Extracted %d bytes of log context", len(log_context))

    prompt = build_prompt(log_context)
    logger.debug("Prompt built (%d chars)", len(prompt))

    if is_dry_run:
        print("=== PROMPT ===")
        print(prompt)
        print("=== END PROMPT ===")
        return 0

    if not cfg.LLM_API_KEY:
        logger.error("LLM_API_KEY is not set")
        return 1

    client = LLMClient(cfg)
    raw_response = client.analyze(prompt)
    if raw_response is None:
        logger.error("LLM returned no response")
        return 1

    logger.info("LLM response received (%d chars)", len(raw_response))

    parsed = parse_response(raw_response)
    if parsed.root_cause is None and parsed.code_patch is None:
        logger.warning("Could not parse structured response from LLM")
        if is_print_mode:
            print("=== RAW LLM RESPONSE ===")
            print(raw_response)
            print("=== END RAW ===")
        return 1

    comment_body = parsed.format_markdown()
    logger.info(
        "Parsed: root_cause=%s, file=%s, patch=%s",
        "yes" if parsed.root_cause else "no",
        parsed.affected_file or "unknown",
        "yes" if parsed.code_patch else "no",
    )

    if is_print_mode:
        print(comment_body)
        return 0

    success = post_diagnosis(cfg, comment_body)
    if success:
        logger.info("Diagnosis posted successfully")
        return 0
    else:
        logger.error("Failed to post diagnosis")
        return 1
