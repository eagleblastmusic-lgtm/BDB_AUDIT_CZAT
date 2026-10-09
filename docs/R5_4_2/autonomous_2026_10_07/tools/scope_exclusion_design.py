"""Read-only OD-026 design predicate; snapshots are model assumptions.

This deliberately is not installed authority, replay, or a durable operation.
No production code imports this module. Real acceptance must independently
derive the model's trusted context and prove transaction/crash atomicity.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from execution import BASE, OUT, ROOT, digest, preserve, read, write

# Editable Python installation points at the separate chat checkout on this
# host. Bind this model to the authoritative repository without reinstalling
# packages or altering the other checkout.
sys.path.insert(0, str(ROOT / "src"))
from bdb_audit.core import canonical_json  # noqa: E402

assert Path(canonical_json.__file__).resolve() == (ROOT / "src/bdb_audit/core/canonical_json.py").resolve(), "WRONG_REPOSITORY_IMPORT"


def encoded(value):
    return canonical_json.canonical_bytes(value)


def schema(kind):
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    key = next(v for k, v in mapping.items() if k.split("/")[0] == kind)
    path = OUT / "design/body_grammars" / (key.replace("/", "__") + ".json")
    if not path.exists():
        path = BASE / "candidate/schemas" / (key.replace("/", "__") + ".schema.json")
    return key, path, read(path)


def body_digest(kind, body):
    key, _, _ = schema(kind)
    return hashlib.sha256(("BDB2/" + key).encode("ascii") + b"\0" + encoded(body)).hexdigest()


def exact_ref(kind, body, logical_id):
    _, path, _ = schema(kind)
    return {"kind": kind, **({"logical_id": logical_id} if logical_id is not None else {}), "revision_digest": body_digest(kind, body),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": {"kind": "schema", "revision_digest": digest(path)}}


class Reject(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Reject(reason)


@dataclass
class SnapshotModel:
    # These data are trusted *only inside the finite design model*. Production
    # must resolve exact accepted history and qualified installation itself.
    campaign_id: str
    namespace_ref: dict
    cuts: dict
    facts: dict
    profiles: dict
    requests: dict
    eligible_decisions: set
    permitted_source_manifest_refs: list
    parent_cut: dict

    def cut(self, value):
        require(value.get("campaign_id") == self.campaign_id, "CUT_CAMPAIGN")
        seq = value.get("accepted_head_seq")
        require(type(seq) is int and seq in self.cuts and encoded(self.cuts[seq]) == encoded(value), "CUT_BINDING")
        require(seq <= self.parent_cut["accepted_head_seq"], "FUTURE_CUT")
        return seq

    def resolve(self, reference, at_seq):
        entry = self.facts.get(encoded(reference))
        require(entry is not None, "EXACT_REFERENCE_MISSING")
        require(entry["campaign_id"] == self.campaign_id and entry["namespace_ref"] == self.namespace_ref, "FACT_CONTEXT")
        require(type(entry["accepted_seq"]) is int and 1 <= entry["accepted_seq"] <= at_seq, "PRIOR_ACCEPTANCE")
        body = entry["body"]
        kind = reference["kind"]
        _, path, grammar = schema(kind)
        require(reference["schema_revision_ref"] == {"kind": "schema", "revision_digest": digest(path)}, "SCHEMA_PIN")
        require(Draft202012Validator(grammar).is_valid(body), "BODY_GRAMMAR")
        require(reference["revision_digest"] == body_digest(kind, body), "OBJECT_HASH")
        id_fields = [name for name, rule in grammar.get("properties", {}).items()
                     if rule.get("pattern", "").startswith("^" + kind + "_")]
        require(len(id_fields) <= 1, "AMBIGUOUS_BODY_ID")
        require(reference.get("logical_id") == (body[id_fields[0]] if id_fields else None), "LOGICAL_ID_BODY_BINDING")
        return body

    def profile(self, reference):
        body = self.profiles.get(encoded(reference))
        require(body is not None, "INSTALLATION_PIN")
        require(reference["revision_digest"] == hashlib.sha256(encoded(body)).hexdigest(), "PROFILE_HASH")
        grammar = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")["PRINCIPAL_AUTHORIZATION_V1"]["grammar"]
        require(reference["profile_id"] == "PRINCIPAL_AUTHORIZATION_V2" and Draft202012Validator(grammar).is_valid(body), "AUTHORITY_PROFILE")
        require(body["namespace_profile_ref"] == self.namespace_ref, "AUTHORITY_NAMESPACE")
        return body


def key_for_scope(reference, context, seq):
    body = context.resolve(reference, seq)
    if reference["kind"] == "scope_state_record":
        return body["scope_key"]
    return {"scope_kind": "CANONICAL_SUBJECT", "subject_ref": reference}


def matches_key(reference, key, context, seq):
    context.resolve(reference, seq)
    if key["scope_kind"] == "CANONICAL_SUBJECT" and key["subject_ref"] == reference:
        return True
    return key_for_scope(reference, context, seq) == key


def eligibility_key(decision_ref, record):
    return (encoded(decision_ref), encoded(record["scope_state_input_history_cut"]), encoded(record["scope_key"]))


def typed_order(reference):
    return (reference["kind"], reference.get("logical_id", ""), reference["revision_digest"],
            reference["digest_profile"], encoded(reference["schema_revision_ref"]))


def check_key(key, context, seq):
    if key["scope_kind"] == "CANONICAL_SUBJECT":
        context.resolve(key["subject_ref"], seq)
    else:
        member = key["source_member"]
        manifest_ref = member["source_manifest_ref"]
        manifest = context.resolve(manifest_ref, seq)
        require(manifest_ref in context.permitted_source_manifest_refs, "SOURCE_APPLICABILITY")
        paths = [e["repo_relative_posix_path"] for e in manifest["entries"]]
        require(paths.count(member["member_path"]) == 1, "EXACT_SOURCE_MEMBER")


def authorization(record, context, expected_parent):
    """Return finite authorization result without any mutation capability."""
    try:
        _, _, grammar = schema("scope_state_record")
        require(Draft202012Validator(grammar).is_valid(record), "RECORD_GRAMMAR")
        require(encoded(expected_parent) == encoded(context.parent_cut), "PARENT_CHANGED")
        seq = context.cut(record["scope_state_input_history_cut"])
        check_key(record["scope_key"], context, seq)
        if "scope_ref" in record:
            require(matches_key(record["scope_ref"], record["scope_key"], context, seq), "SCOPE_REF_KEY")
        # General acceptance of nonexcluded records has separate basis/FSM
        # guards. This predicate supplies no coverage or inventory approval.
        if record["state"] != "EXCLUDED_SCOPE":
            return "NOT_APPLICABLE", None
        decision_ref = record["scope_decision_ref"]
        decision = context.resolve(decision_ref, seq)
        require(decision_ref["kind"] == "approval_decision", "DECISION_KIND")
        require(decision["decision_type"] == "SCOPE_EXCLUSION" and decision["decision"] == "APPROVED", "DECISION_PURPOSE_RESULT")
        require(decision["scope"] == sorted(decision["scope"], key=typed_order), "SCOPE_SET_ORDER")
        approval_seq = context.cut(decision["input_history_cut"])
        require(approval_seq < context.facts[encoded(decision_ref)]["accepted_seq"], "APPROVAL_INPUT_PRIOR")
        identity = context.profile(decision["actor_ref"])
        authority = context.profile(decision["actor_authority_ref"])
        require(identity["principal_id"] == authority["principal_id"], "PRINCIPAL_MISMATCH")
        require("APPROVE" in authority["permitted_operations"] and "SCOPE_EXCLUSION" in authority["permitted_approval_purposes"], "AUTHORITY_CLASS")
        request = context.requests.get(encoded(decision_ref))
        require(request is not None and request["principal_id"] == identity["principal_id"], "AUTHENTICATED_REQUEST")
        require(request["actor_ref"] == decision["actor_ref"] and request["authority_ref"] == decision["actor_authority_ref"], "AUTHENTICATED_PINS")
        require(request["action"] == decision["requested_action"] and request["scope"] == decision["scope"], "AUTHENTICATED_ACTION_SCOPE")
        approved = False
        for reference in decision["scope"]:
            key = key_for_scope(reference, context, approval_seq)
            check_key(key, context, approval_seq)
            approved |= matches_key(reference, record["scope_key"], context, approval_seq)
        require(approved, "EXACT_APPROVED_SCOPE")
        require(eligibility_key(decision_ref, record) in context.eligible_decisions, "CURRENT_POLICY_APPLICABILITY")
        return "ALLOW", None
    except Reject as error:
        return "REJECT", str(error)


def main():
    preserve()
    from test_scope_exclusion_design import controls
    results = controls()
    sources = [ROOT / "F1_QUALIFICATION/inputs/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md",
               BASE / "candidate/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md"]
    write("design/SCOPE_EXCLUSION_DESIGN_CONTROLS.json", {
        "decision": "OD-026", "controls": results,
        "source_digests": {p.relative_to(ROOT).as_posix(): digest(p) for p in sources},
        "implementation_dependencies": {p.relative_to(ROOT).as_posix(): digest(p) for p in [ROOT / "src/bdb_audit/core/canonical_json.py", ROOT / "src/bdb_audit/core/errors.py"]},
        "model_assumptions": ["trusted accepted-history snapshots", "qualified installation profiles", "authenticated human request", "independently derived current policy/source eligibility"],
        "qualification": False, "canonical_runtime": "NOT_RUN", "durable_reject_atomicity": "NOT_PROVEN",
        "semantic_review": "NARROW_AUTHORIZATION_DESIGN; FULL_PER_KIND_PARITY_PENDING"})
    print(f"Scope-exclusion finite design controls PASS: {len(results)}; runtime/durable atomicity NOT_PROVEN")


if __name__ == "__main__":
    main()
