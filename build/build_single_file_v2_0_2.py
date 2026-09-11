#!/usr/bin/env python3
"""Build wrapper for the BDB Audit v2.0.2 standalone patch release."""
from __future__ import annotations

import build_single_file as base


base.DEFAULT_OUTPUT_NAME = "BDB_AUDIT_ASSISTANT_v2.0.2.py"
base.APP_VERSION = "2.0.2"
base.BUILD_ID = "BDB-V2-STANDALONE-2.0.2"
base.STANDALONE_STUB_TEMPLATE = base.STANDALONE_STUB_TEMPLATE.replace("v2.0.1", "v2.0.2")


def main() -> int:
    out_path, sha, size = base.build_standalone()
    print(f"BUILD_SUCCESS: {out_path} ({size} bytes, SHA256: {sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
