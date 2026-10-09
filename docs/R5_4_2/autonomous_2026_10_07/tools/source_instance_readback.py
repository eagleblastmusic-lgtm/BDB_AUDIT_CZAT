"""Read a real Git source manifest; no installation/acceptance authority."""

import dataclasses
import hashlib
import json
import sys

from jsonschema import Draft202012Validator

from execution import BASE, OUT, ROOT, digest, git, read, write

sys.path.insert(0, str(ROOT / "src"))

from bdb_audit.core.canonical_json import canonical_bytes  # noqa: E402
from bdb_audit.source.materializer import materialize_local_source  # noqa: E402
from bdb_audit.source.git_resolver import resolve_local_repository  # noqa: E402


def main():
    head = git("rev-parse", "HEAD")
    body_path = OUT / "design/source_instance_readback/source_manifest_body.json"
    reused = sys.argv[1:] == ["--revalidate-retained"]
    assert not sys.argv[1:] or reused, "Unknown readback option"
    prior = None
    if reused:
        prior = read(OUT / "design/source_instance_readback/READBACK.json")
        assert prior["source_HEAD"] == head and digest(body_path) == prior["body_raw_digest"]
        assert prior["materializer_raw_digest"] == digest(ROOT / "src/bdb_audit/source/materializer.py")
        assert dataclasses.asdict(resolve_local_repository(ROOT, "HEAD", head)) == prior["identity"]
        body = read(body_path)
        assert len(body["entries"]) == prior["entry_count"]
    else:
        # Source dataset is exact committed HEAD, not dirty application inputs.
        source = materialize_local_source(ROOT, "HEAD", head)
        body = source.manifest_body()
    old = read(BASE / "candidate/schemas/source_manifest__1.schema.json")
    new_path = OUT / "design/body_grammars/source_manifest__2.json"
    successor = read(new_path)
    old_errors = [{"path": list(e.path), "message": e.message} for e in Draft202012Validator(old).iter_errors(body)]
    new_errors = [{"path": list(e.path), "message": e.message} for e in Draft202012Validator(successor).iter_errors(body)]
    data = canonical_bytes(body)
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(data)
    write("design/source_instance_readback/READBACK.json", {
        "source_HEAD": head, "identity": prior["identity"] if reused else dataclasses.asdict(source.identity),
        "entry_count": len(body["entries"]), "completeness_state": prior["completeness_state"] if reused else source.completeness_state,
        "limitations": prior["limitations"] if reused else list(source.limitations), "predecessor_errors": old_errors,
        "successor_errors": new_errors, "schema_raw_digest": digest(new_path),
        "body_raw_digest": digest(body_path),
        "source_manifest_object_digest_v2": hashlib.sha256(b"BDB2/source_manifest/2\0" + data).hexdigest(),
        "materializer_raw_digest": digest(ROOT / "src/bdb_audit/source/materializer.py"),
        "dataset": "Real exact committed source test input; different from dirty application build inputs",
        "materialization": "REUSED_EXACT_RETAINED_INPUT" if reused else "FRESH_REAL_GIT_MATERIALIZATION",
        "qualification": False, "accepted_instance": False, "trusted_installation_authority": "NOT_PROVEN"})
    assert not new_errors, json.dumps(new_errors, ensure_ascii=False)
    assert git("rev-parse", "HEAD") == head
    print(f"PASS actual source manifest /2 shape, {len(body['entries'])} entries; predecessor errors {len(old_errors)}; not qualification")


if __name__ == "__main__":
    main()
