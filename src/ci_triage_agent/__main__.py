import sys
from .cli import parse_args, run


def main() -> None:
    args = parse_args()
    exit_code = run(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
