"""M4 import/CLI boundary. No implicit campaign creation."""
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="bdb_audit", description="BDB Audit v2 foundation reference implementation"
    )
    parser.parse_args(argv)
    parser.print_help()


if __name__ == "__main__":
    main()
