"""Retain a real source representation and verify all original source bytes."""

import hashlib
import io
import subprocess
import sys
import zipfile

from execution import OUT, ROOT, digest, git, read, write

sys.path.insert(0, str(ROOT / "src"))

from bdb_audit.assurance.zip_safety import Limits, read_bytes  # noqa: E402


def main():
    prior = read(OUT / "design/source_instance_readback/READBACK.json")
    head = prior["source_HEAD"]
    assert git("rev-parse", "HEAD") == head
    manifest = read(OUT / "design/source_instance_readback/source_manifest_body.json")
    result = subprocess.run(["git", "archive", "--format=zip", head], cwd=ROOT, capture_output=True, check=True)
    expected = {e["repo_relative_posix_path"]: e for e in manifest["entries"]}
    assert len(expected) == len(manifest["entries"])
    input_archive = zipfile.ZipFile(io.BytesIO(result.stdout))
    members = [i for i in input_archive.infolist() if not i.is_dir()]
    assert len(members) == len(expected) and {i.filename for i in members} == set(expected), "Git export omission/alias"
    output = io.BytesIO()
    readback = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as writer:
        for name in sorted(expected, key=lambda n: n.encode("utf-8")):
            entry = expected[name]
            data = input_archive.read(name)
            assert len(data) == entry["byte_length"]
            raw = hashlib.sha256(data).hexdigest()
            assert raw == entry["content_raw_digest"], name
            assert entry["entry_type"] == "REGULAR_FILE", "This actual dataset must not imply untested symlink/submodule support"
            # Git archive may alter permission metadata; explicitly retain the
            # independently verified original manifest's exact source mode.
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = int(entry["relevant_mode"], 8) << 16
            writer.writestr(info, data)
            readback.append({"path": name, "raw_digest": raw, "byte_length": len(data), "mode": entry["relevant_mode"]})
    path = OUT / "design/source_instance_readback/source_head_representation.zip"
    path.write_bytes(output.getvalue())
    bounded_members = read_bytes(path.read_bytes(), limits=Limits(members=65536, input_bytes=67108864, expanded_bytes=67108864))
    assert set(bounded_members) == set(expected)
    assert all(hashlib.sha256(data).hexdigest() == expected[name]["content_raw_digest"] for name, data in bounded_members.items())
    with zipfile.ZipFile(path) as final:
        assert len(final.infolist()) == len(expected)
        for info in final.infolist():
            entry = expected[info.filename]
            assert info.external_attr >> 16 == int(entry["relevant_mode"], 8)
            assert hashlib.sha256(final.read(info)).hexdigest() == entry["content_raw_digest"]
    write("design/source_instance_readback/ARCHIVE_READBACK.json", {
        "source_HEAD": head, "source_manifest_body_raw_digest": prior["body_raw_digest"],
        "source_manifest_object_digest_v2": prior["source_manifest_object_digest_v2"],
        "archive_raw_digest": digest(path), "archive_bytes": path.stat().st_size,
        "members": readback, "complete_exact_regular_member_readback": True,
        "mode_handling": "Transport metadata explicitly equals verified original manifest mode; no source-byte transform",
        "symlink_submodule_lfs_transport_controls": "NOT_EXECUTED_IN_THIS_ALL_REGULAR_DATASET",
        "bounded_existing_zip_parser_readback": "PASS_ALL_REGULAR_MEMBERS",
        "zip_parser_raw_digest": digest(ROOT / "src/bdb_audit/assurance/zip_safety.py"),
        "qualification": False, "accepted_instance": False, "NF02": "OPEN"})
    print(f"PASS retained actual source ZIP, {len(readback)} exact raw members/modes; not qualification")


if __name__ == "__main__":
    main()
