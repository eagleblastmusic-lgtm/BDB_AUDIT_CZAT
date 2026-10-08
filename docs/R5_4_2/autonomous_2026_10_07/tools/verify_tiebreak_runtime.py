"""Exact runtime evidence with the existing Windows-safe temp fixture."""

import subprocess
import sys
import time

from execution import OUT, ROOT, digest, write


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    plugin = ROOT / "._nf02_current_audit/audit_tmp.py"
    code = (
        "import sys; sys.path.insert(0, '._nf02_current_audit'); "
        "import audit_tmp, pytest; "
        "raise SystemExit(pytest.main(['tests/f2','tests/f3','tests/f7','tests/workflow',"
        "'-q','--tb=short'], plugins=[audit_tmp]))"
    )
    command = [sys.executable, "-c", code]
    start = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    write("implementation_tiebreak/RUNTIME_VERIFICATION.json", {
        "argv": command, "exit_code": result.returncode,
        "duration_seconds": round(time.monotonic() - start, 3),
        "stdout": result.stdout, "stderr": result.stderr,
        "implementation_inputs": {name: digest(ROOT / name) for name in (
            "src/bdb_audit/history/closure.py", "src/bdb_audit/history/objects.py",
            "src/bdb_audit/history/store.py", "tests/f2/test_closure_tiebreak_regression.py")},
        "temp_fixture_raw_digest": digest(plugin), "qualification": False, "NF02": "OPEN"})
    print(result.stdout, flush=True)
    print(result.stderr, flush=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
