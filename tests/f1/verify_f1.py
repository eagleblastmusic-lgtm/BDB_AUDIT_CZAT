"""Deterministic F1 pre-history qualification and post-commit replay.

F0's original verifier is HEAD-specific. The descendant regression verifies
every exact F0 subject against its frozen record, then runs the unchanged F0
commands. It never rewrites the F0 artifact or relaxes a predecessor byte pin.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from dual_support import run_dual

START = "5d2093076f7ef27ea68c69289ae6a5cf2f60b7ef"
MAIN = "446f11ce1622a49f5100cefead29a04d952d487e"
RECORD = "F1_QUALIFICATION/F1_MILESTONE_ACCEPTANCE.json"
F0_PATH = "LEGACY_COMPATIBILITY_CORPUS/F0_MILESTONE_ACCEPTANCE.json"
F0_HASH = "ea8e17ae3a23bb2101afb2db19be2e0e99f238ecea51cc9de794e57a3b14b35c"
INPUTS = {
    "ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md": "df7e40fc062f5fcc2309276cc6fd4b529c060fb4f5f24fe39484eb66c0153dfa",
    "BDB_AUDIT_V2_IMPLEMENTATION_ROADMAP.md": "b127e249b8db0bd2f17c5e6f77ed3d2d342fc8fb187e3ec720de0b7bd1fac018",
    "BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN.md": "abf92ea199d57c78eb25dc0ca41ed9267a9d20d79401b3c468c01c4e4371b598",
    "BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md": "658f8866ca1a1330db9be582b13b47e87381de2208c53ee64ed9e47a8d3e15ee",
    "BDB_AUDIT_V1_TO_V2_MIGRATION_AND_COMPATIBILITY.md": "d31fd0d84a4e5c14aced3eae3a67bc704ed5d75d9ca6a8a1ed6943100352358f",
    "BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json": "7bee0013d179adc8eba14d07c2c3ea159de0b8e37be9a9f6dcd55969550b7772",
    "BDB_AUDIT_V2_AUTHOR_BASELINE_QUALIFICATION_R5_3.json": "de7c79c3a7ec3f3879d702993e60f882f01f66ecbc00c67e8084de84dc5f99a0",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def f0_identity():
    raw = (ROOT/F0_PATH).read_bytes()
    require(sha(raw) == F0_HASH, "F0 artifact identity")
    record = json.loads(raw)
    require(record["acceptance_id"] == "BDB-F0-M0-M1-R5_3-001" and record["verdict"] == "PASS", "F0 record")
    for path, entry in record["subject_git_objects"].items():
        require(git("rev-parse", f"{START}:{path}") == entry["git_blob_sha1"], "F0 Git pin: " + path)
        require(git("hash-object", "--", path) == entry["git_blob_sha1"], "F0 working bytes: " + path)
    for path, digest in record["subject_raw_sha256"].items():
        require(sha((ROOT/path).read_bytes()) == digest, "F0 raw pin: " + path)
    source = ROOT/"legacy/v1_4_4/BDB_AUDIT_ASSISTANT_PA_v5.2_WRAPPERS_5.4-RC1_v1.4.4_ARCHIVE.py"
    require(source.stat().st_size == 1030677, "M0 size")
    require(git("rev-parse", "main") == MAIN, "main changed")
    return source


def subjects():
    result = {}
    for entry in git("ls-files", "--stage", "-z").split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        mode, blob, stage = meta.split()
        require(stage == "0", "Unmerged index")
        if path.startswith(("src/", "tests/f1/", "F1_QUALIFICATION/")) and path != RECORD:
            require(git("hash-object", "--", path) == blob, "Unstaged F1 input: " + path)
            result[path] = {"mode": mode, "git_blob_sha1": blob, "raw_sha256": sha((ROOT/path).read_bytes())}
    require(bool(result), "F1 subjects not staged")
    return result


def checks(source):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTEST_ADDOPTS="-p no:cacheprovider")
    commands = [
        [sys.executable, "-B", "-m", "pytest", "tests/f1", "-q", "-p", "no:cacheprovider", "--tb=short"],
        [sys.executable, "-B", "tests/compatibility/verify_m1.py"],
        [sys.executable, "-B", "-m", "pytest", "tests/compatibility/test_legacy_baseline.py", "-q", "-p", "no:cacheprovider"],
        [sys.executable, "-B", str(source), "--self-test"],
    ]
    results = []
    for argv in commands:
        run = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True)
        print(run.stdout, end="", flush=True)
        if run.stderr:
            print(run.stderr, file=sys.stderr, end="")
        require(run.returncode == 0, "Check failed: " + repr(argv))
        counts = re.findall(r"(\d+) passed", run.stdout)
        results.append({"argv": argv, "exit_code": run.returncode, "passed_counts": [int(n) for n in counts]})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    require(git("branch", "--show-current") == "bdb-v2", "Wrong branch")
    require(git("remote", "get-url", "origin") == "https://github.com/eagleblastmusic-lgtm/bdb-audit.git", "Wrong repository")
    head = git("rev-parse", "HEAD")
    require(head == START if args.record else git("rev-parse", "HEAD^") == START, "F1 ancestry")
    source = f0_identity()
    for name, digest in INPUTS.items():
        require(sha((ROOT/"F1_QUALIFICATION/inputs"/name).read_bytes()) == digest, "R5.3 source: " + name)
    subject = subjects()
    if not args.record:
        require(not git("diff", "--name-only") and not git("diff", "--cached", "--name-only"), "Tracked changes remain")
    commands = checks(source)
    dual = run_dual()
    require(len(dual) == 25, "Incomplete dual corpus")
    safe = [r for r in dual if r["expected"] == "ACCEPT"]
    unsafe = [r for r in dual if r["expected"] == "REJECT"]
    require(len(safe) == 8 and len(unsafe) == 17, "Corpus counts")
    require(all(r["preservation"] and r["correctness"] for r in dual), "Dual gate failed")
    require(sum(r["bug_misclassified_safe"] for r in dual) == 0, "Known legacy bug")
    gates = {
        "LEGACY_BEHAVIOR_PRESERVATION_GATE": "PASS", "VALIDATOR_CORRECTNESS_GATE": "PASS",
        "UNEXPLAINED_REQUIRED_PRESERVATION_DIFFS": sum(r["unexplained_diff"] for r in dual),
        "KNOWN_SAFE_EXPECTATIONS_SATISFIED": "100%", "KNOWN_UNSAFE_EXPECTATIONS_REJECTED": "100%",
        "KNOWN_LEGACY_BUGS_MISCLASSIFIED_AS_SAFE": 0, "UNRESOLVED_EXPECTATION_CONFLICTS": 0,
    }
    record = {
        "schema": "BDB_F1_MILESTONE_ACCEPTANCE_PRE_HISTORY_V1",
        "acceptance_id": "BDB-F1-M2-M3-R5_3-001", "milestone": "F1", "verdict": "PASS",
        "qualified_parent_commit": START, "repository": "eagleblastmusic-lgtm/bdb-audit", "branch": "bdb-v2",
        "identity_binding": "Exact parent, staged subject blobs/raw hashes excluding this record; containing commit binds record without circular hash.",
        "f0_acceptance_raw_sha256": F0_HASH, "subject_inputs": subject,
        "baseline_qualification_raw_sha256": INPUTS["BDB_AUDIT_V2_AUTHOR_BASELINE_QUALIFICATION_R5_3.json"],
        "normative_candidate_set_digest": "78de98f8163d2f0bf0ab94781b86bd8e5e0345411a4432669d91fdfc42671d56",
        "commands": commands, "dual_results": dual, "gates": gates, "f0_regression": "PASS",
        "work_packages": {"PR003_M2_CORE": "PASS", "PR004_M2_ZIP_ARTIFACT_HASHES": "PASS", "PR005_M3_LEGACY_ASSURANCE": "PASS", "PR006_M3_DUAL_DIFFERENTIAL": "PASS"},
        "python": platform.python_version(), "platform": platform.platform(),
        "assurance_scope": "Author-qualified synthetic F1; no independent freeze, runtime authority or release qualification.",
        "spec_conflicts": [], "f2_started": False,
    }
    f0_identity()
    require(subjects() == subject, "Inputs changed during qualification")
    raw = (json.dumps(record, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode()
    if args.record:
        (ROOT/RECORD).write_bytes(raw)
    else:
        require((ROOT/RECORD).read_bytes() == raw, "Deterministic F1 qualification mismatch")
        require(subprocess.check_output(["git", "show", "HEAD:"+RECORD], cwd=ROOT) == raw, "Record differs from commit")
    print(json.dumps(gates, indent=2))
    print("F1_MILESTONE_ACCEPTANCE_SHA256 = " + sha(raw))
    print("VERIFIED_HEAD = " + head)
    print("F1 = PASS" + (" (pre-commit candidate)" if args.record else ""))


if __name__ == "__main__":
    main()
