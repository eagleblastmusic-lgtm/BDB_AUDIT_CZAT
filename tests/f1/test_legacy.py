import json
import pytest

from dual_support import *


@pytest.fixture(scope="module")
def dual():
    return {r["fixture_id"]: r for r in run_dual()}


IDS = [r["fixture_id"] for r in json.loads((CORPUS / "manifest.json").read_bytes())["fixtures"]]


@pytest.mark.parametrize("fixture_id", IDS)
def test_dual_corpus(dual, fixture_id):
    row = dual[fixture_id]
    assert row["preservation"], row
    assert row["correctness"], row
    assert row["bug_misclassified_safe"] == 0


def test_two_oracles():
    accepted = {"status": "PASS", "error_families": []}
    rejected = {"status": "FAIL", "error_families": ["UNSAFE"]}
    assert compare(accepted, accepted, "REJECT", known_bug=True) == {
        "preservation": True, "correctness": False, "unexplained_diff": 0, "bug_misclassified_safe": 1}
    assert compare(rejected, accepted, "REJECT")["unexplained_diff"] == 1
    decision = {"version": "1", "revision_digest": "a"*64, "legacy": accepted, "hardened": rejected}
    result = compare(rejected, accepted, "REJECT", known_bug=True, exception=decision)
    assert result["preservation"] and result["correctness"]
    assert result["bug_misclassified_safe"] == 0


def test_prefix_sequence_boundaries():
    errors = []
    assert v2._validate_seq([{"seq": 1}, {"seq": 2}], "L", errors) == (1, 2)
    assert not errors
    for records in [[], [{"seq": "1"}], [{"seq": 1}, {"seq": 3}], [{"seq": 1}, {"seq": 1}]]:
        errors = []
        v2._validate_seq(records, "L", errors)
        assert errors


def test_previous_prompt_failure_paths():
    row = next(r for r in json.loads((CORPUS / "manifest.json").read_bytes())["fixtures"] if r["fixture_id"] == "VALID_PREVIOUS_PROMPT_BUNDLE")
    inputs = json.loads((CORPUS / "EXPECTATION_INPUTS.json").read_bytes())
    args = dict(consumer_variant_id="E2_SOL_ITERACJA_1", predecessor_variant_id="E1_SOL_BASE",
                bundle_sha256=inputs["previous_bundle_sha256"], prompt_hashes=inputs["previous_prompt_hashes"])
    assert v2.validate_previous_prompt_bundle(CORPUS/row["path"], **args)["status"] == "PASS"
    for key, value in [("consumer_variant_id", "wrong"), ("predecessor_variant_id", "wrong"), ("bundle_sha256", "0"*64), ("prompt_hashes", {})]:
        assert v2.validate_previous_prompt_bundle(CORPUS/row["path"], **(args | {key: value}))["status"] == "FAIL"


def test_exact_payload_metadata_and_duplicate_basename():
    frozen = load_legacy()
    for key, item in v2.DATA["payloads"].items():
        assert item == {k: frozen.DATA["payloads"][key][k] for k in ("name", "sha256")}
    errors, warnings = [], []
    assert v2._handoff_by_basename({"a.json": b"x", "evidence/a.json": b"x"}, errors, "a.json", warnings) == "a.json"
    assert not errors and warnings
    errors = []
    assert v2._handoff_by_basename({"a.json": b"x", "evidence/a.json": b"y"}, errors, "a.json") is None
    assert errors


def test_snapshot_raw_binding(tmp_path, monkeypatch):
    from bdb_audit.core.hashing import raw_digest
    row = next(r for r in json.loads((CORPUS/"manifest.json").read_bytes())["fixtures"] if r["fixture_id"] == "VALID_BASE_F1")
    raw = (CORPUS/row["path"]).read_bytes()
    path = tmp_path/"input.zip"
    path.write_bytes(raw)
    frozen = load_legacy()
    variant, step = selection(frozen, row["legacy_call"]["variant_id"], row["legacy_call"]["step_order"])
    original = v2._read_handoff_members
    def replace_after_read(owned, errors, **kwargs):
        members = original(owned, errors, **kwargs)
        path.write_bytes(b"changed after read")
        return members
    monkeypatch.setattr(v2, "_read_handoff_members", replace_after_read)
    result = v2.validate_prior_handoff_bundle(path, variant, step)
    assert result["status"] == "PASS"
    assert result["zip_sha256"] == raw_digest(raw).value
    assert result["zip_sha256"] != raw_digest(path.read_bytes()).value


def test_missing_and_malformed_archive(tmp_path):
    frozen = load_legacy()
    variant, step = selection(frozen, "E1_SOL_BASE_PLUS_PLIKI", 2)
    path = tmp_path/"absent.zip"
    assert v2.validate_prior_handoff_bundle(path, variant, step)["status"] == "FAIL"
    path.write_bytes(b"malformed")
    for fn, args in [(v2.validate_prior_handoff_bundle, ()), (v2.validate_attestation_bundle, ()), (v2.validate_result_bundle, (False,))]:
        assert fn(path, variant, step, *args)["status"] == "FAIL"
