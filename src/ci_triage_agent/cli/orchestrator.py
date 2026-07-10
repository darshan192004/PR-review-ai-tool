import argparse
import logging

from ..config.settings import AppSettings
from ..pipeline.log_context import extract_log_context
from ..pipeline.diagnosis_prompt import build_prompt
from ..llm.client import LLMClient
from ..pipeline.diagnosis_parser import parse_response
from ..ci.platform import post_diagnosis


def run(args: argparse.Namespace) -> int:
    """Execute the full triage pipeline: extract → prompt → LLM → parse → post."""
    cfg = AppSettings.load()

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
