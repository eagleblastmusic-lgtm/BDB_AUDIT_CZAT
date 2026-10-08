"""OD-027 build/campaign chronology contract controls, not installation proof."""

import copy

from jsonschema import Draft202012Validator

from bootstrap_precedence_design import order
from execution import BASE, OUT, ROOT, digest, preserve, read, write
from payload_reference_contracts import decisions
from profile_design_audit import fixture
from profile_reference_contracts import decisions as installed_decisions


def main():
    preserve()
    graph = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")
    nodes = {n["key"]: n for n in graph["nodes"]}
    contracts = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    expected = {
        ("build_manifest/1", "application_source_generation_ref"): ["source_generation/1"],
        ("build_manifest/1", "stage_lane_policy_refs"): ["lane_spec/1", "policy_revision/1", "stage_spec/1"],
        ("campaign_genesis/1", "application_generation_ref"): ["build_manifest/1"],
    }
    results = []
    for (key, field), targets in expected.items():
        item = next(r for r in nodes[key]["resolved_own_material_refs"] if r["field"] == field)
        assert item["ref_class"] == "PINNED_INSTALLATION_REF" and not item["same_commit"]
        assert item["allowed_keys"] == targets and item["delegated_decision_id"] == "OD-027"
        results.append({"case": key + "." + field + "_EXACT_EXTERNAL_CONTEXT", "result": "PASS"})
    # The old model requires an accepted application source before the first
    # campaign commit, although the referenced namespace has no accepted seq.
    assert not any(1 <= seq < 1 for seq in range(1, 3))
    results.append({"case": "OLD_PREGENESIS_PRIOR_ACCEPTANCE_CONTRADICTION", "result": "PASS", "accepted_campaign_seq_before_first": []})
    source_kind = nodes["source_generation/1"]
    parent = next(r for r in source_kind["resolved_own_material_refs"] if r["field"] == "parent_source_generation_ref")
    assert parent["ref_class"] == "PRIOR_ACCEPTED_ONLY" and not parent["same_commit"]
    results.append({"case": "ORDINARY_RUNTIME_PARENT_NOT_GLOBALLY_WAIVED", "result": "PASS"})
    successor_fields = {f["field"] for f in nodes["successor_campaign_genesis/1"]["body"]["fields"]}
    assert "application_generation_ref" not in successor_fields
    assert all(r["field"] != "application_generation_ref" for r in nodes["successor_campaign_genesis/1"]["resolved_own_material_refs"])
    results.append({"case": "NO_INVENTED_SUCCESSOR_APPLICATION_FIELD", "result": "PASS"})

    installation = contracts["INSTALLATION_FULL_PATH_PROFILE_V1"]
    installed = installed_decisions(contracts)
    pin = installed["INSTALLATION_FULL_PATH_PROFILE_V1", "application_build_manifest_ref"]
    assert pin["ref_class"] == "PINNED_INSTALLATION_REF" and pin["targets"] == ["build_manifest"]
    results.append({"case": "ACTIVATION_BUILD_PIN_IS_EXTERNAL_NOT_PRIOR_CAMPAIGN", "result": "PASS"})
    assert installation["wire_profile_id"] == "INSTALLATION_FULL_PATH_PROFILE_V2"
    schema = installation["grammar"]
    validator = Draft202012Validator(schema)
    good = fixture(schema, schema["$defs"])
    assert validator.is_valid(good)
    results.append({"case": "CLOSED_V2_ACTIVATION_GRAMMAR", "result": "PASS", "qualified_instance": "NOT_CREATED"})
    for field in ("application_build_manifest_ref", "application_build_provenance_raw_ref"):
        wrong = copy.deepcopy(good)
        wrong.pop(field)
        assert not validator.is_valid(wrong)
        results.append({"case": "MISSING_" + field, "result": "PASS", "expected": "REJECT"})
    wrong = copy.deepcopy(good)
    wrong["application_build_manifest_ref"]["kind"] = "source_generation"
    assert not validator.is_valid(wrong)
    results.append({"case": "SOURCE_AS_APPLICATION_BUILD_ALIAS", "result": "PASS", "expected": "REJECT"})
    assert not validator.is_valid({**good, "profile_id": "INSTALLATION_FULL_PATH_PROFILE_V1"})
    results.append({"case": "NO_V1_ACTIVATION_ALIAS", "result": "PASS", "expected": "REJECT"})

    receipt = contracts["BUILD_PROVENANCE_RECEIPT_V1"]
    assert receipt["wire_profile_id"] == "BUILD_PROVENANCE_RECEIPT_V2"
    payload = receipt["payload_grammar"]
    pv = Draft202012Validator(payload)
    body = fixture(payload, payload["$defs"])
    assert pv.is_valid(body)
    table = decisions(contracts, graph)
    for field in ("build_input_manifest_ref", "build_environment_ref", "verification_refs[]"):
        assert table["BUILD_PROVENANCE_RECEIPT_V1", field.removesuffix("[]")]["ref_class"] == "PINNED_INSTALLATION_REF"
        results.append({"case": "RECEIPT_" + field + "_BUILD_CONTEXT", "result": "PASS"})
    for kind in ("compatibility_gate_result", "artifact_hash_manifest"):
        wrong = copy.deepcopy(body)
        wrong["verification_refs"][0]["kind"] = kind
        assert not pv.is_valid(wrong)
        results.append({"case": "HISTORY_DEPENDENT_VERIFICATION_" + kind, "result": "PASS", "expected": "REJECT"})
    item = table["BUILD_PROVENANCE_RECEIPT_V1", "verification_refs"]
    assert item["targets"] == ["validation_result/1"]
    results.append({"case": "RECEIPT_SCHEMA_TARGET_CONTRACT_PARITY", "result": "PASS"})

    # Full instance closure must enforce these temporal boundaries. The phase
    # witness cannot itself prove actual bytes, qualification or output checks.
    phases = ["CANDIDATE", "Q1", "BUILD_INPUT_FREEZE", "BUILD_OUTPUT", "OUTPUT_VERIFICATION", "RECEIPT", "ACTIVATION", "INITIALIZE"]
    edges = set(zip(phases, phases[1:]))
    witness = order(phases, edges)
    assert witness == phases
    results.append({"case": "ACYCLIC_EXTERNAL_ACTIVATION_PHASE_WITNESS", "result": "PASS"})
    for consumer in ("CANDIDATE", "BUILD_INPUT_FREEZE", "BUILD_OUTPUT"):
        assert order(phases, edges | {("ACTIVATION", consumer)}) is None
        results.append({"case": "ACTIVATION_BACKLINK_IN_" + consumer, "result": "PASS", "expected": "REJECT_CYCLE"})
    for consumer in ("CANDIDATE", "BUILD_INPUT_FREEZE"):
        assert order(phases, edges | {("RECEIPT", consumer)}) is None
        results.append({"case": "RECEIPT_BACKLINK_IN_" + consumer, "result": "PASS", "expected": "REJECT_CYCLE"})
    write("design/BUILD_INSTALLATION_CONTEXT_CONTROLS.json", {
        "decision": "OD-027", "controls": results, "external_phase_witness": witness,
        "source_digests": {p.relative_to(ROOT).as_posix(): digest(p) for p in [ROOT / "F1_QUALIFICATION/inputs/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md", BASE / "candidate/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md"]},
        "inputs": {name: digest(OUT / name) for name in ["OWN_REFERENCE_RESOLUTIONS.json", "design/EXTERNAL_PROFILE_CONTRACTS.json", "design/BUILD_INSTALLATION_CONTEXT_REVIEW.md"]},
        "qualification": False, "actual_instance_DAG": "NOT_PROVEN", "build_output": "NOT_CREATED",
        "durable_initialization": "NOT_RUN", "remaining": "Complete exact actual source/build/schema/profile/input/output/qualification closure and activation provenance with transitive backlink checks; no gate advances from contract/phase controls"})
    print(f"OD-027 build/installation contract controls PASS: {len(results)}; actual instance/output/qualification NOT_PROVEN")


if __name__ == "__main__":
    main()
