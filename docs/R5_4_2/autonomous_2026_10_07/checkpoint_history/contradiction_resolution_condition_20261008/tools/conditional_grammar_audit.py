"""Known answers for root assertions lost by field-only reconstruction.

These check draft grammar only. They establish neither trusted production nor
cross-object applicability and do not execute a canonical operation.
"""

from __future__ import annotations

import copy

from jsonschema import Draft202012Validator

from execution import OUT, preserve, read, write
from profile_design_audit import fixture


def main():
    preserve()
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    results = []

    def run(key, label, value, expected):
        schema = read(OUT / "design/body_grammars" / (mapping[key].replace("/", "__") + ".json"))
        actual = Draft202012Validator(schema).is_valid(value)
        assert actual == expected, (key, label, [e.message for e in Draft202012Validator(schema).iter_errors(value)])
        results.append({"schema_key": mapping[key], "case": label, "input": copy.deepcopy(value), "expected": "ACCEPT" if expected else "REJECT", "grammar_result": "PASS", "canonical_runtime": "NOT_RUN"})

    def base(key):
        schema = read(OUT / "design/body_grammars" / (mapping[key].replace("/", "__") + ".json"))
        return schema, fixture(schema, schema["$defs"])

    key = "source_generation/1"
    schema, value = base(key)
    profile = fixture(schema["$defs"]["external_profile_ref"], schema["$defs"])
    run(key, "AUTHORITY_MISSING", value, False)
    value["repository_authority_ref"] = profile
    run(key, "EXACT_REPOSITORY_BRANCH", value, True)
    value["snapshot_authority_ref"] = profile
    run(key, "BOTH_AUTHORITIES", value, False)
    del value["repository_authority_ref"]
    run(key, "EXACT_SNAPSHOT_BRANCH", value, True)

    key = "history_cut/1"
    schema, _ = base(key)
    empty = fixture(schema["$defs"]["empty_history_cut"], schema["$defs"])
    accepted = fixture(schema["$defs"]["accepted_history_cut"], schema["$defs"])
    run(key, "EXACT_EMPTY_CUT", empty, True)
    run(key, "EXACT_ACCEPTED_CUT", accepted, True)
    run(key, "HYBRID_EMPTY_ACCEPTED_CUT", {**empty, **accepted}, False)
    for field in ("campaign_id", "accepted_head_hash", "accepted_head_seq"):
        partial = copy.deepcopy(accepted)
        del partial[field]
        run(key, "MISSING_ACCEPTED_CUT_" + field, partial, False)
    run(key, "GOVERNANCE_ONLY_WITHOUT_HEAD_OR_NAMESPACE", {k: v for k, v in empty.items() if k in ("governing_policy_ref", "governing_spec_refs")}, False)

    for key, selector, value, required in (
        ("source_identity/1", "authority_mode", "AUTHORIZED_GIT", ["git_commit_object_id", "git_tree_object_id"]),
        ("trusted_predecessor_selection_decision/1", "decision", "SELECTED", ["selected_legacy_ref"]),
        ("bootstrap_admission_decision/1", "requested_role", "CANONICAL_PREDECESSOR", ["trusted_predecessor_selection_ref"]),
    ):
        schema, body = base(key)
        body[selector] = value
        for field in required:
            body[field] = fixture(schema["properties"][field], schema["$defs"])
        run(key, "REQUIRED_CONTEXT_PRESENT", body, True)
        for field in required:
            missing = copy.deepcopy(body)
            del missing[field]
            run(key, "REQUIRED_CONTEXT_MISSING_" + field, missing, False)

    key = "input_disposition_record/2"
    schema, body = base(key)
    body["disposition"] = "COLLECTED"
    run(key, "TERMINAL_SOURCE_MEMBER_WITHOUT_CAPTURE", body, False)
    body["collector_record_ref"] = fixture(schema["properties"]["collector_record_ref"], schema["$defs"])
    run(key, "TERMINAL_SOURCE_MEMBER_WITH_CAPTURE", body, True)
    del body["collector_record_ref"]
    body["disposition"] = "PROVISIONAL"
    run(key, "PROVISIONAL_WITHOUT_CAPTURE", body, True)

    key = "grant_body/1"
    schema, body = base(key)
    body["previous_knowledge_state_ref"] = None
    run(key, "INITIAL_KNOWLEDGE_NULL_SENTINEL", body, True)
    missing = copy.deepcopy(body)
    del missing["previous_knowledge_state_ref"]
    run(key, "OMITTED_KNOWLEDGE_SENTINEL", missing, False)
    previous = fixture(schema["properties"]["previous_knowledge_state_ref"]["oneOf"][1], schema["$defs"])
    body["previous_knowledge_state_ref"] = previous
    run(key, "SUCCESSOR_KNOWLEDGE_REFERENCE_SYNTAX", body, True)
    wrong = copy.deepcopy(body)
    wrong["previous_knowledge_state_ref"]["kind"] = "attempt"
    run(key, "WRONG_KNOWLEDGE_REFERENCE_KIND", wrong, False)

    key = "scope_state_record/1"
    schema, body = base(key)
    body["state"] = "EXCLUDED_SCOPE"
    run(key, "EXCLUDED_SCOPE_WITHOUT_DECISION", body, False)
    body["scope_decision_ref"] = fixture(schema["properties"]["scope_decision_ref"], schema["$defs"])
    run(key, "EXCLUDED_SCOPE_WITH_DECISION_SYNTAX", body, True)
    for state in schema["properties"]["state"]["enum"]:
        if state == "EXCLUDED_SCOPE":
            continue
        body["state"] = state
        run(key, state + "_WITH_FORBIDDEN_SCOPE_DECISION", body, False)
        without = copy.deepcopy(body)
        del without["scope_decision_ref"]
        run(key, state + "_WITHOUT_SCOPE_DECISION", without, True)

    # Data 123: inputs are frozen before output production. These controls
    # prove the tagged entry representation only; declared complete inputs,
    # installed provenance and transitive output exclusion remain semantic.
    key = "build_manifest/1"
    schema, body = base(key)
    branches = schema["$defs"]["build_input_ref"]["oneOf"]
    for field in ("ordered_input_refs", "embedded_resource_refs"):
        for branch in branches:
            entry = fixture(branch, schema["$defs"])
            tag = entry["input_kind"]
            reference_field = next(name for name in entry if name != "input_kind")
            good = copy.deepcopy(body)
            good[field] = [entry]
            run(key, field + "_" + tag + "_EXACT_BRANCH", good, True)
            missing = copy.deepcopy(good)
            del missing[field][0][reference_field]
            run(key, field + "_" + tag + "_MISSING_REF", missing, False)
            for other in branches:
                extra = fixture(other, schema["$defs"])
                if extra["input_kind"] == tag:
                    continue
                mixed = copy.deepcopy(good)
                mixed[field][0].update({name: value for name, value in extra.items() if name != "input_kind"})
                run(key, field + "_" + tag + "_MIXED_WITH_" + extra["input_kind"], mixed, False)
            duplicate = copy.deepcopy(good)
            duplicate[field].append(copy.deepcopy(entry))
            run(key, field + "_" + tag + "_DUPLICATE_ENTRY", duplicate, False)
    run(key, "FINAL_OUTPUT_HASH_IN_FROZEN_BUILD_INPUT", {**body, "final_output_raw_digest": "0" * 64}, False)
    # Replay the retained snapshots, after every fixture mutation is finished.
    # A live alias to a later-mutated body is not evidence of the tested input.
    for result in results:
        schema = read(OUT / "design/body_grammars" / (result["schema_key"].replace("/", "__") + ".json"))
        actual = Draft202012Validator(schema).is_valid(result["input"])
        assert actual == (result["expected"] == "ACCEPT"), ("RETAINED_VECTOR_DRIFT", result["schema_key"], result["case"])
    write("design/CONDITIONAL_GRAMMAR_KNOWN_ANSWERS.json", {"vectors": results, "retained_vectors_replayed": len(results), "status": "PASS", "qualification": False,
          "claim": "Draft root/branch syntax only; producer, source, HistoryCut applicability and no-mutation checks NOT_RUN"})
    print({"draft_conditional_known_answers": len(results), "result": "PASS"})


if __name__ == "__main__":
    main()
