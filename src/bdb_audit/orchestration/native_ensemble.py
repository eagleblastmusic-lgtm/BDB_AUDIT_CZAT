"""Native E1 Discovery Ensemble and E2 Convergence/Adjudication Orchestration (WP-F4-09)."""
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
import hashlib

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import object_digest
from ..core.ids import deterministic_id, new_id
from ..history.objects import CanonicalObject, ObjectRef
from .stages import StageSpec
from .runs import LaneSpec, Attempt
from ..adjudication.models import (
    FindingClaimRevision,
    FindingAxisAssessment,
    FindingAdjudicationDecision,
    ContradictionRevision,
    _ref_dict,
)
from ..adjudication.engine import adjudicate_finding

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
    """Construct normative E2 StageSpec (R5.3 §28)."""
    return StageSpec(
        stage_key="E2",
        stage_spec_revision=revision,
        stage_role="CONVERGENCE_AND_ADJUDICATION",
        stage_ordinal=2,
        purpose="Quarantine claim deduplication, 4-axis finding adjudication, and contradiction obligations",
        predecessor_requirements=("E1",),
        required_lane_slots=("E2-CONVERGENCE", "E2-ADJUDICATION"),
        blind_reveal_phase_model="CONTROLLED",
        required_stage_completion_outputs=("adjudication_decisions", "contradiction_obligations"),
        stop_e6_relationship="CONTINUE_REQUIRED",
    )


class EnsembleQuarantineBroker:
    """Enforces knowledge isolation and prevents cross-lane contamination in E1 discovery."""

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
        """A lane can ONLY see its own findings prior to checkpoint release."""
        if requesting_lane not in E1_LANE_SLOTS:
            raise ValidationError("UNKNOWN_LANE_SLOT", requesting_lane)
        return list(self._sealed_findings[requesting_lane])

    def query_cross_lane_findings(self, requesting_lane: str, target_lane: str) -> list[dict]:
        """Adversarial check: requesting another lane's unreleased findings must fail closed."""
        if not self._is_checkpoint_released and requesting_lane != target_lane:
            raise ValidationError(
                "CROSS_LANE_KNOWLEDGE_LEAKAGE",
                f"Lane {requesting_lane} cannot access unsealed findings of {target_lane}",
            )
        return list(self._sealed_findings[target_lane])

    def release_checkpoint_for_e2(self) -> dict[str, list[dict]]:
        """Seal E1 discoveries and release them to E2 convergence."""
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
    """Execute E1 discovery ensemble and produce validated E1CompletionResult.

    Fails closed if any of the 5 mandatory lanes (E1-A..E1-E) is missing.
    """
    spec = stage_spec or build_e1_stage_spec()

    # Check all mandatory lanes are reported
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
        disc_list = lane_discoveries.get(slot, [])
        for d in disc_list:
            broker.record_lane_discovery(slot, d)
            claim_data = dict(d)
            claim_data["originating_lane"] = slot
            all_quarantined_claims.append(claim_data)
            total_count += 1

    released = broker.release_checkpoint_for_e2()

    # Bind the exact quarantined content, not merely its count.  This makes the
    # library-level checkpoint change when the evidence-bearing discovery set
    # changes even if lane/count summaries remain constant.
    completion_body = {
        "stage_key": "E1",
        "stage_spec_digest": spec.revision_digest,
        "completed_lanes": sorted(spec.required_lane_slots),
        "source_generation_ref": _ref_dict(source_generation_ref),
        "total_discoveries": total_count,
        "quarantined_claims": sorted(
            all_quarantined_claims,
            key=lambda item: canonical_bytes(item),
        ),
    }
    comp_digest = hashlib.sha256(canonical_bytes(completion_body)).hexdigest()

    return E1CompletionResult(
        stage_key="E1",
        stage_spec_digest=spec.revision_digest,
        completed_lanes=tuple(sorted(spec.required_lane_slots)),
        total_discoveries=total_count,
        discoveries_by_lane=released,
        completion_digest=comp_digest,
        quarantined_claims=tuple(all_quarantined_claims),
    )


