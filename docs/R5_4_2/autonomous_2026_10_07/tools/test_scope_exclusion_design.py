"""Independent exploit controls for the read-only OD-026 model, not Q1."""

import copy
import hashlib

from execution import OUT, read
from profile_design_audit import fixture
from scope_exclusion_design import SnapshotModel, authorization, eligibility_key, encoded, exact_ref, schema


def base():
    _, _, grammar = schema("scope_state_record")
    common = grammar["$defs"]
    namespace = {"profile_id": "BOOTSTRAP_NAMESPACE_V2", "revision_digest": "1" * 64}
    policy = fixture(common["accepted_history_cut"]["properties"]["governing_policy_ref"], common)
    specs = fixture(common["accepted_history_cut"]["properties"]["governing_spec_refs"], common)
    cuts = {i: {"campaign_id": "campaign_00000000-0000-4000-8000-000000000001", "accepted_head_seq": i,
                "accepted_head_hash": hashlib.sha256(f"MODEL_CUT_{i}".encode()).hexdigest(),
                "governing_policy_ref": policy, "governing_spec_refs": specs} for i in range(1, 4)}
    context = SnapshotModel(cuts[1]["campaign_id"], namespace, cuts, {}, {}, {}, set(), [], cuts[3])
    manifest = {"entries": [{"repo_relative_posix_path": "src/main.py", "entry_type": "REGULAR_FILE",
                              "relevant_mode": "0644", "byte_length": 1,
                              "content_raw_digest": hashlib.sha256(b"x").hexdigest()}]}
    manifest_ref = exact_ref("source_manifest", manifest, None)
    fact(context, manifest_ref, manifest, 1)
    context.permitted_source_manifest_refs.append(manifest_ref)
    key = {"scope_kind": "SOURCE_MEMBER", "source_member": {"source_manifest_ref": manifest_ref, "member_path": "src/main.py"}}
    prior = {"scope_state_record_id": "scope_state_record_00000000-0000-4000-8000-000000000001",
             "scope_key": key, "state": "UNKNOWN_SCOPE", "basis_refs": [], "reason_codes": [],
             "scope_state_input_history_cut": cuts[1]}
    prior_ref = exact_ref("scope_state_record", prior, prior["scope_state_record_id"])
    fact(context, prior_ref, prior, 2)
    profile_grammar = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")["PRINCIPAL_AUTHORIZATION_V1"]["grammar"]
    principal = fixture(profile_grammar, profile_grammar["$defs"])
    principal.update(principal_id="HUMAN", role="OWNER", namespace_profile_ref=namespace,
                     permitted_operations=["APPROVE"], permitted_approval_purposes=["SCOPE_EXCLUSION"])
    actor = install(context, principal)
    authority = install(context, {**principal, "permitted_operations": ["ACCEPT", "APPROVE"]})
    decision = {"approval_id": "approval_decision_00000000-0000-4000-8000-000000000001",
                "decision_type": "SCOPE_EXCLUSION", "scope": [prior_ref], "requested_action": "Exclude this exact source member",
                "actor_ref": actor, "actor_authority_ref": authority, "input_history_cut": cuts[2],
                "related_refs": [], "decision": "APPROVED", "reason": "Explicit human scope selection"}
    decision_ref = exact_ref("approval_decision", decision, decision["approval_id"])
    fact(context, decision_ref, decision, 3)
    context.requests[encoded(decision_ref)] = {"principal_id": "HUMAN", "actor_ref": actor, "authority_ref": authority,
                                              "action": decision["requested_action"], "scope": decision["scope"]}
    record = {**prior, "scope_state_record_id": "scope_state_record_00000000-0000-4000-8000-000000000002",
              "state": "EXCLUDED_SCOPE", "scope_decision_ref": decision_ref, "scope_state_input_history_cut": cuts[3]}
    context.eligible_decisions.add(eligibility_key(decision_ref, record))
    # Proposed bytes are independent of the trusted snapshot's bodies/cuts.
    return copy.deepcopy(record), context


def fact(context, reference, body, seq):
    context.facts[encoded(reference)] = {"body": body, "accepted_seq": seq, "campaign_id": context.campaign_id,
                                       "namespace_ref": context.namespace_ref}


def install(context, body):
    reference = {"profile_id": body["profile_id"], "revision_digest": hashlib.sha256(encoded(body)).hexdigest()}
    context.profiles[encoded(reference)] = body
    return reference


def change_decision(record, context, **changes):
    old = record["scope_decision_ref"]
    entry = context.facts[encoded(old)]
    body = {**entry["body"], **changes}
    current = exact_ref("approval_decision", body, body["approval_id"])
    fact(context, current, body, entry["accepted_seq"])
    context.requests[encoded(current)] = copy.deepcopy(context.requests[encoded(old)])
    context.eligible_decisions.add(eligibility_key(current, record))
    record["scope_decision_ref"] = current


