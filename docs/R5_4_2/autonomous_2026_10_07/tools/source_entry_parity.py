"""Execute symlink materializer branch on controlled Git command responses."""

import base64
import copy
import hashlib
import sys
from unittest.mock import patch

from jsonschema import Draft202012Validator

from execution import BASE, OUT, ROOT, digest, read, write

sys.path.insert(0, str(ROOT / "src"))

from bdb_audit.source import materializer  # noqa: E402
from bdb_audit.source.git_resolver import VerifiedGitIdentity  # noqa: E402


def main():
    schema_path = OUT / "design/body_grammars/source_manifest__2.json"
    readback = read(OUT / "design/source_instance_readback/READBACK.json")
    assert readback["schema_raw_digest"] == digest(schema_path), "SOURCE_READBACK_SCHEMA_DRIFT"
    validator = Draft202012Validator(read(schema_path))
    retained = OUT / "design/source_instance_readback/source_manifest_body.json"
    prior = read(OUT / "design/source_instance_readback/READBACK.json")
    assert digest(retained) == prior["body_raw_digest"]
    assert validator.is_valid(read(retained)), "Current /2 must retain real regular-member source parity"
    old = Draft202012Validator(read(BASE / "candidate/schemas/source_manifest__1.schema.json"))
    controls = []
    for target in (b"../external-target", b"\xff\xfe-target", b"target\nwith-newline"):
        def responses(repo, args, **kwargs):
            if args[0] == "ls-tree":
                return b"120000 blob " + b"a" * 40 + b"\tlink\x00"
            assert args == ["cat-file", "blob", "a" * 40]
            return target

        identity = VerifiedGitIdentity(str(ROOT), "CONTROLLED", "b" * 40, "c" * 40)
        with patch.object(materializer, "_git_bytes", responses):
            result = materializer._manifest_from_repo(ROOT, identity)
        body = result.manifest_body()
        assert validator.is_valid(body)
        assert not old.is_valid(body)
        entry = body["entries"][0]
        decoded = base64.b64decode(entry["symlink_target"], validate=True)
        assert decoded == target
        assert base64.b64encode(decoded).decode("ascii") == entry["symlink_target"]
        assert len(decoded) == entry["byte_length"]
        assert hashlib.sha256(decoded).hexdigest() == entry["content_raw_digest"]
        controls.append({"case": "EXACT_TARGET_BYTES_" + target.hex(), "result": "PASS",
                         "manifest": body, "runtime_input": "Controlled Git command responses, no actual authenticated tree"})
        for field in ("symlink_target", "symlink_target_encoding", "byte_length", "content_raw_digest"):
            missing = copy.deepcopy(body)
            del missing["entries"][0][field]
            assert not validator.is_valid(missing)
            controls.append({"case": "MISSING_" + field + "_" + target.hex(), "result": "PASS"})
        wrong = copy.deepcopy(body)
        wrong["entries"][0]["symlink_target_encoding"] = "utf8"
        assert not validator.is_valid(wrong)
        controls.append({"case": "WRONG_ENCODING_" + target.hex(), "result": "PASS"})
        wrong["entries"][0]["symlink_target_encoding"] = "base64"
        wrong["entries"][0]["entry_type"] = "REGULAR_FILE"
        assert not validator.is_valid(wrong)
        controls.append({"case": "ENCODING_ON_REGULAR_FILE_" + target.hex(), "result": "PASS"})
    write("design/SOURCE_ENTRY_PARITY_CONTROLS.json", {
        "controls": controls, "schema_raw_digest": digest(schema_path),
        "retained_actual_manifest_body_raw_digest": digest(retained),
        "retained_actual_manifest_current_schema": "PASS_ALL_499_ENTRIES_NO_REMATERIALIZATION",
        "materializer_raw_digest": digest(ROOT / "src/bdb_audit/source/materializer.py"),
        "qualification": False, "trusted_actual_input": "NOT_PROVEN",
        "canonical_base64_and_raw_reconciliation_guard": "NOT_IMPLEMENTED_BY_SCHEMA",
        "symlink_transport_and_durable_admission": "NOT_PROVEN", "NF02": "OPEN"})
    print(f"PASS {len(controls)} controlled symlink branch/schema controls; no trusted source or transport proof")


if __name__ == "__main__":
    main()
