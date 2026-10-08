"""Execute current source parser on retained real HEAD archive and manifest."""

import hashlib
import sys

from execution import OUT, ROOT, digest, git, read, write

sys.path.insert(0, str(ROOT / "src"))

from bdb_audit.source.archive import read_complete_source_archive  # noqa: E402
from bdb_audit.source.git_resolver import VerifiedGitIdentity, resolve_local_repository  # noqa: E402
from bdb_audit.source.materializer import SourceMaterialization  # noqa: E402


def main():
    folder = OUT / "design/source_instance_readback"
    prior = read(folder / "READBACK.json")
    archive_record = read(folder / "ARCHIVE_READBACK.json")
    body = folder / "source_manifest_body.json"
    archive = folder / "source_head_representation.zip"
    assert digest(body) == prior["body_raw_digest"]
    assert digest(archive) == archive_record["archive_raw_digest"]
    assert git("rev-parse", "HEAD") == prior["source_HEAD"]
    identity = VerifiedGitIdentity(**prior["identity"])
    assert resolve_local_repository(ROOT, "HEAD", prior["source_HEAD"]) == identity
    source = SourceMaterialization(identity, tuple(read(body)["entries"]), prior["completeness_state"], tuple(prior["limitations"]))
    result = read_complete_source_archive(archive.read_bytes(), source)
    assert len(result) == prior["entry_count"] == 499
    write("design/source_instance_readback/SOURCE_PARSER_READBACK.json", {
        "source_HEAD": prior["source_HEAD"], "source_manifest_body_raw_digest": digest(body),
        "source_archive_raw_digest": digest(archive), "member_count": len(result),
        "member_raw_digests": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(result.items())},
        "parser_inputs": {name: digest(ROOT / name) for name in (
            "src/bdb_audit/source/archive.py", "src/bdb_audit/source/git_resolver.py",
            "src/bdb_audit/source/materializer.py", "src/bdb_audit/assurance/zip_safety.py")},
        "actual_regular_member_runtime": "PASS_499_EXACT_MEMBERS", "member_materialization": "REUSED_EXACT_RETAINED_HEAD_INPUT",
        "trusted_profile_installation": "NOT_PROVEN", "qualification": False, "accepted_instance": False, "NF02": "OPEN"})
    print("PASS current source parser on 499 actual retained members; no profile activation or qualification")


if __name__ == "__main__":
    main()
