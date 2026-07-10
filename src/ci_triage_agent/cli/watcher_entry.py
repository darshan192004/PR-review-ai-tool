import argparse
import logging

from ..config.settings import AppSettings
from ..monitoring.docker_watcher import DockerWatcher


def parse_watcher_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Build and parse CLI arguments for the Docker watcher daemon."""
    parser = argparse.ArgumentParser(
        prog="ci-triage-watcher",
        description="Docker event watcher for CI Triage Agent",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompt without calling LLM or posting comments",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point: load settings, configure logging, and start the DockerWatcher daemon."""
    args = parse_watcher_args()
    cfg = AppSettings.load()

    if args.log_level:
        cfg.LOG_LEVEL = args.log_level

    logging.basicConfig(
        level=getattr(logging, cfg.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    watcher = DockerWatcher(config=cfg, dry_run=args.dry_run)
    try:
        watcher.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
