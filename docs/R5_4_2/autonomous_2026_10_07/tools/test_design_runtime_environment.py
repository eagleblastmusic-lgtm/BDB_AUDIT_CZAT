"""Verification cannot silently discard its mandatory assertion checks."""

import os
import subprocess
import sys

from execution import OUT, ROOT, digest, write


def main():
    code = "import execution"
    clean_env = {key: value for key, value in os.environ.items() if key != "PYTHONOPTIMIZE"}
    controls = []
    for name, flags, environment, valid in (
        ("ASSERTIONS_ENABLED", [], clean_env, True),
        ("OPTIMIZED_PYTHON", ["-O"], clean_env, False),
        ("DOUBLE_OPTIMIZED_PYTHON", ["-OO"], clean_env, False),
        ("ENVIRONMENT_OPTIMIZATION", [], {**clean_env, "PYTHONOPTIMIZE": "1"}, False),
    ):
        command = [sys.executable, *flags, "-c", code]
        result = subprocess.run(command, cwd=OUT / "tools", env=environment,
                                capture_output=True, encoding="utf-8", timeout=30)
        if valid:
            assert result.returncode == 0, result.stderr
        else:
            assert result.returncode != 0 and "DESIGN_VERIFICATION_ASSERTIONS_DISABLED" in result.stderr
        controls.append({"case": name, "argv": command, "exit_code": result.returncode,
                         "expected_accept": valid, "result": "PASS"})
    write("design/VERIFICATION_RUNTIME_ENVIRONMENT_CONTROLS.json", {
        "controls": controls, "execution_tool_raw_digest": digest(OUT / "tools/execution.py"),
        "repository": str(ROOT), "qualification": False,
        "scope": "Design harness assertion execution only; not runtime authority or qualification"})
    print("PASS 4 verification assertion-environment controls")


if __name__ == "__main__":
    main()
