"""Real subprocess demonstration on a non-sensitive Git target; no fake AI result."""
from __future__ import annotations

import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standalone", type=Path)
    args = parser.parse_args()
    scratch = ROOT / ".product-smoke" / uuid.uuid4().hex
    repo = scratch / "target"
    repo.mkdir(parents=True)
    (repo / "calculator.py").write_text("def add(a, b):\n    return a + b\n\ndef clamp(value, low, high):\n    return min(low, max(high, value))\n", encoding="utf-8")
    (repo / "test_calculator.py").write_text("import unittest\nfrom calculator import add, clamp\n\nclass CalculatorTest(unittest.TestCase):\n    def test_sum(self):\n        self.assertEqual(add(2, 3), 5)\n    def test_clamp_midpoint(self):\n        self.assertEqual(clamp(5, 0, 10), 5)\n", encoding="utf-8")
    for git_args in (["init"], ["add", "."], ["-c", "user.name=Product demo", "-c", "user.email=product@example.invalid", "commit", "-m", "non-sensitive audit target with known clamp defect"]):
        subprocess.run(["git", "-C", str(repo), *git_args], check=True, capture_output=True)
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1"}
    records = []
    def cli(argv, expected=0):
        command = ([sys.executable, "-I", str(args.standalone.resolve())] if args.standalone
                   else [sys.executable, "-m", "bdb_audit"])
        proc = subprocess.run([*command, *argv], env=env, capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == expected, (argv, proc.stdout, proc.stderr)
        payload = json.loads(proc.stderr if expected else proc.stdout)
        records.append({"argv": argv, "exit_code": proc.returncode, "result": payload})
        return payload
    store = scratch / "work/campaign.sqlite"
    created = cli(["product", "start", "--repo", str(repo), "--ref", sha, "--store", str(store), "--json"])
    assert created["source"]["exact_commit_sha"] == sha and len(created["packages"]) == 5
    # Clean target equals committed files; exact Git raw bytes are independently verified.
    for name in ("calculator.py", "test_calculator.py"):
        raw = subprocess.check_output(["git", "-C", str(repo), "show", f"{sha}:{name}"])
        assert (repo / name).read_bytes() == raw
    passed = scratch / "checks-pass"
    failed = scratch / "checks-detected-defect"
    for run_id, evidence, test in (("sum-control", passed, "test_calculator.CalculatorTest.test_sum"), ("clamp-defect", failed, "test_calculator.CalculatorTest.test_clamp_midpoint")):
        result = cli(["tools", "run", "--source", str(repo), "--evidence", str(evidence), "--run-id", run_id, "--json", "--", sys.executable, "-m", "unittest", test])
        assert result["supervisor_status"] == ("SUCCESS" if run_id == "sum-control" else "TARGET_NONZERO")
        cli(["tools", "results", "--evidence", str(evidence), "--json"])
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in store.parent.rglob("*") if path.is_file()}
    cli(["product", "import", "--store", str(store), "--zip", str(scratch / "unauthorized.zip"), "--json"], expected=2)
    resumed = cli(["product", "resume", "--store", str(store), "--json"])
    assert resumed["campaign_id"] == created["campaign_id"]
    after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in store.parent.rglob("*") if path.is_file()}
    assert before == after
    report = ROOT / "docs/PRODUCT_V1/DEMO_AUDIT_REPORT.md"
    # Each run uses its own export; retain an existing earlier demonstration.
    export = scratch / "AUDIT_REPORT.md"
    cli(["product", "report", "--store", str(store), "--output", str(export), "--run-evidence", str(passed), "--run-evidence", str(failed), "--json"])
    report.write_bytes(export.read_bytes())
    evidence = {"kind": "REAL_LOCAL_SUBPROCESS_SMOKE", "synthetic_external_results": False,
                "distribution": "standalone -I" if args.standalone else "source",
                "target_type": "created non-sensitive Git repository with explicit known defect",
                "target_commit": sha, "campaign_id": created["campaign_id"], "store": str(store),
                "rejection_and_restart_no_mutation": True, "external_audit": "BLOCKED_NF02_OPEN",
                "local_checks": "one actual passing control and one actual detected clamp defect",
                "records": records}
    (ROOT / "docs/PRODUCT_V1/SMOKE_EVIDENCE.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PRODUCT_SMOKE_PASS", "campaign_id": created["campaign_id"], "target_commit": sha, "report": str(report), "external_audit": "NOT_COMPLETED"}))


if __name__ == "__main__":
    main()