def controls():
    results = []

    def run(name, mutate=lambda r, c: None, expected="REJECT", reason=None):
        record, context = base()
        expected_parent = copy.deepcopy(context.parent_cut)
        mutate(record, context)
        before = copy.deepcopy((record, context))
        actual, code = authorization(record, context, expected_parent)
        assert actual == expected and (reason is None or code == reason), (name, actual, code)
        assert (record, context) == before, name + " mutated read-only model"
        results.append({"case": name, "expected": expected, "result": "PASS", "reason": code,
                        "model_state_unchanged": True, "canonical_runtime": "NOT_RUN"})

    run("SOURCE_MEMBER_PRIOR_RECORD_APPROVAL_THEN_EXCLUSION", expected="ALLOW")
    run("MISSING_DECISION", lambda r, c: r.pop("scope_decision_ref"), reason="RECORD_GRAMMAR")
    run("REJECTED_DECISION", lambda r, c: change_decision(r, c, decision="REJECTED"), reason="DECISION_PURPOSE_RESULT")
    for purpose in "COVERAGE_OBLIGATION_WAIVER RESIDUAL_RISK_ACCEPTANCE DESTRUCTIVE_ACTION LIVE_ACTION CONTINUATION_BUDGET LIMITED_CONCLUSION".split():
        run("WRONG_PURPOSE_" + purpose, lambda r, c, p=purpose: change_decision(r, c, decision_type=p), reason="DECISION_PURPOSE_RESULT")
    run("SAME_COMMIT_DECISION", lambda r, c: c.facts[encoded(r["scope_decision_ref"])].update(accepted_seq=4), reason="PRIOR_ACCEPTANCE")
    run("UNACCEPTED_DECISION", lambda r, c: c.facts[encoded(r["scope_decision_ref"])].update(accepted_seq=0), reason="PRIOR_ACCEPTANCE")
    run("FOREIGN_CAMPAIGN_DECISION", lambda r, c: c.facts[encoded(r["scope_decision_ref"])].update(campaign_id="OTHER"), reason="FACT_CONTEXT")
    run("FOREIGN_NAMESPACE_DECISION", lambda r, c: c.facts[encoded(r["scope_decision_ref"])].update(namespace_ref={}), reason="FACT_CONTEXT")
    run("SCHEMA_SUBSTITUTION", lambda r, c: r["scope_decision_ref"]["schema_revision_ref"].update(revision_digest="a" * 64), reason="EXACT_REFERENCE_MISSING")
    run("BODY_MUTATION_WITHOUT_REHASH", lambda r, c: c.facts[encoded(r["scope_decision_ref"])]["body"].update(reason="tampered"), reason="OBJECT_HASH")
    def logical_id_alias(record, context):
        old = record["scope_decision_ref"]
        current = {**old, "logical_id": "approval_decision_00000000-0000-4000-8000-000000000009"}
        context.facts[encoded(current)] = copy.deepcopy(context.facts[encoded(old)])
        record["scope_decision_ref"] = current
    run("LOGICAL_ID_ALIAS_TO_SAME_BODY", logical_id_alias, reason="LOGICAL_ID_BODY_BINDING")
    run("MEMBER_NAME_SUBSTITUTION", lambda r, c: r["scope_key"]["source_member"].update(member_path="src/other.py"), reason="EXACT_SOURCE_MEMBER")
    run("WRONG_SOURCE_APPLICABILITY", lambda r, c: c.permitted_source_manifest_refs.clear(), reason="SOURCE_APPLICABILITY")
    run("MISSING_AUTHENTICATED_REQUEST", lambda r, c: c.requests.clear(), reason="AUTHENTICATED_REQUEST")
    run("ACTION_CHANGED", lambda r, c: change_decision(r, c, requested_action="Different action"), reason="AUTHENTICATED_ACTION_SCOPE")
    run("SCOPE_CHANGED", lambda r, c: c.requests[encoded(r["scope_decision_ref"])].update(scope=[]), reason="AUTHENTICATED_ACTION_SCOPE")
    run("ACTOR_SPOOFING", lambda r, c: c.requests[encoded(r["scope_decision_ref"])].update(principal_id="EXECUTOR"), reason="AUTHENTICATED_REQUEST")
    run("STALE_POLICY_ELIGIBILITY", lambda r, c: c.eligible_decisions.clear(), reason="CURRENT_POLICY_APPLICABILITY")
    run("PARENT_DRIFT", lambda r, c: c.parent_cut.update(accepted_head_hash="e" * 64), reason="PARENT_CHANGED")
    run("APPROVAL_INPUT_NOT_PRIOR", lambda r, c: change_decision(r, c, input_history_cut=c.cuts[3]), reason="APPROVAL_INPUT_PRIOR")
    run("CUT_WRONG_HASH", lambda r, c: r["scope_state_input_history_cut"].update(accepted_head_hash="f" * 64), reason="CUT_BINDING")
    run("EMPTY_CUT_AFTER_GENESIS", lambda r, c: r.update(scope_state_input_history_cut={"kind": "EMPTY_HISTORY_CUT", "history_namespace_ref": c.namespace_ref,
        "governing_policy_ref": c.parent_cut["governing_policy_ref"], "governing_spec_refs": c.parent_cut["governing_spec_refs"]}), reason="CUT_CAMPAIGN")

    def authority_change(record, context, **change):
        decision = context.facts[encoded(record["scope_decision_ref"])]["body"]
        current = context.profiles[encoded(decision["actor_authority_ref"])]
        reference = install(context, {**current, **change})
        change_decision(record, context, actor_authority_ref=reference)
        context.requests[encoded(record["scope_decision_ref"])]["authority_ref"] = reference

    run("GENERAL_APPROVE_WITHOUT_PURPOSE", lambda r, c: authority_change(r, c, permitted_approval_purposes=[]), reason="AUTHORITY_CLASS")
    run("WRONG_AUTHORITY_PURPOSE", lambda r, c: authority_change(r, c, permitted_approval_purposes=["LIVE_ACTION"]), reason="AUTHORITY_CLASS")
    run("PURPOSE_WITHOUT_APPROVE", lambda r, c: authority_change(r, c, permitted_operations=["EXECUTE"]), reason="AUTHORITY_CLASS")
    run("AUTHORITY_FOR_DIFFERENT_PRINCIPAL", lambda r, c: authority_change(r, c, principal_id="OTHER"), reason="PRINCIPAL_MISMATCH")
    run("UNINSTALLED_AUTHORITY", lambda r, c: c.profiles.clear(), reason="INSTALLATION_PIN")

    def other_member(record, context):
        old_manifest_ref = context.permitted_source_manifest_refs[0]
        body = copy.deepcopy(context.facts[encoded(old_manifest_ref)]["body"])
        body["entries"].append({**body["entries"][0], "repo_relative_posix_path": "src/other.py"})
        current = exact_ref("source_manifest", body, None)
        fact(context, current, body, 1)
        context.permitted_source_manifest_refs.append(current)
        record["scope_key"]["source_member"] = {"source_manifest_ref": current, "member_path": "src/other.py"}
    run("EXISTING_MEMBER_OUTSIDE_APPROVED_SCOPE", other_member, reason="EXACT_APPROVED_SCOPE")

    def unaccepted_scope(record, context):
        reference = context.facts[encoded(record["scope_decision_ref"])]["body"]["scope"][0]
        context.facts[encoded(reference)]["accepted_seq"] = 3
    run("SCOPE_ONLY_ACCEPTED_AFTER_APPROVAL_INPUT", unaccepted_scope, reason="PRIOR_ACCEPTANCE")

    def two_scope_members(record, context, reverse=False):
        decision = context.facts[encoded(record["scope_decision_ref"])]["body"]
        original = decision["scope"][0]
        prior = copy.deepcopy(context.facts[encoded(original)]["body"])
        prior["scope_state_record_id"] = "scope_state_record_00000000-0000-4000-8000-000000000003"
        additional = exact_ref("scope_state_record", prior, prior["scope_state_record_id"])
        fact(context, additional, prior, 2)
        scopes = [original, additional]
        if reverse:
            scopes.reverse()
        change_decision(record, context, scope=scopes)
        context.requests[encoded(record["scope_decision_ref"])]["scope"] = scopes
    run("COMPLETE_MULTI_SUBJECT_AUTHENTICATED_SCOPE", two_scope_members, expected="ALLOW")
    run("UNSORTED_SCOPE_SET", lambda r, c: two_scope_members(r, c, reverse=True), reason="SCOPE_SET_ORDER")

    def wrong_key(record, context):
        previous_ref = context.facts[encoded(record["scope_decision_ref"])]["body"]["scope"][0]
        record["scope_key"] = {"scope_kind": "CANONICAL_SUBJECT", "subject_ref": previous_ref}
        record["scope_ref"] = previous_ref
        context.eligible_decisions.add(eligibility_key(record["scope_decision_ref"], record))
    run("EXACT_CANONICAL_SUBJECT", wrong_key, expected="ALLOW")
    def unbound_key(record, context):
        previous_ref = context.facts[encoded(record["scope_decision_ref"])]["body"]["scope"][0]
        record["scope_key"] = {"scope_kind": "CANONICAL_SUBJECT", "subject_ref": previous_ref}
    run("ELIGIBILITY_NOT_TRANSFERABLE_TO_OTHER_EXACT_KEY", unbound_key, reason="CURRENT_POLICY_APPLICABILITY")
    run("NONEXCLUDED_WITH_DECISION", lambda r, c: r.update(state="UNKNOWN_SCOPE"), reason="RECORD_GRAMMAR")
    run("NONEXCLUDED_NOT_COVERAGE_APPROVAL", lambda r, c: (r.update(state="UNKNOWN_SCOPE"), r.pop("scope_decision_ref")), expected="NOT_APPLICABLE")
    return results


if __name__ == "__main__":
    print(f"{len(controls())} scope-exclusion design controls PASS")
