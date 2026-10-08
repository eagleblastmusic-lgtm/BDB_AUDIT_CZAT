"""OD-028 finite representation controls; no trusted source proof."""

import copy

from jsonschema import Draft202012Validator

from execution import BASE, OUT, ROOT, digest, git, read, write
from profile_design_audit import fixture


def main():
    path = OUT / "design/body_grammars/source_identity__2.json"
    schema = read(path)
    validator = Draft202012Validator(schema)
    body = fixture(schema, schema["$defs"])
    # The independent fixture builder does not apply root conditionals.
    body["authority_mode"] = "AUTHORIZED_SNAPSHOT"
    controls = []
    for value in ("COMPLETE_SOURCE", "BOUNDED_SOURCE"):
        assert validator.is_valid({**body, "completeness_state": value})
        controls.append({"case": value + "_REPRESENTABLE", "result": "PASS", "eligibility": "NOT_PROVEN"})
    for value in ("PASS", "UNKNOWN", "", True, None, "COMPLETE_SOURCE "):
        assert not validator.is_valid({**body, "completeness_state": value})
        controls.append({"case": "UNKNOWN_OR_WRONG_STATUS_" + repr(value), "result": "PASS", "expected": "REJECT"})
    git_body = {**body, "authority_mode": "AUTHORIZED_GIT"}
    assert not validator.is_valid(git_body)
    controls.append({"case": "GIT_IDS_REMAIN_REQUIRED", "result": "PASS"})
    git_body.update(git_commit_object_id="a" * 40, git_tree_object_id="b" * 40)
    assert validator.is_valid(git_body)
    controls.append({"case": "GIT_SHAPE_NO_IDENTITY_PROOF", "result": "PASS", "reconciliation": "NOT_PROVEN"})
    for fields in (("git_commit_object_id",), ("git_tree_object_id",),
                   ("git_commit_object_id", "git_tree_object_id")):
        wrong = {**body, **{field: "a" * 40 for field in fields}}
        assert not validator.is_valid(wrong), "Snapshot must not carry Git identity IDs"
        controls.append({"case": "SNAPSHOT_GIT_IDENTITY_" + "_".join(fields), "result": "PASS", "expected": "REJECT"})
    extra = copy.deepcopy(body)
    extra["trusted"] = True
    assert not validator.is_valid(extra)
    controls.append({"case": "SERIALIZED_TRUST_REJECT", "result": "PASS"})
    contract = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")["SOURCE_IDENTITY_V2"]
    ps = contract["grammar"]
    pv = Draft202012Validator(ps)
    profile = fixture(ps, ps["$defs"])
    assert pv.is_valid(profile)
    for field in ("path_profile_ref", "manifest_entry_profile_ref", "authority_parameters", "submodule_policy", "lfs_policy", "symlink_policy", "mode_policy"):
        wrong = copy.deepcopy(profile)
        wrong.pop(field)
        assert not pv.is_valid(wrong)
        controls.append({"case": "REQUIRED_SOURCE_PARAMETER_" + field, "result": "PASS"})
    row = profile["authority_parameters"][0]
    for mode, algorithm, valid in (("AUTHORIZED_GIT", "SHA1", True), ("AUTHORIZED_GIT", "SHA256", True),
                                   ("AUTHORIZED_GIT", "NONE", False), ("AUTHORIZED_SNAPSHOT", "NONE", True),
                                   ("AUTHORIZED_SNAPSHOT", "SHA1", False), ("AUTHORIZED_GIT", "MD5", False)):
        wrong = copy.deepcopy(profile)
        wrong["authority_parameters"] = [{**row, "authority_mode": mode, "git_object_algorithm": algorithm}]
        assert pv.is_valid(wrong) == valid
        controls.append({"case": mode + "_" + algorithm, "result": "PASS", "authority": "NOT_PROVEN"})
    manifest = read(OUT / "design/body_grammars/source_manifest__2.json")
    path_shape = manifest["properties"]["entries"]["items"]["properties"]["repo_relative_posix_path"]
    paths = Draft202012Validator(path_shape)
    contracts = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    assert contracts["SOURCE_PATH_PROFILE_V1"]["grammar"]["properties"]["path_shape"]["const"] == path_shape
    controls.append({"case": "PATH_PROFILE_AND_MANIFEST_EXACT_SHAPE", "result": "PASS"})
    for value in (".gitignore", ".gitattributes", ".github/workflows/test.yml", "src/żółć.py", "a/.hidden"):
        assert paths.is_valid(value)
        controls.append({"case": "CANONICAL_PATH_" + value, "result": "PASS"})
    for value in (".", "..", "../a", "a/../b", "a/./b", "/a", "a/", "a//b", "a\\b", "a\0b", "x" * 513):
        assert not paths.is_valid(value)
        controls.append({"case": "INVALID_PATH_" + repr(value), "result": "PASS", "expected": "REJECT"})
    old_path = read(BASE / "candidate/schemas/source_manifest__1.schema.json")["$defs"]["member_path"]
    old_paths = Draft202012Validator(old_path)
    actual = git("-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", "HEAD").splitlines()
    rejected = [p for p in actual if not old_paths.is_valid(p)]
    assert rejected == [".gitattributes", ".github/workflows/v2-0-3-qualification.yml", ".gitignore"]
    assert all(paths.is_valid(p) for p in actual)
    controls.append({"case": "ACTUAL_HEAD_SOURCE_PATHS", "result": "PASS", "path_count": len(actual), "old_rejected": rejected})
    source = ROOT / "docs/R5_4_1/candidate/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md"
    write("design/SOURCE_IDENTITY_DESIGN_CONTROLS.json", {
        "controls": controls, "schema_raw_digest": digest(path), "source_raw_digest": digest(source),
        "profile_catalog_raw_digest": digest(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json"),
        "qualification": False, "actual_source_materialization": "NOT_PROVEN", "NF02": "OPEN"})
    print(f"PASS {len(controls)} source representation controls; actual identity NOT_PROVEN")


if __name__ == "__main__":
    main()
