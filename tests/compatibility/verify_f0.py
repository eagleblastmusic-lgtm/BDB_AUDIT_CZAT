"""Pre-history F0 acceptance; --record before commit, read-only replay after it.

The record binds the complete candidate Git object map except itself, plus raw
hashes of F0 payloads. The containing commit binds the record without a circular
commit/hash reference. No v2 history or runtime authority is implemented here.
"""
import argparse
import json
import os
import platform
import subprocess
import sys

from corpus_support import CORPUS, ROOT, SOURCE, SOURCE_SHA, sha

BASE = "4f14ab55cdc22f2137d9cea6f7f1d25fc2be9d33"
M0 = "46ae26e2b91a2fd7a6e2bf2a164b90231f6a95d5"
LEGACY = "446f11ce1622a49f5100cefead29a04d952d487e"
RECORD = "LEGACY_COMPATIBILITY_CORPUS/F0_MILESTONE_ACCEPTANCE.json"
TEST_FILES = [f"tests/compatibility/{name}.py" for name in (
    "build_corpus", "corpus_support", "test_compatibility_corpus", "verify_m1", "verify_f0")]
DOC_FILES = [f"LEGACY_COMPATIBILITY_CORPUS/{name}" for name in (
    "README.md", "EXPECTATION_BASIS.md", "EXPECTATION_INPUTS.json", "manifest.json", "M1_QUALIFICATION.json")]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").rstrip("\r\n")


