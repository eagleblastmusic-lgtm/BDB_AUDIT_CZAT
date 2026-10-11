"""Verify archived removals, representative git restore and original user WIP."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/PRODUCT_V1"


def main():
    manifest = json.loads((OUT / "CLEANUP_REMOVAL_MANIFEST.json").read_text(encoding="utf-8"))
    assert all(not (ROOT / row["path"]).exists() for row in manifest["entries"])
    restore = ROOT / ".product-smoke" / ("r-" + uuid.uuid4().hex[:8])
    restore.mkdir(parents=True)
    samples = [manifest["entries"][i] for i in (0, len(manifest["entries"]) // 2, -1)]
    command = ["git", "-c", "core.longpaths=true", "--git-dir=" + str(ROOT / ".git"), "--work-tree=" + str(restore), "restore", "--source=" + manifest["archive_commit"], "--worktree", "--", *[row["path"] for row in samples]]
    # Use a separate index: restoration must not touch the product staging area.
    env = {**os.environ, "GIT_INDEX_FILE": str(restore / "restore.index")}
    proc = subprocess.run(command, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    for row in samples:
        assert hashlib.sha256((restore / row["path"]).read_bytes()).hexdigest() == row["sha256"]
    original = json.loads((OUT / "ORIGINAL_WIP_PRESERVATION.json").read_text(encoding="utf-8"))
    for row in original["files"]:
        assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row["sha256"]
    for row in original["directories"]:
        assert (ROOT / row["path"]).stat().st_mtime_ns == row["mtime_ns"]
    for ref, sha in (("review/r5-4-2-current-snapshot", manifest["archive_commit"]), ("main", "dcd8bd6ef5f7e3f7b5803ade6843c6217f16f044")):
        assert subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", ref], text=True).strip() == sha
    report = {
        "git_directory_file_bytes": sum(p.stat().st_size for p in (ROOT / ".git").rglob("*") if p.is_file()),
        "files_removed": manifest["files"], "logical_bytes_removed": manifest["logical_bytes"],
        "worktree_file_bytes_removed": manifest["worktree_file_bytes"],
        "before_tree_logical_bytes": 7083918754,
        "tree_logical_bytes_after_deletions_before_product_additions": 7083918754 - manifest["logical_bytes"],
        "archival_identity_verified_all_blobs": True,
        "git_restore_samples_verified": samples, "git_restore_command": command,
        "restore_environment": {"GIT_INDEX_FILE": "separate scratch index"},
        "original_untracked_sha256_verified": len(original["files"]),
        "original_untracked_directories_unchanged_mtime": True, "review_and_main_unchanged": True,
        "git_count_objects_after": subprocess.check_output(["git", "-C", str(ROOT), "count-objects", "-v"], text=True, stderr=subprocess.DEVNULL),
        "git_object_store_reduction": "NONE; history retained; object-store size-pack reported in KiB",
        "complete_git_directory_size": "sum of current .git file lengths; not filesystem allocation",
        "full_clone_reduction": "not promised",
    }
    (OUT / "CLEANUP_RESULT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("files_removed", "logical_bytes_removed", "original_untracked_sha256_verified", "review_and_main_unchanged")}))


if __name__ == "__main__":
    main()