@dataclass(frozen=True)
class E2CompletionResult:
    stage_key: str
    e1_completion_digest: str
    adjudicated_decisions: tuple[FindingAdjudicationDecision, ...]
    contradiction_revisions: tuple[ContradictionRevision, ...]
    completion_digest: str

    def as_dict(self) -> dict:
        return {
            "stage_key": self.stage_key,
            "e1_completion_digest": self.e1_completion_digest,
            "adjudicated_decisions_count": len(self.adjudicated_decisions),
            "contradictions_count": len(self.contradiction_revisions),
            "completion_digest": self.completion_digest,
        }


def validate_stage_transition(
    predecessor_completion: E1CompletionResult | dict,
    target_stage_spec: StageSpec,
) -> None:
    """Validate stage transition gating from predecessor to target stage."""
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


def _typed_evidence_refs(value: Any) -> list[dict]:
    """Return only complete typed evidence refs; incomplete labels are not evidence."""
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    refs: list[dict] = []
    required = {"kind", "revision_digest", "digest_profile", "schema_revision_ref"}
    for item in values:
        if isinstance(item, dict) and required.issubset(item):
            refs.append(dict(item))
    return refs


def _generic_evidence(item: Mapping[str, Any]) -> list[dict]:
    refs = _typed_evidence_refs(item.get("evidence_ref"))
    refs.extend(_typed_evidence_refs(item.get("evidence_refs")))
    by_digest = {ref["revision_digest"]: ref for ref in refs}
    return [by_digest[key] for key in sorted(by_digest)]


def _axis_evidence(item: Mapping[str, Any], axis: str) -> list[dict]:
    raw = item.get("axis_evidence_refs")
    refs = []
    if isinstance(raw, Mapping):
        refs.extend(_typed_evidence_refs(raw.get(axis)))
    by_digest = {ref["revision_digest"]: ref for ref in refs}
    return [by_digest[key] for key in sorted(by_digest)]


def _stable_convergence_key(item: Mapping[str, Any]) -> bytes:
    """Build a conservative dedup key that never relies on statement text alone.

    A pre-existing typed root-cause reference is strongest.  Otherwise a claim
    can converge only when invariant + component + source location are all
    explicitly supplied.  Without either, the discovery remains a distinct
    claim candidate, keyed by its lane/finding identity or exact content.
    """
    root = item.get("root_cause_ref")
    if isinstance(root, dict) and {"kind", "revision_digest"}.issubset(root):
        return canonical_bytes({"root_cause_ref": root})

    invariant = item.get("invariant_ref") or item.get("violated_invariant_ref")
    component = item.get("affected_component")
    location = item.get("source_location") or item.get("location")
    if isinstance(invariant, dict) and component and location:
        return canonical_bytes({
            "invariant_ref": invariant,
            "affected_component": component,
            "source_location": location,
        })

    finding_id = item.get("finding_id") or item.get("id")
    if finding_id:
        return canonical_bytes({
            "originating_lane": item.get("originating_lane"),
            "finding_id": str(finding_id),
        })
    return canonical_bytes({
        "originating_lane": item.get("originating_lane"),
        "exact_discovery": dict(item),
    })


def _claim_outcome_with_evidence(item: Mapping[str, Any]) -> str:
    outcome = item.get("claim_outcome")
    if outcome not in {"SUPPORTED", "REFUTED"}:
        return "INCONCLUSIVE"
    if not _generic_evidence(item):
        return "INCONCLUSIVE"
    return str(outcome)


def _axis_outcome(items: Sequence[Mapping[str, Any]], axis: str) -> tuple[str, list[dict]]:
    observed: list[str] = []
    evidence: list[dict] = []
    for item in items:
        raw = item.get("axis_outcomes")
        outcome = raw.get(axis) if isinstance(raw, Mapping) else None
        refs = _axis_evidence(item, axis)
        if outcome in {"SUPPORTED", "REFUTED", "INCONCLUSIVE", "BLOCKED", "NOT_APPLICABLE"} and refs:
            observed.append(str(outcome))
            evidence.extend(refs)
    unique = set(observed)
    if not unique:
        result = "INCONCLUSIVE"
    elif "SUPPORTED" in unique and "REFUTED" in unique:
        result = "INCONCLUSIVE"
    elif len(unique) == 1:
        result = next(iter(unique))
    else:
        # Mixed epistemic states are not promoted to positive evidence.
        result = "INCONCLUSIVE"
    by_digest = {ref["revision_digest"]: ref for ref in evidence}
    return result, [by_digest[key] for key in sorted(by_digest)]


