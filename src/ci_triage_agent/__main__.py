import sys
from .cli.parser import parse_args
from .cli.orchestrator import run


def main() -> None:
    args = parse_args()
    exit_code = run(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
