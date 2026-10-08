"""Build current local code, preserving earlier build evidence."""

import subprocess
import sys
import time

from execution import OUT, ROOT, digest, write


def main():
    sys.path.insert(0, str(ROOT))
    from build.build_single_file import build_standalone

    folder = "implementation_source_format/build_runs/" + str(time.time_ns())
    path, raw, size = build_standalone(OUT / folder / "BDB_AUDIT_SOURCE_FORMAT.py")
    results = []
    for option in ("--self-test", "--help"):
        command = [sys.executable, str(path), option]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        results.append({"argv": command, "exit_code": run.returncode, "stdout": run.stdout, "stderr": run.stderr})
    result_name = folder + "/BUILD_RESULT.json"
    write(result_name, {
        "path": path.relative_to(OUT).as_posix(), "raw_digest": raw, "bytes": size,
        "implementation_inputs": {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted((ROOT / "src").rglob("*.py"))},
        "builder_raw_digest": digest(ROOT / "build/build_single_file.py"), "commands": results,
        "qualification": False, "installation_activation": "NOT_PERFORMED", "NF02": "OPEN"})
    write("implementation_source_format/CURRENT_BUILD.json", {"file": result_name, "raw_digest": digest(OUT / result_name),
          "role": "Diagnostic local build locator, never installation or acceptance authority", "qualification": False})
    assert all(r["exit_code"] == 0 for r in results)
    print("PASS current build, self-test and help; qualification remains open")


if __name__ == "__main__":
    main()
