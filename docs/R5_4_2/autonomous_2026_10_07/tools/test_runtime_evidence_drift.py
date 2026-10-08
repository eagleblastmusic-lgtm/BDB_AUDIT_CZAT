"""Adversarial verifier checks in isolated copies; no qualification authority."""
import json
import shutil
import subprocess
import sys
import uuid

from execution import OUT, ROOT, digest, write


RUNNER = '''
import importlib.util, json, pathlib, sys
sys.path.insert(0, sys.argv[3])
root = pathlib.Path(sys.argv[1])
case = sys.argv[2]
tool = root / "runtime_verifier.py"
spec = importlib.util.spec_from_file_location("runtime_verifier", tool)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ROOT = root
module.git = lambda *args: "isolated-test-head"
records = {}
def isolated_write(name, value):
    records[name] = value
    path = root / "docs/R5_4_2/autonomous_2026_10_07" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
module.write = isolated_write
import pytest
def fake_pytest(*args, **kwargs):
    targets = {
        "SOURCE_BYTES": root / "src/bdb_audit/source/git_resolver.py",
        "TEST_HELPER": root / "tests/helper.py",
        "CONFIG": root / "pyproject.toml",
        "HARNESS": tool,
        "ADDED": root / "src/new_input.py",
    }
    if case in targets:
        with targets[case].open("ab") as stream:
            stream.write(b"\\n# controlled drift\\n")
    elif case == "DELETED":
        (root / "tests/helper.py").unlink()
    return 0
pytest.main = fake_pytest
sys.argv = [str(tool), "tests/test_selected.py"]
try:
    module.main()
except AssertionError as exc:
    outcome = "REJECTED"
    reason = str(exc)
except SystemExit as exc:
    assert exc.code == 0
    outcome, reason = "ACCEPTED", "unchanged diagnostic inputs"
record = next(value for name, value in records.items() if "runtime_runs/" in name)
print(json.dumps({"case": case, "outcome": outcome, "reason": reason,
                  "tool_drift": record["tool_drift"], "input_drift": record["input_drift"],
                  "inventory_drift": record["input_inventory_drift"]}))
'''


def main():
    root = ROOT / "._nf02_current_audit/data" / ("evidence-drift-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    controls = []
    for case in ("UNCHANGED", "SOURCE_BYTES", "TEST_HELPER", "CONFIG", "HARNESS", "ADDED", "DELETED"):
        workspace = root / case
        workspace.mkdir()
        shutil.copytree(ROOT / "src", workspace / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (workspace / "tests").mkdir()
        for name in ("test_selected.py", "helper.py"):
            (workspace / "tests" / name).write_bytes(b"# isolated verifier fixture\n")
        (workspace / "build").mkdir()
        (workspace / "._nf02_current_audit").mkdir()
        (workspace / "._nf02_current_audit/audit_tmp.py").write_bytes(b"# isolated plugin fixture\n")
        (workspace / "requirements-f2.lock").write_bytes(b"# isolated lock fixture\n")
        (workspace / "pyproject.toml").write_bytes(b"# isolated config fixture\n")
        shutil.copyfile(OUT / "tools/source_runtime_verification.py", workspace / "runtime_verifier.py")
        (workspace / "runner.py").write_text(RUNNER, encoding="utf-8")
        run = subprocess.run([sys.executable, str(workspace / "runner.py"), str(workspace), case, str(OUT / "tools")],
                             capture_output=True, text=True, encoding="utf-8")
        assert run.returncode == 0, (case, run.stdout, run.stderr)
        observed = json.loads(run.stdout)
        assert observed["outcome"] == ("ACCEPTED" if case == "UNCHANGED" else "REJECTED"), observed
        controls.append({**observed, "result": "PASS"})
    write("design/source_instance_readback/diagnostics/" + root.name + ".json", {
        "retained_isolated_workspaces": str(root), "qualification": False})
    write("design/RUNTIME_EVIDENCE_DRIFT_CONTROLS.json", {
        "controls": controls, "harness_raw_digest": digest(OUT / "tools/source_runtime_verification.py"),
        "qualification": False,
        "scope": "Verifier mutation detection only; pytest execution is deliberately stubbed in isolated copies"})
    print("7 runtime evidence drift controls PASS")


if __name__ == "__main__":
    main()
