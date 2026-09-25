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


def build_e1_lane_specs(
    stage_spec_revision: str = "1",
    lane_revision: str = "1",
    required_isolation_assurance: str = "DECLARED",
) -> dict[str, LaneSpec]:
    """Construct E1 LaneSpecs without overstating executor isolation."""
    specs = {}
    for slot in E1_LANE_SLOTS:
        purpose, strategy = E1_LANE_STRATEGIES[slot]
        specs[slot] = LaneSpec(
            lane_key=slot,
            lane_spec_revision=lane_revision,
            stage_spec_revision=stage_spec_revision,
            purpose=purpose,
            primary_strategy=strategy,
            required_isolation_assurance=required_isolation_assurance,
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