def execute_e2_convergence(
    e1_completion: E1CompletionResult,
    source_generation_ref: Any,
    adjudicator_ref: Any,
    input_history_cut: dict,
    policy_ref: Any,
) -> E2CompletionResult:
    """Execute fail-closed E2 convergence and four-axis adjudication.

    Discovery text is never sufficient proof.  Missing evidence/outcomes remain
    INCONCLUSIVE, statement similarity alone cannot merge findings, and each
    axis is promoted only from explicitly supplied axis evidence.
    """
    e2_spec = build_e2_stage_spec()
    validate_stage_transition(e1_completion, e2_spec)

    grouped: dict[bytes, list[dict]] = {}
    for raw_claim in e1_completion.quarantined_claims:
        claim_data = dict(raw_claim)
        grouped.setdefault(_stable_convergence_key(claim_data), []).append(claim_data)

    adjudicated_decisions: list[FindingAdjudicationDecision] = []
    contradictions: list[ContradictionRevision] = []
    decision_digests: list[str] = []
    contradiction_digests: list[str] = []

    for group_key in sorted(grouped):
        items = grouped[group_key]
        statements = sorted({str(item.get("statement", "")).strip() for item in items if str(item.get("statement", "")).strip()})
        statement = statements[0] if len(statements) == 1 else " | ".join(statements)
        if not statement:
            statement = "UNSPECIFIED_CLAIM"

        invariant_refs: list[dict] = []
        scope_refs: list[dict] = []
        for item in items:
            invariant_refs.extend(_typed_evidence_refs(item.get("invariant_ref") or item.get("violated_invariant_ref")))
            scope_refs.extend(_typed_evidence_refs(item.get("scope_ref") or item.get("scope_refs")))
        inv_by_digest = {ref["revision_digest"]: ref for ref in invariant_refs}
        scope_by_digest = {ref["revision_digest"]: ref for ref in scope_refs}

        claim = FindingClaimRevision(
            statement=statement,
            source_generation_ref=_ref_dict(source_generation_ref),
            scope_refs=[scope_by_digest[key] for key in sorted(scope_by_digest)],
            violated_invariant_refs=[inv_by_digest[key] for key in sorted(inv_by_digest)],
        )

        # Contradiction requires explicit, evidence-bearing positions on both
        # sides.  Each side remains an exact FindingClaimRevision; the canonical
        # contradiction contract does not collapse opposing positions into one
        # claim plus an untyped "contradicting evidence" bag.
        evidence_by_outcome: dict[str, list[dict]] = {
            "SUPPORTED": [],
            "REFUTED": [],
        }
        position_claim_refs: dict[str, list[dict]] = {
            "SUPPORTED": [],
            "REFUTED": [],
        }
        for item_index, item in enumerate(items):
            outcome = _claim_outcome_with_evidence(item)
            if outcome not in evidence_by_outcome:
                continue
            evidence_by_outcome[outcome].extend(
                _generic_evidence(item)
            )
            item_statement = str(
                item.get("statement", statement)
            ).strip() or statement
            position_claim = FindingClaimRevision(
                statement=item_statement,
                source_generation_ref=_ref_dict(
                    source_generation_ref
                ),
                scope_refs=[
                    scope_by_digest[key]
                    for key in sorted(scope_by_digest)
                ],
                violated_invariant_refs=[
                    inv_by_digest[key]
                    for key in sorted(inv_by_digest)
                ],
                claim_id=deterministic_id(
                    "finding_claim_revision",
                    canonical_bytes(
                        {
                            "group_key": hashlib.sha256(
                                group_key
                            ).hexdigest(),
                            "outcome": outcome,
                            "item_index": item_index,
                            "item": item,
                        }
                    ),
                ),
            )
            position_claim_refs[outcome].append(
                position_claim.as_object().as_ref().as_dict()
            )

        if (
            evidence_by_outcome["SUPPORTED"]
            and evidence_by_outcome["REFUTED"]
            and position_claim_refs["SUPPORTED"]
            and position_claim_refs["REFUTED"]
        ):
            supporting = {
                ref["revision_digest"]: ref
                for ref in evidence_by_outcome["SUPPORTED"]
            }
            opposing = {
                ref["revision_digest"]: ref
                for ref in evidence_by_outcome["REFUTED"]
            }
            claim_refs = [
                *position_claim_refs["SUPPORTED"],
                *position_claim_refs["REFUTED"],
            ]
            contra = ContradictionRevision(
                claim_revision_refs=claim_refs,
                scope={
                    "convergence_key_sha256": hashlib.sha256(
                        group_key
                    ).hexdigest()
                },
                positions=[
                    {
                        "side": "SUPPORTING",
                        "claim_revision_digests": sorted(
                            ref["revision_digest"]
                            for ref in position_claim_refs[
                                "SUPPORTED"
                            ]
                        ),
                    },
                    {
                        "side": "OPPOSING",
                        "claim_revision_digests": sorted(
                            ref["revision_digest"]
                            for ref in position_claim_refs[
                                "REFUTED"
                            ]
                        ),
                    },
                ],
                supporting_evidence_qualification_refs=[
                    supporting[key]
                    for key in sorted(supporting)
                ],
                opposing_evidence_qualification_refs=[
                    opposing[key]
                    for key in sorted(opposing)
                ],
                failure_assumption_differences=[],
                environment_input_model_differences=[],
                required_falsifier=(
                    "SCOPE_MATCHED_FALSIFIER_OR_SCOPE_SPLIT"
                ),
                status="OPEN",
                contradiction_id=deterministic_id(
                    "contradiction_revision",
                    hashlib.sha256(group_key).hexdigest(),
                ),
            )
            contradictions.append(contra)
            contradiction_digests.append(contra.digest)

        axis_assessments: dict[str, FindingAxisAssessment] = {}
        all_axis_evidence: dict[str, dict] = {}
        for axis in ("MECHANISM", "REACHABILITY", "IMPACT", "SEVERITY"):
            outcome, evidence_refs = _axis_outcome(items, axis)
            for ref in evidence_refs:
                all_axis_evidence[ref["revision_digest"]] = ref
            axis_assessments[axis] = FindingAxisAssessment(
                claim_revision_ref=claim.as_object().as_ref().as_dict(),
                assessment_input_history_cut=input_history_cut,
                assessment_policy_ref=_ref_dict(policy_ref),
                axis=axis,
                epistemic_outcome=outcome,
                method="E2_EXPLICIT_AXIS_EVIDENCE" if evidence_refs else "E2_INSUFFICIENT_EVIDENCE",
                evidence_qualification_refs=evidence_refs,
            )

        dec = adjudicate_finding(
            claim=claim,
            mechanism=axis_assessments["MECHANISM"],
            reachability=axis_assessments["REACHABILITY"],
            impact=axis_assessments["IMPACT"],
            severity=axis_assessments["SEVERITY"],
            adjudicator_ref=_ref_dict(adjudicator_ref),
            input_history_cut=input_history_cut,
            evidence_refs=[all_axis_evidence[key] for key in sorted(all_axis_evidence)],
        )
        adjudicated_decisions.append(dec)
        decision_digests.append(dec.digest)

    # Bind exact decision/contradiction identities, not only cardinalities.
    e2_body = {
        "stage_key": "E2",
        "e1_completion_digest": e1_completion.completion_digest,
        "adjudication_decision_digests": sorted(decision_digests),
        "contradiction_digests": sorted(contradiction_digests),
    }
    e2_digest = hashlib.sha256(canonical_bytes(e2_body)).hexdigest()

    return E2CompletionResult(
        stage_key="E2",
        e1_completion_digest=e1_completion.completion_digest,
        adjudicated_decisions=tuple(adjudicated_decisions),
        contradiction_revisions=tuple(contradictions),
        completion_digest=e2_digest,
    )
