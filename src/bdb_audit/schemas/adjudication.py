"""Executable R5.3 contracts for Finding, Root Cause, and Contradiction (M21/M22)."""

REFERENCE_SCHEMA = {
    "type": "object",
    "required": ["kind", "revision_digest", "digest_profile", "schema_revision_ref", "ref_class"],
    "properties": {
        "kind": {"type": "string"},
        "revision_digest": {"type": "string"},
        "digest_profile": {"type": "string"},
        "schema_revision_ref": {"type": "string"},
        "ref_class": {"type": "string"},
    },
    "additionalProperties": True,
}

REFERENCE_ARRAY = {"type": "array", "items": REFERENCE_SCHEMA}
STRING_ARRAY = {"type": "array", "items": {"type": "string"}}

FINDING_CATEGORIES = [
    "SECURITY", "RELIABILITY", "DATA_INTEGRITY", "AVAILABILITY", "PRIVACY",
    "RELEASE_ASSURANCE", "EVIDENCE_QUALITY", "OTHER",
]
FINDING_LIFECYCLE = [
    "OPEN", "CONFIRMED_CURRENT", "REJECTED", "SUPERSEDED",
    "REMEDIATION_PENDING", "STALE_FOR_CURRENT_SOURCE",
    "FIXED_ON_NEW_SOURCE", "PARTIALLY_FIXED", "REOPENED",
]
EPISTEMIC_OUTCOMES = ["SUPPORTED", "REFUTED", "INCONCLUSIVE", "BLOCKED", "NOT_APPLICABLE"]
SEVERITY_VALUES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
CONFIDENCE_VALUES = ["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
ROOT_CAUSE_LIFECYCLE = ["ACTIVE", "SUPERSEDED", "RETIRED"]
CONTRADICTION_LIFECYCLE = ["OPEN", "TESTING", "RESOLVED_SCOPED", "RESOLVED_FULL", "REOPENED", "BLOCKED"]
CONTRADICTION_RESOLUTION_KINDS = [
    "REFUTED", "SCOPES_SEPARATED", "HARNESS_INVALIDATED", "CONTRACT_CHANGED", "BLOCKED",
]
CONTRADICTION_RESOLUTION_RESULTS = ["RESOLVED_SCOPED", "RESOLVED_FULL", "BLOCKED"]


def _object(required, properties):
    return {
        "type": "object",
        "required": list(required),
        "properties": properties,
        "additionalProperties": False,
    }


def adjudication_schema(kind):
    if kind == "finding_claim_revision":
        return _object(
            [
                "finding_id", "finding_claim_revision", "source_generation_ref",
                "claim_statement", "scope_refs", "category", "violated_invariant_refs",
                "discovery_relation_refs", "limitations",
            ],
            {
                "finding_id": {"type": "string"},
                "finding_claim_revision": {"type": "string"},
                "previous_finding_claim_revision_ref": REFERENCE_SCHEMA,
                "source_generation_ref": REFERENCE_SCHEMA,
                "claim_statement": {"type": "string", "minLength": 1},
                "scope_refs": REFERENCE_ARRAY,
                "category": {"enum": FINDING_CATEGORIES},
                "violated_invariant_refs": REFERENCE_ARRAY,
                "discovery_relation_refs": REFERENCE_ARRAY,
                "limitations": STRING_ARRAY,
            },
        )

    if kind == "finding_axis_assessment":
        schema = _object(
            [
                "finding_axis_assessment_id", "claim_revision_ref", "axis",
                "assessment_input_history_cut", "assessment_policy_ref", "scope",
                "evidence_qualification_refs", "method_or_characterization_refs",
                "confidence", "limitations", "reason_codes",
            ],
            {
                "finding_axis_assessment_id": {"type": "string"},
                "claim_revision_ref": REFERENCE_SCHEMA,
                "axis": {"enum": ["SEVERITY", "MECHANISM", "REACHABILITY", "IMPACT"]},
                "assessment_input_history_cut": {"type": "object"},
                "assessment_policy_ref": REFERENCE_SCHEMA,
                "scope": {"type": "object"},
                "evidence_qualification_refs": REFERENCE_ARRAY,
                "epistemic_outcome": {"enum": EPISTEMIC_OUTCOMES},
                "method_or_characterization_refs": REFERENCE_ARRAY,
                "severity_value": {"enum": SEVERITY_VALUES},
                "confidence": {"enum": CONFIDENCE_VALUES},
                "limitations": STRING_ARRAY,
                "reason_codes": STRING_ARRAY,
            },
        )
        schema["allOf"] = [
            {
                "if": {"properties": {"axis": {"const": "SEVERITY"}}, "required": ["axis"]},
                "then": {
                    "required": ["severity_value"],
                    "not": {"required": ["epistemic_outcome"]},
                },
                "else": {
                    "required": ["epistemic_outcome"],
                    "not": {"required": ["severity_value"]},
                },
            }
        ]
        return schema

    if kind == "finding_adjudication_decision":
        return _object(
            [
                "decision_id", "claim_revision_ref", "scope", "mechanism_assessment_ref",
                "reachability_assessment_ref", "impact_assessment_ref", "severity_assessment_ref",
                "finding_lifecycle_status", "evidence_qualification_refs", "knowledge_state_refs",
                "corpus_snapshot_refs", "adjudicator_ref", "input_history_cut", "reason_codes",
            ],
            {
                "decision_id": {"type": "string"},
                "claim_revision_ref": REFERENCE_SCHEMA,
                "previous_adjudication_decision_ref": REFERENCE_SCHEMA,
                "scope": {"type": "object"},
                "mechanism_assessment_ref": REFERENCE_SCHEMA,
                "reachability_assessment_ref": REFERENCE_SCHEMA,
                "impact_assessment_ref": REFERENCE_SCHEMA,
                "severity_assessment_ref": REFERENCE_SCHEMA,
                "finding_lifecycle_status": {"enum": FINDING_LIFECYCLE},
                "evidence_qualification_refs": REFERENCE_ARRAY,
                "knowledge_state_refs": REFERENCE_ARRAY,
                "corpus_snapshot_refs": REFERENCE_ARRAY,
                "adjudicator_ref": REFERENCE_SCHEMA,
                "input_history_cut": {"type": "object"},
                "reason_codes": STRING_ARRAY,
            },
        )

    if kind == "root_cause_revision":
        return _object(
            [
                "root_cause_id", "root_cause_revision", "source_generation_ref",
                "mechanism_statement", "membership_edges", "predecessor_root_cause_refs",
                "scope", "status",
            ],
            {
                "root_cause_id": {"type": "string"},
                "root_cause_revision": {"type": "string"},
                "source_generation_ref": REFERENCE_SCHEMA,
                "mechanism_statement": {"type": "string", "minLength": 1},
                "membership_edges": {
                    "type": "array",
                    "items": _object(
                        ["finding_claim_revision_ref", "relation_role", "scope"],
                        {
                            "finding_claim_revision_ref": REFERENCE_SCHEMA,
                            "relation_role": {"type": "string", "minLength": 1},
                            "scope": {"type": "object"},
                        },
                    ),
                },
                "predecessor_root_cause_refs": REFERENCE_ARRAY,
                "multi_causal_condition": {},
                "scope": {"type": "object"},
                "status": {"enum": ROOT_CAUSE_LIFECYCLE},
            },
        )

    if kind == "contradiction_revision":
        return _object(
            [
                "contradiction_id", "contradiction_revision", "claim_revision_refs", "scope",
                "positions", "supporting_evidence_qualification_refs",
                "opposing_evidence_qualification_refs", "failure_assumption_differences",
                "environment_input_model_differences", "required_falsifier", "status",
            ],
            {
                "contradiction_id": {"type": "string"},
                "contradiction_revision": {"type": "string"},
                "predecessor_contradiction_revision_ref": REFERENCE_SCHEMA,
                "claim_revision_refs": {"type": "array", "minItems": 2, "items": REFERENCE_SCHEMA},
                "scope": {"type": "object"},
                "positions": {"type": "array", "minItems": 2},
                "supporting_evidence_qualification_refs": REFERENCE_ARRAY,
                "opposing_evidence_qualification_refs": REFERENCE_ARRAY,
                "failure_assumption_differences": {"type": "array"},
                "environment_input_model_differences": {"type": "array"},
                "required_falsifier": {},
                "status": {"enum": CONTRADICTION_LIFECYCLE},
                "resolution_decision_ref": REFERENCE_SCHEMA,
            },
        )

    if kind == "contradiction_resolution_decision":
        return _object(
            [
                "resolution_decision_id", "contradiction_prior_revision_ref",
                "resolution_input_history_cut", "resolved_scope", "resolution_kind",
                "basis_refs", "resulting_status",
            ],
            {
                "resolution_decision_id": {"type": "string"},
                "contradiction_prior_revision_ref": REFERENCE_SCHEMA,
                "resolution_input_history_cut": {"type": "object"},
                "resolved_scope": {"type": "object"},
                "resolution_kind": {"enum": CONTRADICTION_RESOLUTION_KINDS},
                "basis_refs": {"type": "array", "minItems": 1, "items": REFERENCE_SCHEMA},
                "resulting_status": {"enum": CONTRADICTION_RESOLUTION_RESULTS},
            },
        )

    return None