def object_map(ref=None):
    result = {}
    command = ("ls-tree", "-rz", ref) if ref else ("ls-files", "--stage", "-z")
    for entry in git(*command).split("\0"):
        if not entry:
            continue
        metadata, path = entry.split("\t", 1)
        if ref:
            mode, kind, blob = metadata.split()
            assert kind == "blob"
        else:
            mode, blob, stage = metadata.split()
            assert stage == "0", "Unmerged index"
        if path != RECORD:
            result[path] = {"mode": mode, "git_blob_sha1": blob}
    return dict(sorted(result.items()))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true", help="Qualify the staged candidate before the F0 commit")
    args = parser.parse_args()
    head = git("rev-parse", "HEAD")
    require(git("remote", "get-url", "origin").rstrip("/") ==
            "https://github.com/eagleblastmusic-lgtm/bdb-audit.git", "Wrong repository")
    require(git("branch", "--show-current") == "bdb-v2", "Wrong branch")
    require(git("rev-parse", "main") == LEGACY, "Frozen main changed")
    require(git("rev-parse", BASE + "^") == M0, "M0 portability ancestry changed")
    require(git("diff-tree", "--no-commit-id", "--name-only", "-r", BASE) == ".gitattributes",
            "Unexpected M0 portability commit scope")
    if args.record:
        require(head == BASE, "Record only at the qualified pre-F0 HEAD")
        objects = object_map()
    else:
        require(git("show", "-s", "--format=%P", head) == BASE, "Wrong F0 parent")
        objects = object_map(head)
        require(object_map() == objects, "Index differs from qualified commit")
        require(git("diff", "--name-only") == "", "Tracked working tree differs")
        # Include the acceptance artifact itself in the clean-index check.
        require(git("diff", "--cached", "--name-only") == "", "Staged changes remain")
        require((ROOT / RECORD).read_bytes() == subprocess.check_output(
            ["git", "show", f"HEAD:{RECORD}"], cwd=ROOT), "Acceptance record differs from HEAD")

    baseline = json.loads((ROOT / "legacy/v1_4_4/LEGACY_BASELINE_MANIFEST.json").read_bytes())
    source = SOURCE.read_bytes()
    require(len(source) == baseline["source"]["size_bytes"] == 1030677, "Legacy size mismatch")
    require(sha(source) == baseline["source"]["sha256"] == SOURCE_SHA, "Legacy RawDigest mismatch")
    require(git("hash-object", "--no-filters", str(SOURCE)) == baseline["source"]["git_blob_sha1"] ==
            "37adeefe3bf91bb00f9ffa2d5c3d92aebce33bc2", "Legacy blob mismatch")
    require(baseline["source"]["git_commit_sha1"] == baseline["exact_legacy_pin"]["value"] == LEGACY,
            "Legacy pin mismatch")
    require(git("rev-parse", LEGACY + "^{tree}") == baseline["source"]["git_tree_sha1"] ==
            "35e83b7424795381240bd1520f412f6111c28c24", "Legacy tree mismatch")
    retained_output = ROOT / baseline["self_test"]["retained_output_path"]
    require(sha(retained_output.read_bytes()) == baseline["self_test"]["retained_output_sha256"] ==
            "301358956c7bb34727c5458acf37e27f0ba044eb6d46992b5b256bfaaf101a44", "Retained self-test mismatch")
    mutated = bytearray(source)
    mutated[0] ^= 1
    require(sha(bytes(mutated)) != SOURCE_SHA and SOURCE.read_bytes() == source, "Copy mutation detection failed")

    manifest = json.loads((CORPUS / "manifest.json").read_bytes())
    raw_paths = ["LEGACY_COMPATIBILITY_CORPUS/" + r["path"] for r in manifest["fixtures"]]
    scope = {".gitattributes", *TEST_FILES, *DOC_FILES, *raw_paths}
    original = object_map(BASE)
    require(set(objects) == set(original) | scope, "Candidate contains missing or out-of-scope files")
    require(all(objects[p] == entry for p, entry in original.items() if p != ".gitattributes"),
            "Existing source/M0 objects changed")
    # Verify working-tree bytes map to the candidate's Git objects, including
    # text files with checkout EOL handling outside the exact-byte payloads.
    for path, entry in objects.items():
        require(git("hash-object", "--", path) == entry["git_blob_sha1"], f"Unstaged input: {path}")
    raw_subjects = sorted(scope | {p for p in original if p.startswith("legacy/v1_4_4/")})
    hashes = {p: sha((ROOT / p).read_bytes()) for p in raw_subjects}
    for path in [*raw_paths, *(p for p in original if p.startswith("legacy/v1_4_4/"))]:
        require(git("check-attr", "text", "--", path).endswith(": text: unset"), f"EOL conversion enabled: {path}")

    prior = json.loads((ROOT / RECORD).read_bytes()) if not args.record else None
    if prior:
        require(prior["subject_git_objects"] == objects and prior["subject_raw_sha256"] == hashes,
                "F0 qualification subject changed")
        require(prior["qualified_parent_commit"] == BASE and prior["milestone"] == "F0" and
                prior["verdict"] == "PASS" and not prior["m2_started"], "Invalid acceptance record")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTEST_ADDOPTS="-p no:cacheprovider")
    commands = []
    for argv in ([sys.executable, "-B", "tests/compatibility/verify_m1.py"],
                 [sys.executable, "-m", "pytest", "tests/compatibility/test_legacy_baseline.py", "-q"],
                 [sys.executable, "-B", str(SOURCE), "--self-test"]):
        result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True)
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        require(result.returncode == 0, f"F0 check failed: {argv}")
        commands.append({"argv": argv, "exit_code": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
    runtime = json.loads(commands[-1]["stdout"])
    require(runtime["status"] == "PASS" and runtime["errors"] == [], "Legacy self-test failed")
    require(hashes == {p: sha((ROOT / p).read_bytes()) for p in raw_subjects}, "Inputs changed during verification")
    m1 = json.loads((CORPUS / "M1_QUALIFICATION.json").read_bytes())
    if args.record:
        record = {
            "schema": "BDB_F0_MILESTONE_ACCEPTANCE_PRE_HISTORY_V1",
            "acceptance_id": "BDB-F0-M0-M1-R5_3-001", "milestone": "F0", "verdict": "PASS",
            "repository": "eagleblastmusic-lgtm/bdb-audit", "branch": "bdb-v2",
            "qualified_parent_commit": BASE, "m0_checkpoint": M0, "legacy_pin": LEGACY,
            "identity_binding": "Parent commit plus complete subject Git objects excluding this record; containing F0 commit binds the record itself.",
            "subject_git_objects": objects, "subject_raw_sha256": hashes,
            "m0_gate": baseline["m0_gate"], "m0_portability": "PASS", "copy_mutation_detected": True,
            "m1_gate": m1["gates"], "fixture_counts": {"valid": 8, "invalid": 17, "extra": 0},
            "unresolved_spec_conflicts": [], "m2_started": False,
            "assurance_scope": "Author-qualified synthetic F0 corpus; no independent foundation freeze, real audit or release qualification",
            "environment": {"python": platform.python_version(), "platform": platform.platform()},
            "commands": commands,
        }
        (ROOT / RECORD).write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode())
    print("F0_ARTIFACT_SHA256 = " + sha((ROOT / RECORD).read_bytes()))
    print("VERIFIED_HEAD = " + head)
    print("F0 = PASS" + (" (pre-commit candidate)" if args.record else ""))


if __name__ == "__main__":
    main()
