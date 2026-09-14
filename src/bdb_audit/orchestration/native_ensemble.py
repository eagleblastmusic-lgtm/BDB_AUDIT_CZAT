"""Native E1 Discovery Ensemble and R5.3 E2 Convergence/Adjudication orchestration."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from .stages import StageSpec
from .runs import LaneSpec
from ..adjudication.models import (
    FINDING_CATEGORIES,
    SEVERITY_VALUES,
    FindingClaimRevision,
    FindingAxisAssessment,
    FindingAdjudicationDecision,
    RootCauseRevision,
    ContradictionRevision,
    _ref_dict,
)
from ..adjudication.engine import adjudicate_finding, cluster_findings_into_root_cause

# 5 Mandatory E1 Discovery Lanes (R5.3 §27)
E1_LANE_SLOTS = ("E1-A", "E1-B", "E1-C", "E1-D", "E1-E")

E1_LANE_STRATEGIES = {
    "E1-A": ("General Systems & Architecture", "STRUCTURAL_ENUMERATION"),
    "E1-B": ("Security, Trust & Authority", "AUTHORITY_BOUNDARY_ANALYSIS"),
    "E1-C": ("State, Persistence & Recovery", "STATE_MUTATION_TRACE"),
    "E1-D": ("Data, Catalog & Parsing", "INPUT_PARSER_DIFFERENTIAL"),
    "E1-E": ("Concurrency, Resources & Oracles", "INTERACTION_CONCURRENCY_ANALYSIS"),
}


def build_e1_stage_spec(revision: str = "1") -> StageSpec:
    """Construct normative E1 StageSpec (R5.3 §27)."""
    return StageSpec(
        stage_key="E1",
        stage_spec_revision=revision,
        stage_role="DISCOVERY_ENSEMBLE",
        stage_ordinal=1,
        purpose="Independent multi-lane discovery ensemble across architectural dimensions",
        required_lane_slots=E1_LANE_SLOTS,
        blind_reveal_phase_model="CONTROLLED",
        required_stage_completion_outputs=("discovery_records", "stage_completion_digest"),
        stop_e6_relationship="CONTINUE_REQUIRED",
    )


def build_e1_lane_specs(stage_spec_revision: str = "1", lane_revision: str = "1") -> dict[str, LaneSpec]:
    """Construct normative LaneSpecs for all 5 E1 lanes with enforced isolation."""
    specs = {}
    for slot in E1_LANE_SLOTS:
        purpose, strategy = E1_LANE_STRATEGIES[slot]
        specs[slot] = LaneSpec(
            lane_key=slot,
            lane_spec_revision=lane_revision,
            stage_spec_revision=stage_spec_revision,
            purpose=purpose,
            primary_strategy=strategy,
            required_isolation_assurance="ENFORCED",
            forbidden_knowledge_classes=("OTHER_LANE_UNSEALED_FINDINGS", "FUTURE_ADJUDICATION_OUTCOMES"),
            required_outputs=("discovery_records",),
        )
    return specs


def build_e2_stage_spec(revision: str = "1") -> StageSpec:
    """Construct normative E2 StageSpec (R5.3 §71)."""
    return StageSpec(
        stage_key="E2",
        stage_spec_revision=revision,
        stage_role="CONVERGENCE_AND_ADJUDICATION",
        stage_ordinal=2,
        purpose=(
            "Claim quarantine, individual four-axis adjudication, then root-cause normalization "
            "and contradiction obligations"
        ),
        predecessor_requirements=("E1",),
        required_lane_slots=("E2-CONVERGENCE", "E2-ADJUDICATION"),
        blind_reveal_phase_model="CONTROLLED",
        required_stage_completion_outputs=(
            "finding_claim_revisions",
            "finding_axis_assessments",
            "adjudication_decisions",
            "root_cause_revisions",
            "contradiction_obligations",
        ),
        stop_e6_relationship="CONTINUE_REQUIRED",
    )


class EnsembleQuarantineBroker:
    """Enforce knowledge isolation and prevent cross-lane contamination in E1."""

    def __init__(self):
        self._sealed_findings: dict[str, list[dict]] = {slot: [] for slot in E1_LANE_SLOTS}
        self._is_checkpoint_released: bool = False

    def record_lane_discovery(self, lane_slot: str, discovery: dict) -> None:
        if lane_slot not in E1_LANE_SLOTS:
            raise ValidationError("UNKNOWN_LANE_SLOT", f"Invalid lane slot: {lane_slot}")
        if self._is_checkpoint_released:
            raise ValidationError("CHECKPOINT_ALREADY_SEALED", "Cannot add discoveries after checkpoint seal")
        self._sealed_findings[lane_slot].append(dict(discovery))

    def get_lane_view(self, requesting_lane: str) -> list[dict]:
        if requesting_lane not in E1_LANE_SLOTS:
            raise ValidationError("UNKNOWN_LANE_SLOT", requesting_lane)
        return list(self._sealed_findings[requesting_lane])

    def query_cross_lane_findings(self, requesting_lane: str, target_lane: str) -> list[dict]:
        if not self._is_checkpoint_released and requesting_lane != target_lane:
            raise ValidationError(
                "CROSS_LANE_KNOWLEDGE_LEAKAGE",
                f"Lane {requesting_lane} cannot access unsealed findings of {target_lane}",
            )
        return list(self._sealed_findings[target_lane])

    def release_checkpoint_for_e2(self) -> dict[str, list[dict]]:
        self._is_checkpoint_released = True
        return {slot: list(findings) for slot, findings in self._sealed_findings.items()}


@dataclass(frozen=True)
class E1CompletionResult:
    stage_key: str
    stage_spec_digest: str
    completed_lanes: tuple[str, ...]
    total_discoveries: int
    discoveries_by_lane: dict[str, list[dict]]
    completion_digest: str
    quarantined_claims: tuple[dict, ...]

    def as_dict(self) -> dict:
        return {
            "stage_key": self.stage_key,
            "stage_spec_digest": self.stage_spec_digest,
            "completed_lanes": list(self.completed_lanes),
            "total_discoveries": self.total_discoveries,
            "completion_digest": self.completion_digest,
            "quarantined_claims_count": len(self.quarantined_claims),
        }


def execute_e1_ensemble(
    source_generation_ref: Any,
    lane_discoveries: Mapping[str, Sequence[dict]],
    stage_spec: StageSpec | None = None,
) -> E1CompletionResult:
    """Execute E1 and bind the exact quarantined discovery content."""
    spec = stage_spec or build_e1_stage_spec()
    reported_lanes = set(lane_discoveries.keys())
    missing = set(spec.required_lane_slots) - reported_lanes
    if missing:
        raise ValidationError(
            "MANDATORY_LANE_MISSING",
            f"Missing required E1 discovery lanes: {sorted(missing)}",
        )

    broker = EnsembleQuarantineBroker()
    all_quarantined_claims: list[dict] = []
    total_count = 0
    for slot in sorted(spec.required_lane_slots):
        for discovery in lane_discoveries.get(slot, []):
            broker.record_lane_discovery(slot, discovery)
            claim_data = dict(discovery)
            claim_data["originating_lane"] = slot
            all_quarantined_claims.append(claim_data)
            total_count += 1

    released = broker.release_checkpoint_for_e2()
    completion_body = {
        "stage_key": "E1",
        "stage_spec_digest": spec.revision_digest,
        "completed_lanes": sorted(spec.required_lane_slots),
        "source_generation_ref": _ref_dict(source_generation_ref),
        "total_discoveries": total_count,
        "quarantined_claims": sorted(all_quarantined_claims, key=canonical_bytes),
    }
    completion_digest = hashlib.sha256(canonical_bytes(completion_body)).hexdigest()
    return E1CompletionResult(
        stage_key="E1",
        stage_spec_digest=spec.revision_digest,
        completed_lanes=tuple(sorted(spec.required_lane_slots)),
        total_discoveries=total_count,
        discoveries_by_lane=released,
        completion_digest=completion_digest,
        quarantined_claims=tuple(all_quarantined_claims),
    )


@dataclass(frozen=True)
class E2CompletionResult:
    stage_key: str
    e1_completion_digest: str
    finding_claim_revisions: tuple[FindingClaimRevision, ...]
    axis_assessments: tuple[FindingAxisAssessment, ...]
    adjudicated_decisions: tuple[FindingAdjudicationDecision, ...]
    root_cause_revisions: tuple[RootCauseRevision, ...]
    contradiction_revisions: tuple[ContradictionRevision, ...]
    completion_digest: str

    def as_dict(self) -> dict:
        return {
            "stage_key": self.stage_key,
            "e1_completion_digest": self.e1_completion_digest,
            "finding_claim_revisions_count": len(self.finding_claim_revisions),
            "axis_assessments_count": len(self.axis_assessments),
            "adjudicated_decisions_count": len(self.adjudicated_decisions),
            "root_cause_revisions_count": len(self.root_cause_revisions),
            "contradictions_count": len(self.contradiction_revisions),
            "completion_digest": self.completion_digest,
        }


def validate_stage_transition(
    predecessor_completion: E1CompletionResult | dict,
    target_stage_spec: StageSpec,
) -> None:
    pred_stage = (
        predecessor_completion.stage_key
        if isinstance(predecessor_completion, E1CompletionResult)
        else predecessor_completion.get("stage_key")
    )
    if pred_stage not in target_stage_spec.predecessor_requirements:
        raise ValidationError(
            "STAGE_TRANSITION_GATED",
            f"Predecessor stage {pred_stage} does not satisfy requirements {target_stage_spec.predecessor_requirements}",
        )


def _typed_refs(value: Any, *, expected_kind: str | None = None) -> list[dict[str, Any]]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    required = {"kind", "revision_digest", "digest_profile", "schema_revision_ref", "ref_class"}
    refs: dict[bytes, dict[str, Any]] = {}
    for item in values:
        if not isinstance(item, Mapping) or not required.issubset(item):
            continue
        ref = dict(item)
        if expected_kind is not None and ref.get("kind") != expected_kind:
            continue
        refs[canonical_bytes(ref)] = ref
    return [refs[key] for key in sorted(refs)]


def _generic_evidence(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = _typed_refs(item.get("evidence_ref"), expected_kind="evidence_qualification_assessment")
    refs.extend(_typed_refs(item.get("evidence_refs"), expected_kind="evidence_qualification_assessment"))
    return _unique_refs(refs)


def _axis_evidence(item: Mapping[str, Any], axis: str) -> list[dict[str, Any]]:
    raw = item.get("axis_evidence_refs")
    if not isinstance(raw, Mapping):
        return []
    return _typed_refs(raw.get(axis), expected_kind="evidence_qualification_assessment")


def _axis_method_refs(item: Mapping[str, Any], axis: str) -> list[dict[str, Any]]:
    raw = item.get("axis_method_refs") or item.get("method_or_characterization_refs")
    if isinstance(raw, Mapping):
        return _typed_refs(raw.get(axis))
    return _typed_refs(raw)


def _unique_refs(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    refs = {canonical_bytes(dict(value)): dict(value) for value in values}
    return [refs[key] for key in sorted(refs)]


def _unique_values(values: Sequence[Any]) -> list[Any]:
    keyed = {canonical_bytes(value): value for value in values}
    return [keyed[key] for key in sorted(keyed)]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    return sorted({str(item) for item in values if str(item)}, key=lambda text: text.encode("utf-8"))


def _claim_statement(item: Mapping[str, Any]) -> str:
    statement = str(item.get("claim_statement") or item.get("statement") or "").strip()
    if not statement:
        raise ValidationError("E2_FINDING_CLAIM_STATEMENT_REQUIRED")
    return statement


def _claim_category(item: Mapping[str, Any]) -> str:
    raw = item.get("category")
    if raw is None:
        return "OTHER"
    category = str(raw).upper()
    if category not in FINDING_CATEGORIES:
        raise ValidationError("INVALID_FINDING_CATEGORY", category)
    return category


def _finding_scope(item: Mapping[str, Any]) -> dict[str, Any]:
    raw = item.get("finding_scope")
    if raw is None:
        raw = item.get("scope")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _axis_scope(item: Mapping[str, Any], axis: str) -> dict[str, Any]:
    raw = item.get("axis_scopes")
    if isinstance(raw, Mapping) and isinstance(raw.get(axis), Mapping):
        return dict(raw[axis])
    return _finding_scope(item)


def _axis_confidence(item: Mapping[str, Any], axis: str) -> str:
    raw = item.get("axis_confidence")
    value = raw.get(axis) if isinstance(raw, Mapping) else None
    if value is None and axis == "SEVERITY":
        value = item.get("severity_confidence")
    return str(value or "UNKNOWN").upper()


def _axis_reason_codes(item: Mapping[str, Any], axis: str) -> list[str]:
    raw = item.get("axis_reason_codes")
    values = raw.get(axis) if isinstance(raw, Mapping) else None
    return _string_list(values)


def _operational_axis_outcome(
    item: Mapping[str, Any],
    axis: str,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    raw = item.get("axis_outcomes")
    outcome = raw.get(axis) if isinstance(raw, Mapping) else None
    outcome = str(outcome).upper() if outcome is not None else None
    evidence = _axis_evidence(item, axis)
    reasons = _axis_reason_codes(item, axis)
    valid = {"SUPPORTED", "REFUTED", "INCONCLUSIVE", "BLOCKED", "NOT_APPLICABLE"}
    if outcome not in valid:
        return "INCONCLUSIVE", evidence, _string_list([*reasons, "E2_AXIS_UNASSESSED"])
    if outcome in {"SUPPORTED", "REFUTED"} and not evidence:
        return "INCONCLUSIVE", evidence, _string_list([*reasons, "E2_AXIS_EVIDENCE_REQUIRED"])
    return outcome, evidence, reasons


def _severity_value(item: Mapping[str, Any]) -> str:
    raw = item.get("severity_value") or item.get("severity")
    if raw is None:
        axis_values = item.get("axis_values")
        if isinstance(axis_values, Mapping):
            raw = axis_values.get("SEVERITY")
    severity = str(raw or "").upper()
    if severity not in SEVERITY_VALUES:
        raise ValidationError(
            "E2_SEVERITY_ASSESSMENT_REQUIRED",
            "Each quarantined finding requires an explicit CRITICAL/HIGH/MEDIUM/LOW/INFO severity assessment",
        )
    return severity


def _normalization_key(item: Mapping[str, Any]) -> bytes | None:
    """Return only an explicit/stable relation key; statement text is never a merge key."""
    root = item.get("root_cause_ref")
    if _typed_refs(root, expected_kind="root_cause_revision"):
        return canonical_bytes({"root_cause_ref": _typed_refs(root, expected_kind="root_cause_revision")[0]})

    invariant_refs = _typed_refs(item.get("invariant_ref") or item.get("violated_invariant_ref"))
    component = item.get("affected_component")
    location = item.get("source_location") or item.get("location")
    if invariant_refs and component and location:
        return canonical_bytes(
            {
                "invariant_ref": invariant_refs[0],
                "affected_component": str(component),
                "source_location": location,
            }
        )
    return None


def _claim_outcome_with_evidence(item: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    outcome = str(item.get("claim_outcome") or "").upper()
    evidence = _generic_evidence(item)
    if outcome not in {"SUPPORTED", "REFUTED"} or not evidence:
        return "INCONCLUSIVE", evidence
    return outcome, evidence


def _common_mapping(items: Sequence[Mapping[str, Any]], field_name: str) -> dict[str, Any]:
    candidates = [dict(item[field_name]) for item in items if isinstance(item.get(field_name), Mapping)]
    if not candidates:
        return {}
    first = canonical_bytes(candidates[0])
    if any(canonical_bytes(candidate) != first for candidate in candidates[1:]):
        raise ValidationError("E2_NORMALIZATION_SCOPE_CONFLICT", field_name)
    return candidates[0]


def _root_cause_statement(items: Sequence[Mapping[str, Any]]) -> str | None:
    statements = sorted(
        {str(item.get("root_cause_statement") or "").strip() for item in items if str(item.get("root_cause_statement") or "").strip()},
        key=lambda text: text.encode("utf-8"),
    )
    if not statements:
        return None
    if len(statements) != 1:
        raise ValidationError("E2_ROOT_CAUSE_MECHANISM_CONFLICT")
    return statements[0]


def _required_falsifier(items: Sequence[Mapping[str, Any]]) -> Any:
    values = [item.get("required_falsifier") for item in items if item.get("required_falsifier") is not None]
    unique = _unique_values(values)
    if len(unique) > 1:
        raise ValidationError("E2_CONTRADICTION_FALSIFIER_CONFLICT")
    if unique:
        return unique[0]
    return {
        "requirement": "QUALIFIED_FALSIFIER_FOR_EXACT_CONTRADICTORY_CLAIM_REVISIONS",
        "generated_by": "E2_CONTRADICTION_ENGINE",
    }


def _deterministic_object_id(kind: str, *parts: Any) -> str:
    normalized_parts = [
        {"__bdb_bytes_hex__": part.hex()} if isinstance(part, bytes) else part
        for part in parts
    ]
    return deterministic_id(kind, canonical_bytes(normalized_parts))


@dataclass(frozen=True)
class _AdjudicatedCandidate:
    raw: dict[str, Any]
    claim: FindingClaimRevision
    axes: tuple[FindingAxisAssessment, FindingAxisAssessment, FindingAxisAssessment, FindingAxisAssessment]
    decision: FindingAdjudicationDecision
    normalization_key: bytes | None


def _adjudicate_candidate(
    raw_claim: Mapping[str, Any],
    *,
    source_generation_ref: Any,
    adjudicator_ref: Any,
    input_history_cut: Mapping[str, Any],
    policy_ref: Any,
    e1_completion_digest: str,
) -> _AdjudicatedCandidate:
    item = dict(raw_claim)
    seed = {
        "e1_completion_digest": e1_completion_digest,
        "source_generation_ref": _ref_dict(source_generation_ref),
        "raw_discovery": item,
    }
    finding_id = _deterministic_object_id("finding_claim_revision", seed)
    claim = FindingClaimRevision(
        finding_id=finding_id,
        finding_claim_revision=str(item.get("finding_claim_revision") or "1"),
        claim_statement=_claim_statement(item),
        source_generation_ref=_ref_dict(source_generation_ref),
        category=_claim_category(item),
        scope_refs=_typed_refs(item.get("scope_ref") or item.get("scope_refs")),
        violated_invariant_refs=_typed_refs(
            item.get("invariant_ref") or item.get("violated_invariant_ref") or item.get("violated_invariant_refs")
        ),
        discovery_relation_refs=_typed_refs(item.get("discovery_relation_ref") or item.get("discovery_relation_refs")),
        limitations=_string_list(item.get("limitations")),
    )
    claim_ref = claim.as_object().as_ref().as_dict()

    axes: dict[str, FindingAxisAssessment] = {}
    all_evidence: list[dict[str, Any]] = []
    for axis in ("MECHANISM", "REACHABILITY", "IMPACT"):
        outcome, evidence, reasons = _operational_axis_outcome(item, axis)
        all_evidence.extend(evidence)
        axes[axis] = FindingAxisAssessment(
            finding_axis_assessment_id=_deterministic_object_id(
                "finding_axis_assessment", claim.digest, axis, input_history_cut, policy_ref
            ),
            claim_revision_ref=claim_ref,
            assessment_input_history_cut=dict(input_history_cut),
            assessment_policy_ref=_ref_dict(policy_ref),
            axis=axis,
            scope=_axis_scope(item, axis),
            evidence_qualification_refs=evidence,
            epistemic_outcome=outcome,
            method_or_characterization_refs=_axis_method_refs(item, axis),
            confidence=_axis_confidence(item, axis),
            limitations=_string_list(item.get("axis_limitations", {}).get(axis) if isinstance(item.get("axis_limitations"), Mapping) else None),
            reason_codes=reasons,
        )

    severity_evidence = _axis_evidence(item, "SEVERITY")
    all_evidence.extend(severity_evidence)
    axes["SEVERITY"] = FindingAxisAssessment(
        finding_axis_assessment_id=_deterministic_object_id(
            "finding_axis_assessment", claim.digest, "SEVERITY", input_history_cut, policy_ref
        ),
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=dict(input_history_cut),
        assessment_policy_ref=_ref_dict(policy_ref),
        axis="SEVERITY",
        scope=_axis_scope(item, "SEVERITY"),
        evidence_qualification_refs=severity_evidence,
        method_or_characterization_refs=_axis_method_refs(item, "SEVERITY"),
        severity_value=_severity_value(item),
        confidence=_axis_confidence(item, "SEVERITY"),
        limitations=_string_list(item.get("axis_limitations", {}).get("SEVERITY") if isinstance(item.get("axis_limitations"), Mapping) else None),
        reason_codes=_axis_reason_codes(item, "SEVERITY"),
    )

    decision = adjudicate_finding(
        claim=claim,
        mechanism=axes["MECHANISM"],
        reachability=axes["REACHABILITY"],
        impact=axes["IMPACT"],
        severity=axes["SEVERITY"],
        adjudicator_ref=_ref_dict(adjudicator_ref),
        input_history_cut=dict(input_history_cut),
        evidence_refs=_unique_refs(all_evidence),
        scope=_finding_scope(item),
        reason_codes=(
            ("E2_INDIVIDUAL_ADJUDICATION_INCOMPLETE",)
            if any(axes[name].epistemic_outcome not in {"SUPPORTED", "REFUTED"} for name in ("MECHANISM", "REACHABILITY", "IMPACT"))
            else ()
        ),
    )
    decision = replace(
        decision,
        decision_id=_deterministic_object_id(
            "finding_adjudication_decision",
            claim.digest,
            axes["MECHANISM"].digest,
            axes["REACHABILITY"].digest,
            axes["IMPACT"].digest,
            axes["SEVERITY"].digest,
            input_history_cut,
            adjudicator_ref,
        ),
    )
    return _AdjudicatedCandidate(
        raw=item,
        claim=claim,
        axes=(axes["MECHANISM"], axes["REACHABILITY"], axes["IMPACT"], axes["SEVERITY"]),
        decision=decision,
        normalization_key=_normalization_key(item),
    )


def _normalize_root_causes(
    groups: Mapping[bytes, Sequence[_AdjudicatedCandidate]],
    *,
    source_generation_ref: Any,
) -> list[RootCauseRevision]:
    revisions: list[RootCauseRevision] = []
    for group_key in sorted(groups):
        candidates = list(groups[group_key])
        mechanism_statement = _root_cause_statement([candidate.raw for candidate in candidates])
        if mechanism_statement is None:
            continue
        membership_edges = []
        predecessor_refs: list[dict[str, Any]] = []
        for candidate in candidates:
            membership_edges.append(
                {
                    "finding_claim_revision_ref": candidate.claim.as_object().as_ref().as_dict(),
                    "relation_role": str(candidate.raw.get("root_cause_relation_role") or "CONTRIBUTING"),
                    "scope": (
                        dict(candidate.raw["root_cause_membership_scope"])
                        if isinstance(candidate.raw.get("root_cause_membership_scope"), Mapping)
                        else _finding_scope(candidate.raw)
                    ),
                }
            )
            predecessor_refs.extend(
                _typed_refs(candidate.raw.get("root_cause_ref"), expected_kind="root_cause_revision")
            )
        revision = cluster_findings_into_root_cause(
            source_generation_ref=_ref_dict(source_generation_ref),
            mechanism_statement=mechanism_statement,
            membership_edges=membership_edges,
            predecessor_root_cause_refs=_unique_refs(predecessor_refs),
            scope=_common_mapping([candidate.raw for candidate in candidates], "root_cause_scope"),
            multi_causal_condition=(
                candidates[0].raw.get("multi_causal_condition")
                if all(
                    canonical_bytes(candidate.raw.get("multi_causal_condition"))
                    == canonical_bytes(candidates[0].raw.get("multi_causal_condition"))
                    for candidate in candidates
                )
                else None
            ),
        )
        revision = replace(
            revision,
            root_cause_id=_deterministic_object_id(
                "root_cause_revision",
                group_key,
                [candidate.claim.digest for candidate in candidates],
                mechanism_statement,
            ),
        )
        revisions.append(revision)
    return revisions


def _build_contradictions(
    groups: Mapping[bytes, Sequence[_AdjudicatedCandidate]],
) -> list[ContradictionRevision]:
    contradictions: list[ContradictionRevision] = []
    for group_key in sorted(groups):
        candidates = list(groups[group_key])
        supported: list[tuple[_AdjudicatedCandidate, list[dict[str, Any]]]] = []
        refuted: list[tuple[_AdjudicatedCandidate, list[dict[str, Any]]]] = []
        for candidate in candidates:
            outcome, evidence = _claim_outcome_with_evidence(candidate.raw)
            if outcome == "SUPPORTED":
                supported.append((candidate, evidence))
            elif outcome == "REFUTED":
                refuted.append((candidate, evidence))
        if not supported or not refuted:
            continue

        contradictory = [*supported, *refuted]
        claim_refs = [candidate.claim.as_object().as_ref().as_dict() for candidate, _ in contradictory]
        positions = [
            {
                "claim_revision_ref": candidate.claim.as_object().as_ref().as_dict(),
                "position": "SUPPORTED" if (candidate, evidence) in supported else "REFUTED",
            }
            for candidate, evidence in contradictory
        ]
        supporting_evidence = _unique_refs([ref for _, refs in supported for ref in refs])
        opposing_evidence = _unique_refs([ref for _, refs in refuted for ref in refs])
        raw_items = [candidate.raw for candidate, _ in contradictory]
        failure_differences = _unique_values(
            [
                value
                for item in raw_items
                for value in (item.get("failure_assumption_differences") or [])
            ]
        )
        environment_differences = _unique_values(
            [
                value
                for item in raw_items
                for value in (item.get("environment_input_model_differences") or [])
            ]
        )
        contradiction = ContradictionRevision(
            contradiction_id=_deterministic_object_id(
                "contradiction_revision",
                group_key,
                [ref["revision_digest"] for ref in claim_refs],
            ),
            contradiction_revision="1",
            claim_revision_refs=claim_refs,
            scope=_common_mapping(raw_items, "contradiction_scope"),
            positions=positions,
            supporting_evidence_qualification_refs=supporting_evidence,
            opposing_evidence_qualification_refs=opposing_evidence,
            failure_assumption_differences=failure_differences,
            environment_input_model_differences=environment_differences,
            required_falsifier=_required_falsifier(raw_items),
            status="OPEN",
        )
        contradictions.append(contradiction)
    return contradictions


def execute_e2_convergence(
    e1_completion: E1CompletionResult,
    source_generation_ref: Any,
    adjudicator_ref: Any,
    input_history_cut: Mapping[str, Any],
    policy_ref: Any,
) -> E2CompletionResult:
    """Run R5.3 E2 in the required order: individual adjudication, then normalization.

    Every quarantined E1 discovery becomes its own evidence-free claim revision
    and four exact axis assessments. Statement similarity is never a merge key.
    Only after those individual decisions exist may E2 derive Root Cause or
    Contradiction relations from explicit stable relation inputs.
    """
    e2_spec = build_e2_stage_spec()
    validate_stage_transition(e1_completion, e2_spec)

    candidates = [
        _adjudicate_candidate(
            raw_claim,
            source_generation_ref=source_generation_ref,
            adjudicator_ref=adjudicator_ref,
            input_history_cut=input_history_cut,
            policy_ref=policy_ref,
            e1_completion_digest=e1_completion.completion_digest,
        )
        for raw_claim in sorted(e1_completion.quarantined_claims, key=canonical_bytes)
    ]

    normalization_groups: dict[bytes, list[_AdjudicatedCandidate]] = {}
    for candidate in candidates:
        if candidate.normalization_key is not None:
            normalization_groups.setdefault(candidate.normalization_key, []).append(candidate)

    root_causes = _normalize_root_causes(normalization_groups, source_generation_ref=source_generation_ref)
    contradictions = _build_contradictions(normalization_groups)

    claims = [candidate.claim for candidate in candidates]
    axes = [axis for candidate in candidates for axis in candidate.axes]
    decisions = [candidate.decision for candidate in candidates]
    e2_body = {
        "stage_key": "E2",
        "stage_spec_digest": e2_spec.revision_digest,
        "e1_completion_digest": e1_completion.completion_digest,
        "finding_claim_revision_digests": sorted(claim.digest for claim in claims),
        "axis_assessment_digests": sorted(axis.digest for axis in axes),
        "adjudication_decision_digests": sorted(decision.digest for decision in decisions),
        "root_cause_revision_digests": sorted(revision.digest for revision in root_causes),
        "contradiction_digests": sorted(contradiction.digest for contradiction in contradictions),
    }
    e2_digest = hashlib.sha256(canonical_bytes(e2_body)).hexdigest()
    return E2CompletionResult(
        stage_key="E2",
        e1_completion_digest=e1_completion.completion_digest,
        finding_claim_revisions=tuple(claims),
        axis_assessments=tuple(axes),
        adjudicated_decisions=tuple(decisions),
        root_cause_revisions=tuple(root_causes),
        contradiction_revisions=tuple(contradictions),
        completion_digest=e2_digest,
    )
