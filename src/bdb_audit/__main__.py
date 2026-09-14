"""CLI entry point for bdb_audit module."""
import sys
from .astra_cli import run_cli


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    return run_cli(argv)


if __name__ == "__main__":
    sys.exit(main())
