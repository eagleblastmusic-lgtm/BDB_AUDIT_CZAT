"""Restore exact oversized review evidence; never replace conflicting bytes."""

import gzip
import hashlib
import json
import os
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    manifest = json.loads((ROOT / "docs/R5_4_2/REVIEW_EVIDENCE_ARCHIVE_MANIFEST.json").read_text(encoding="utf-8"))
    for entry in manifest["entries"]:
        target = (ROOT / entry["original_path"]).resolve()
        archive = (ROOT / entry["archive_path"]).resolve()
        if not target.is_relative_to(ROOT) or not archive.is_relative_to(ROOT):
            raise ValueError("ARCHIVE_PATH_OUTSIDE_REPOSITORY")
        if archive.stat().st_size != entry["archive_bytes"] or digest(archive) != entry["archive_sha256"]:
            raise ValueError("ARCHIVE_BYTES_CHANGED")
        if target.exists():
            if target.stat().st_size != entry["original_bytes"] or digest(target) != entry["original_sha256"]:
                raise ValueError("EXISTING_EVIDENCE_CONFLICT: " + entry["original_path"])
            print("Already exact:", entry["original_path"])
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / (".restore-" + uuid.uuid4().hex)
        try:
            with temporary.open("xb") as sink, gzip.open(archive, "rb") as source:
                while chunk := source.read(1024 * 1024):
                    sink.write(chunk)
                sink.flush()
                os.fsync(sink.fileno())
            if temporary.stat().st_size != entry["original_bytes"] or digest(temporary) != entry["original_sha256"]:
                raise ValueError("RESTORED_EVIDENCE_BYTES_CHANGED")
            # Atomic creation rejects an existing destination without overwriting it.
            os.link(temporary, target)
            print("Restored exact:", entry["original_path"])
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
