"""Verify old generated build copies and write an explicit removal manifest.

Does not delete files or mutate refs/index. Only PRODUCT_V1 reports are written.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import subprocess

SNAPSHOT = "f23dbedccb6dca9d23f41830e282e814e550bca1"
ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/PRODUCT_V1"
CATEGORY = "docs/R5_4_2/autonomous_2026_10_07/build_time_candidate/"


def main():
    scan = json.loads((REPORT / "CLEANUP_REFERENCE_SCAN.json").read_text(encoding="utf-8"))
    groups = scan["groups"]
    tree = subprocess.check_output(["git", "-C", str(ROOT), "ls-tree", "-rlz", SNAPSHOT])
    pattern = re.compile(b"|".join(key.encode() for key in groups))
    refs = {key: set() for key in groups}
    for rec in tree.split(b"\0"):
        if not rec:
            continue
        meta, raw_path = rec.split(b"\t", 1)
        name = raw_path.decode()
        if any(segment in name for segment in ("/checkpoint_history/", "/build_time_candidate/", "/normative_build_candidate/", "/golden_build_candidate/", "/build_schema_fixtures/")):
            continue
        if Path(name).suffix not in {".py", ".md", ".json", ".toml", ".yml", ".yaml", ".txt"}:
            continue
        with (ROOT / name).open("rb") as handle:
            tail = b""
            while chunk := handle.read(1024 * 1024):
                data = tail + chunk
                for match in pattern.finditer(data):
                    refs[match.group().decode()].add(name)
                tail = data[-63:]
    for key, row in groups.items():
        row["refs"] = sorted(refs[key])
    scan["scan"] = "ALL tracked text/json/python/config, streaming without size limit, excluding only generated candidate/checkpoint copies; active code/build/test included."
    (REPORT / "CLEANUP_REFERENCE_SCAN.json").write_text(json.dumps(scan, indent=2) + "\n", encoding="utf-8")
    safe_groups = {digest for digest, row in groups.items()
                   if row["refs"] == ["docs/R5_4_2/REVIEW_SNAPSHOT_MANIFEST.json"]}
    rows = []
    for rec in tree.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, kind, sha, size = meta.split()
        name = path.decode("utf-8")
        if kind == b"blob" and name.startswith(CATEGORY) and name[len(CATEGORY):].split("/")[0] in safe_groups:
            rows.append((name, sha.decode("ascii"), int(size)))
    checked = {}
    process = subprocess.Popen(["git", "-C", str(ROOT), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for name, sha, size in rows:
            if sha not in checked:
                process.stdin.write((sha + "\n").encode("ascii"))
                process.stdin.flush()
                header = process.stdout.readline().decode().strip().split()
                assert header == [sha, "blob", str(size)], header
                raw = process.stdout.read(size)
                assert process.stdout.read(1) == b"\n"
                assert hashlib.sha1(b"blob " + str(size).encode() + b"\0" + raw).hexdigest() == sha
                checked[sha] = hashlib.sha256(raw).hexdigest()
            raw = (ROOT / name).read_bytes()
            assert len(raw) == size and hashlib.sha256(raw).hexdigest() == checked[sha], name
    finally:
        process.stdin.close()
        process.wait()
    entries = [{"path": name, "git_blob_sha": sha, "bytes": size,
                "worktree_bytes": size, "sha256": checked[sha], "archive_commit": SNAPSHOT,
                "classification": "SAFE_TO_REMOVE", "archived_in_commit": SNAPSHOT,
                "reason": "Obsolete generated build copy; no active runtime/test/build or current readback dependency. Original snapshot manifest remains bound to pinned archive commit.",
                "restore_command": f"git -c core.longpaths=true restore --source={SNAPSHOT} --worktree -- '{name}'"}
               for name, sha, size in sorted(rows)]
    count = len(entries)
    total = sum(row["bytes"] for row in entries)
    manifest = {"archive_commit": SNAPSHOT, "archived_in_commit": {"docs/R5_4_2/REVIEW_SNAPSHOT_MANIFEST.json": SNAPSHOT},
                "original_manifest_immutable": True, "verification": "ALL Git blobs read back; Git SHA1 and SHA256 verified; ALL current worktree bytes equal Git raw bytes. No CRLF delta.",
                "source_preservation_policy": "docs/R5_4_2/REVIEW_GIT_BYTE_PRESERVATION.json; existing info attributes retained",
                "files": count, "logical_bytes": total, "worktree_file_bytes": total,
                "entries": entries}
    (REPORT / "CLEANUP_REMOVAL_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    kept = [f"- KEEP `{CATEGORY}{digest}/`: {row['files']} files, {row['bytes']} bytes; active references: {', '.join(row['refs'])}." for digest, row in sorted(groups.items()) if digest not in safe_groups]
    plan = f"""# CLEANUP PLAN — PRODUCT-V1

Archive: `{SNAPSHOT}`; remote review ref verified with git ls-remote. Main/review are immutable. SAFE_TO_REMOVE: {count} exact files, {total} bytes, {len(safe_groups)} obsolete generated build directories. Full path list, Git IDs, SHA256, restoration commands and verification: CLEANUP_REMOVAL_MANIFEST.json.

Only old build copies referenced solely by the immutable original REVIEW_SNAPSHOT_MANIFEST are archived. That manifest continues to describe `{SNAPSHOT}`, not the product tree; its references are explicitly `archived_in_commit` in the product removal manifest. All files were recovered via git cat-file, Git blob ID and SHA256 verified, and compared with every worktree file. No original evidence is destroyed. No active runtime/src/tests/build/.github/pyproject reference was found by rg. Dynamic build_time_candidates tool uses current BUILD_TIME_CANDIDATE_READBACK and generates its destination by current input digest; all its active readback sets and dependencies remain present. Historical formal reports are evaluated from the archive commit.

SAFE_TO_REMOVE directories:
""" + "\n".join(f"- `{CATEGORY}{digest}/` ({groups[digest]['files']} files, {groups[digest]['bytes']} bytes)." for digest in sorted(safe_groups)) + "\n\n" + "\n".join(kept) + f"""

KEEP: src, tests, active build, .github, pyproject, legacy, F1-F8 qualifications, frozen normative sources, user untracked changes and raw/accepted evidence. KEEP checkpoint_history, normative_build_candidate, golden_build_candidate, build_schema_fixtures: identity-bearing formal inputs/references need more review; no blanket deletion. NEEDS_REVIEW: other duplicate groups and all unknown files. No deletion authorization inferred from their size.

Rollback on a product working branch: `git restore --source={SNAPSHOT} --worktree -- <exact path from manifest>`. To restore all removed files, pass the manifest paths via a NUL pathspec file and --pathspec-from-file/--pathspec-file-nul. Formal R5.4.2 workflow: create a separate checkout/worktree at the pinned archive; historical scripts and inputs there are complete. Gzip historical payloads: docs/R5_4_2/restore_review_evidence.py.

After removal: product tests + all affected safe surfaces, Ruff, mypy, standalone build/release-validator/smoke; protected Git identity and untracked preservation checks. Reduction concerns file bytes in active worktree only. Git history retains blobs; .git and a full clone do not automatically shrink. Exact .git measurements and before/after tree sizes are recorded in CLEANUP_RESULT.json after execution.
"""
    (REPORT / "CLEANUP_PLAN.md").write_text(plan, encoding="utf-8")
    print(json.dumps({"safe_files": count, "bytes": total, "directories": len(safe_groups), "unique_blobs_read_back": len(checked)}))


if __name__ == "__main__":
    main()
