"""Executable field contracts for Finding Adjudication, Root Cause, and Contradiction (M21/M22)."""

FIELDS = {
    "finding_claim_revision": "claim_id claim_revision source_generation_ref statement scope_refs violated_invariant_refs discovery_relation_refs",
    "finding_axis_assessment": "assessment_id claim_revision_ref assessment_input_history_cut assessment_policy_ref axis epistemic_outcome method evidence_qualification_refs",
    "finding_adjudication_decision": "decision_id claim_revision_ref input_history_cut adjudicator_ref mechanism_assessment_ref reachability_assessment_ref impact_assessment_ref severity_assessment_ref lifecycle_status evidence_qualification_refs",
    "root_cause_revision": "root_cause_id root_cause_revision source_generation_ref membership_edges predecessor_root_cause_refs",
    "contradiction_revision": "contradiction_id contradiction_revision claim_revision_ref contradicting_evidence_refs input_history_cut status",
    "contradiction_resolution_decision": "resolution_id contradiction_revision_ref adjudicator_ref resolution_status rationale input_history_cut",
}

OPTIONAL = {
    "finding_claim_revision": ("previous_finding_claim_revision_ref",),
    "finding_axis_assessment": ("method_or_characterization_refs",),
    "finding_adjudication_decision": ("previous_adjudication_decision_ref", "corpus_snapshot_refs", "knowledge_state_refs"),
}

ARRAYS = {
    "scope_refs", "violated_invariant_refs", "discovery_relation_refs",
    "evidence_qualification_refs", "method_or_characterization_refs",
    "corpus_snapshot_refs", "knowledge_state_refs", "membership_edges",
    "predecessor_root_cause_refs", "contradicting_evidence_refs",
}

OBJECTS = {
    "assessment_input_history_cut", "input_history_cut",
}


def adjudication_schema(kind):
    if kind not in FIELDS:
        return None
    fields = FIELDS[kind].split()
    properties = {}
    for name in fields + list(OPTIONAL.get(kind, ())):
        if name in ARRAYS:
            properties[name] = {"type": "array"}
        elif name in OBJECTS:
            properties[name] = {"type": "object"}
        elif name.endswith("_ref"):
            properties[name] = {
                "type": "object",
                "required": ["kind", "revision_digest", "digest_profile", "schema_revision_ref", "ref_class"],
            }
        else:
            properties[name] = {"type": ["string", "number", "object"]}

    if kind == "finding_axis_assessment":
        properties["axis"] = {"enum": ["MECHANISM", "REACHABILITY", "IMPACT", "SEVERITY"]}
        properties["epistemic_outcome"] = {
            "enum": ["SUPPORTED", "REFUTED", "INCONCLUSIVE", "BLOCKED", "NOT_APPLICABLE"]
        }
    elif kind == "finding_adjudication_decision":
        properties["lifecycle_status"] = {
            "enum": [
                "OPEN", "CONFIRMED_CURRENT", "REJECTED", "SUPERSEDED",
                "REMEDIATION_PENDING", "STALE_FOR_CURRENT_SOURCE",
                "FIXED_ON_NEW_SOURCE", "PARTIALLY_FIXED", "REOPENED"
            ]
        }
    elif kind == "contradiction_revision":
        properties["status"] = {
            "enum": [
                "UNRESOLVED", "RESOLVED",
                "OPEN", "TESTING", "RESOLVED_SCOPED", "RESOLVED_FULL", "REOPENED", "BLOCKED"
            ]
        }

    return {
        "type": "object",
        "required": fields,
        "properties": properties,
        "additionalProperties": False,
    }
