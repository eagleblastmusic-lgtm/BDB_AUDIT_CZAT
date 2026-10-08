"""Retry only the host-ACL failure with an ordinary local temp directory."""

import contextlib
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

from execution import OUT, ROOT, digest, write


def main():
    sys.path.insert(0, str(ROOT / "._nf02_current_audit"))
    import audit_tmp
    import pytest

    @contextlib.contextmanager
    def safe_temp(*args, **kwargs):
        path = ROOT / "._nf02_current_audit/data" / ("resolver-" + uuid.uuid4().hex)
        path.mkdir(parents=True)
        try:
            yield str(path)
        finally:
            shutil.rmtree(path)

    original = tempfile.TemporaryDirectory
    tempfile.TemporaryDirectory = safe_temp
    target = "tests/workflow/test_review_blockers.py::test_github_resolver_never_uses_cwd_fallback"
    start = time.monotonic()
    try:
        result = pytest.main([target, "-q", "--tb=short"], plugins=[audit_tmp])
    finally:
        tempfile.TemporaryDirectory = original
    write("implementation_tiebreak/RESOLVER_ENVIRONMENT_RETRY.json", {
        "target": target, "exit_code": int(result), "duration_seconds": time.monotonic() - start,
        "environment_change": "Ordinary repo-local temp directory; no resolver/network/result mock or production change",
        "tool_raw_digest": digest(Path(__file__)), "test_raw_digest": digest(ROOT / target.split("::")[0]),
        "original_broad_result": "560 passed; one host TemporaryDirectory ACL failure",
        "qualification": False, "NF02": "OPEN"})
    raise SystemExit(result)


if __name__ == "__main__":
    main()
