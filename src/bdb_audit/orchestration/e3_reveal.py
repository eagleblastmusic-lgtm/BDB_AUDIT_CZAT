"""E3 Checkpoint, Positive Reveal, Gap-Directed Mode, Cumulative/Holdout Reveal, and Multi-Stage False Negative Assessment (WP-F5 / PR-E3-02)."""
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
import hashlib
from uuid import uuid4

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..knowledge.exposure import (
    KnowledgeState,
    DiscoveryRecord,
    GrantAccepted,
    PotentialExposureRecord,
)
from .e3 import (
    E3_LANE_SLOTS,
    E3BlindNoveltyResult,
    _ref_dict,
)

FORBIDDEN_REVEAL_FIELDS = frozenset({
    "finding_claim_ref",
    "finding_id",
    "adjudication_decision",
    "finding_statement",
    "mechanism_statement",
    "claim_corpus",
    "prior_finding_ref",
    "raw_finding_bytes",
    "finding_count",
    "leak_metadata",
})


@dataclass(frozen=True)
class E3BlindCheckpoint:
    checkpoint_id: str
    accepted_history_cut: dict
    blind_completion_digest: str
    sealed_findings_count: int
    lane_slots: tuple[str, ...] = E3_LANE_SLOTS

    def __post_init__(self):
        if not self.checkpoint_id:
            raise ValidationError("CHECKPOINT_ID_REQUIRED")
        if not self.accepted_history_cut:
            raise ValidationError("HISTORY_CUT_REQUIRED")
        if len(self.blind_completion_digest) != 64:
            raise ValidationError("INVALID_BLIND_COMPLETION_DIGEST")
        if tuple(self.lane_slots) != E3_LANE_SLOTS:
            raise ValidationError("LANE_SLOTS_MISMATCH")

    def body(self) -> dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "accepted_history_cut": dict(self.accepted_history_cut),
            "blind_completion_digest": self.blind_completion_digest,
            "sealed_findings_count": self.sealed_findings_count,
            "lane_slots": list(self.lane_slots),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def ref(self) -> dict:
        return {
            "kind": "checkpoint",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::checkpoint/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


def create_e3_blind_checkpoint(
    blind_result: E3BlindNoveltyResult,
    accepted_history_cut: Mapping,
) -> E3BlindCheckpoint:
    """Accept and seal an immutable checkpoint after blind novelty ensemble."""
    cut_seq = accepted_history_cut.get("accepted_head_seq", 0)
    blind_seq = blind_result.assigned_history_cut.get("accepted_head_seq", 0)
    if cut_seq < blind_seq:
        raise ValidationError(
            "STALE_CHECKPOINT_OR_CUT_REJECTED",
            f"Checkpoint cut seq {cut_seq} is older than blind cut seq {blind_seq}",
        )

    # Ensure all mandatory lanes are sealed in broker
    if not blind_result.broker.is_checkpoint_sealed:
        blind_result.broker.seal_checkpoint(dict(accepted_history_cut))

    chk_id = f"chk_e3_blind_{blind_result.blind_completion_digest[:16]}"
    return E3BlindCheckpoint(
        checkpoint_id=chk_id,
        accepted_history_cut=dict(accepted_history_cut),
        blind_completion_digest=blind_result.blind_completion_digest,
        sealed_findings_count=blind_result.total_discoveries,
        lane_slots=blind_result.completed_lanes,
    )


@dataclass(frozen=True)
class PositiveGapProjection:
    projection_id: str
    checkpoint_ref: dict
    accepted_history_cut: dict
    coverage_obligations: tuple[dict, ...]
    gap_map: dict
    explicit_unknown_scope: tuple[dict, ...]
    explicit_unsupported_scope: tuple[dict, ...]

    def __post_init__(self):
        # Fail closed on any forbidden finding leakage
        self._check_for_forbidden_leak(self.body())

    def _check_for_forbidden_leak(self, data: Any, path: str = "") -> None:
        if isinstance(data, Mapping):
            for k, v in data.items():
                if k in FORBIDDEN_REVEAL_FIELDS:
                    raise ValidationError(
                        "DISALLOWED_FINDING_CORPUS_REVEAL",
                        f"Forbidden field '{k}' detected in positive gap projection at '{path}.{k}'",
                    )
                self._check_for_forbidden_leak(v, f"{path}.{k}" if path else str(k))
        elif isinstance(data, (list, tuple)):
            for idx, item in enumerate(data):
                self._check_for_forbidden_leak(item, f"{path}[{idx}]")

    def body(self) -> dict:
        return {
            "projection_id": self.projection_id,
            "checkpoint_ref": dict(self.checkpoint_ref),
            "accepted_history_cut": dict(self.accepted_history_cut),
            "coverage_obligations": [dict(o) for o in self.coverage_obligations],
            "gap_map": dict(self.gap_map),
            "explicit_unknown_scope": [dict(s) for s in self.explicit_unknown_scope],
            "explicit_unsupported_scope": [dict(s) for s in self.explicit_unsupported_scope],
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def ref(self) -> dict:
        return {
            "kind": "view_manifest",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::view_manifest/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


@dataclass(frozen=True)
class E3RevealEvent:
    reveal_id: str
    reveal_type: str  # "POSITIVE_GAP_VIEW", "CUMULATIVE_CORPUS_VIEW", "HOLDOUT_CORPUS_VIEW"
    checkpoint_ref: dict
    accepted_history_cut: dict
    knowledge_state_before_ref: dict
    knowledge_state_after_ref: dict
    revealed_view_manifest_ref: dict
    producer_ref: dict

    def body(self) -> dict:
        return {
            "reveal_id": self.reveal_id,
            "reveal_type": self.reveal_type,
            "checkpoint_ref": dict(self.checkpoint_ref),
            "accepted_history_cut": dict(self.accepted_history_cut),
            "knowledge_state_before_ref": dict(self.knowledge_state_before_ref),
            "knowledge_state_after_ref": dict(self.knowledge_state_after_ref),
            "revealed_view_manifest_ref": dict(self.revealed_view_manifest_ref),
            "producer_ref": dict(self.producer_ref),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def ref(self) -> dict:
        return {
            "kind": "view_manifest",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::view_manifest/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


def execute_positive_gap_reveal(
    checkpoint: E3BlindCheckpoint,
    accepted_history_cut: Mapping,
    knowledge_state_before: KnowledgeState,
    coverage_obligations: Sequence[Mapping],
    gap_map: Mapping,
    explicit_unknown_scope: Sequence[Mapping],
    explicit_unsupported_scope: Sequence[Mapping],
    producer_ref: Mapping,
) -> tuple[PositiveGapProjection, E3RevealEvent, KnowledgeState]:
    """Execute positive gap projection reveal.

    Fails closed if:
    - checkpoint is missing or invalid;
    - history cut is stale relative to checkpoint;
    - forbidden finding corpus data is included.
    """
    chk_seq = checkpoint.accepted_history_cut.get("accepted_head_seq", 0)
    current_seq = accepted_history_cut.get("accepted_head_seq", 0)
    if current_seq < chk_seq:
        raise ValidationError(
            "STALE_OR_INCONSISTENT_HISTORY_CUT",
            f"Current cut {current_seq} is older than checkpoint cut {chk_seq}",
        )

    proj_id = f"proj_gap_{uuid4().hex[:12]}"
    projection = PositiveGapProjection(
        projection_id=proj_id,
        checkpoint_ref=checkpoint.ref,
        accepted_history_cut=dict(accepted_history_cut),
        coverage_obligations=tuple(dict(o) for o in coverage_obligations),
        gap_map=dict(gap_map),
        explicit_unknown_scope=tuple(dict(s) for s in explicit_unknown_scope),
        explicit_unsupported_scope=tuple(dict(s) for s in explicit_unsupported_scope),
    )

    view_manifest_ref = projection.ref

    # Construct KnowledgeState advancement
    adv_attempt_ref = knowledge_state_before.attempt_ref
    iso_ref = knowledge_state_before.isolation_qualification_ref
    prev_state_ref = knowledge_state_before.as_object().ref.as_dict()

    # Create GrantAccepted and PotentialExposureRecord
    grant = GrantAccepted(
        attempt_ref=adv_attempt_ref,
        grant_input_history_cut=dict(accepted_history_cut),
        view_manifest_ref=view_manifest_ref,
        delivery_profile_ref={"delivery": "SAFE_PROJECTION_VIEW"},
        forbidden_knowledge_policy_ref="NO_RAW_FINDING_CORPUS",
        channel_class="POSITIVE_GAP_VIEW",
        previous_knowledge_state_ref=prev_state_ref,
    )
    exposure = PotentialExposureRecord(
        attempt_ref=adv_attempt_ref,
        grant_ref=grant.as_object().ref.as_dict(),
        view_manifest_ref=view_manifest_ref,
        exposure_input_history_cut=dict(accepted_history_cut),
        previous_knowledge_state_ref=prev_state_ref,
    )

    new_known_classes = tuple(sorted(set(knowledge_state_before.known_classes) | {
        "GAP_DIRECTED_COVERAGE_VIEW",
        "EXPLICIT_UNKNOWN_SCOPE",
        "EXPLICIT_UNSUPPORTED_SCOPE",
    }))

    knowledge_state_after = KnowledgeState(
        attempt_ref=adv_attempt_ref,
        basis_history_cut=dict(accepted_history_cut),
        isolation_qualification_ref=iso_ref,
        allowed_view_refs=(view_manifest_ref,),
        potential_exposure_refs=(exposure.as_object().ref.as_dict(),),
        contamination_assessment_refs=(),
        previous_knowledge_state_ref=prev_state_ref,
        known_classes=new_known_classes,
    )

    reveal_event = E3RevealEvent(
        reveal_id=f"rev_{uuid4().hex[:12]}",
        reveal_type="POSITIVE_GAP_VIEW",
        checkpoint_ref=checkpoint.ref,
        accepted_history_cut=dict(accepted_history_cut),
        knowledge_state_before_ref=prev_state_ref,
        knowledge_state_after_ref=knowledge_state_after.as_object().ref.as_dict(),
        revealed_view_manifest_ref=view_manifest_ref,
        producer_ref=dict(producer_ref),
    )

    return projection, reveal_event, knowledge_state_after


class E3GapDirectedScheduler:
    """Scheduler in GAP-DIRECTED MODE; generates target list strictly from Gap Engine / Gap Map."""

    def __init__(
        self,
        positive_projection: PositiveGapProjection,
        reveal_event: E3RevealEvent,
        knowledge_state: KnowledgeState,
    ):
        if reveal_event.reveal_type != "POSITIVE_GAP_VIEW":
            raise ValidationError(
                "REVEAL_REQUIRED_FOR_GAP_MODE",
                f"Cannot enter gap-directed mode with reveal_type {reveal_event.reveal_type}",
            )
        self.projection = positive_projection
        self.reveal_event = reveal_event
        self.knowledge_state = knowledge_state
        self.mode = "GAP_DIRECTED_MODE"
        self._executed_targets: list[dict] = []

    def get_gap_target_list(self) -> list[dict]:
        """Derive prioritized targets strictly from Gap Map."""
        gaps = self.projection.gap_map.get("gaps", [])
        targets = []
        for g in gaps:
            targets.append({
                "gap_id": g.get("gap_id"),
                "target_scope_ref": g.get("target_scope_ref"),
                "materiality": g.get("materiality", "MATERIAL"),
                "missing_obligations": g.get("missing_or_unsatisfied_obligation_refs", []),
            })
        return sorted(targets, key=lambda x: str(x.get("gap_id")))

    def record_gap_directed_discovery(
        self,
        target_scope_ref: Mapping,
        discovery_data: Mapping,
    ) -> dict:
        """Record discovery found during gap exploration.

        Discoveries carry POST_REVEAL_CONFIRMATION and cannot claim blind origin.
        """
        disc = dict(discovery_data)
        classification = disc.get("classification", "POST_REVEAL_CONFIRMATION")
        if classification == "PRE_REVEAL_DISCOVERY":
            raise ValidationError(
                "BLIND_ORIGIN_AFTER_REVEAL_FORBIDDEN",
                "Discoveries produced in gap-directed mode cannot claim PRE_REVEAL_DISCOVERY",
            )
        disc["classification"] = "POST_REVEAL_CONFIRMATION"
        disc["mode"] = "GAP_DIRECTED"
        disc["target_scope_ref"] = dict(target_scope_ref)
        disc["knowledge_state_ref"] = self.knowledge_state.as_object().ref.as_dict()
        self._executed_targets.append(disc)
        return disc


def execute_cumulative_corpus_reveal(
    scheduler: E3GapDirectedScheduler,
    e1_e2_corpus_manifest_ref: Mapping,
    accepted_history_cut: Mapping,
    producer_ref: Mapping,
) -> tuple[E3RevealEvent, KnowledgeState]:
    """Phase E cumulative corpus reveal (E1 + E2 corpus) after gap phase execution."""
    prev_state_ref = scheduler.knowledge_state.as_object().ref.as_dict()
    new_known = tuple(sorted(set(scheduler.knowledge_state.known_classes) | {"CUMULATIVE_E1_E2_CORPUS"}))

    grant = GrantAccepted(
        attempt_ref=scheduler.knowledge_state.attempt_ref,
        grant_input_history_cut=dict(accepted_history_cut),
        view_manifest_ref=dict(e1_e2_corpus_manifest_ref),
        delivery_profile_ref={"delivery": "ADJUDICATED_FINDING_CORPUS"},
        forbidden_knowledge_policy_ref="PERMIT_E1_E2_CORPUS",
        channel_class="CUMULATIVE_CORPUS_VIEW",
        previous_knowledge_state_ref=prev_state_ref,
    )
    exposure = PotentialExposureRecord(
        attempt_ref=scheduler.knowledge_state.attempt_ref,
        grant_ref=grant.as_object().ref.as_dict(),
        view_manifest_ref=dict(e1_e2_corpus_manifest_ref),
        exposure_input_history_cut=dict(accepted_history_cut),
        previous_knowledge_state_ref=prev_state_ref,
    )

    state_after = KnowledgeState(
        attempt_ref=scheduler.knowledge_state.attempt_ref,
        basis_history_cut=dict(accepted_history_cut),
        isolation_qualification_ref=scheduler.knowledge_state.isolation_qualification_ref,
        allowed_view_refs=(dict(e1_e2_corpus_manifest_ref),),
        potential_exposure_refs=(exposure.as_object().ref.as_dict(),),
        contamination_assessment_refs=(),
        previous_knowledge_state_ref=prev_state_ref,
        known_classes=new_known,
    )

    reveal = E3RevealEvent(
        reveal_id=f"rev_cumul_{uuid4().hex[:12]}",
        reveal_type="CUMULATIVE_CORPUS_VIEW",
        checkpoint_ref=scheduler.projection.checkpoint_ref,
        accepted_history_cut=dict(accepted_history_cut),
        knowledge_state_before_ref=prev_state_ref,
        knowledge_state_after_ref=state_after.as_object().ref.as_dict(),
        revealed_view_manifest_ref=dict(e1_e2_corpus_manifest_ref),
        producer_ref=dict(producer_ref),
    )
    return reveal, state_after


def execute_holdout_reveal(
    knowledge_state: KnowledgeState,
    holdout_corpus_manifest_ref: Mapping,
    accepted_history_cut: Mapping,
    producer_ref: Mapping,
    corpus_role: str = "AUXILIARY_HOLDOUT",
) -> tuple[E3RevealEvent, KnowledgeState]:
    """Phase F external holdout reveal (e.g. A1/A2/A3 external corpus).

    Fails closed if corpus_role is confused with canonical direct predecessor.
    """
    if corpus_role in {"CANONICAL_PREDECESSOR", "DIRECT_PREDECESSOR", "E1", "E2"}:
        raise ValidationError(
            "CANONICAL_PREDECESSOR_CONFUSION",
            f"Auxiliary holdout corpus role cannot be '{corpus_role}'; must not be confused with direct predecessor",
        )

    prev_state_ref = knowledge_state.as_object().ref.as_dict()
    new_known = tuple(sorted(set(knowledge_state.known_classes) | {"CONSUMED_EXTERNAL_HOLDOUT"}))

    grant = GrantAccepted(
        attempt_ref=knowledge_state.attempt_ref,
        grant_input_history_cut=dict(accepted_history_cut),
        view_manifest_ref=dict(holdout_corpus_manifest_ref),
        delivery_profile_ref={"delivery": "EXTERNAL_HOLDOUT_CORPUS"},
        forbidden_knowledge_policy_ref="PERMIT_EXTERNAL_HOLDOUT",
        channel_class="HOLDOUT_CORPUS_VIEW",
        previous_knowledge_state_ref=prev_state_ref,
    )
    exposure = PotentialExposureRecord(
        attempt_ref=knowledge_state.attempt_ref,
        grant_ref=grant.as_object().ref.as_dict(),
        view_manifest_ref=dict(holdout_corpus_manifest_ref),
        exposure_input_history_cut=dict(accepted_history_cut),
        previous_knowledge_state_ref=prev_state_ref,
    )

    state_after = KnowledgeState(
        attempt_ref=knowledge_state.attempt_ref,
        basis_history_cut=dict(accepted_history_cut),
        isolation_qualification_ref=knowledge_state.isolation_qualification_ref,
        allowed_view_refs=(dict(holdout_corpus_manifest_ref),),
        potential_exposure_refs=(exposure.as_object().ref.as_dict(),),
        contamination_assessment_refs=(),
        previous_knowledge_state_ref=prev_state_ref,
        known_classes=new_known,
    )

    reveal = E3RevealEvent(
        reveal_id=f"rev_holdout_{uuid4().hex[:12]}",
        reveal_type="HOLDOUT_CORPUS_VIEW",
        checkpoint_ref={"checkpoint": "HOLDOUT_PHASE"},
        accepted_history_cut=dict(accepted_history_cut),
        knowledge_state_before_ref=prev_state_ref,
        knowledge_state_after_ref=state_after.as_object().ref.as_dict(),
        revealed_view_manifest_ref=dict(holdout_corpus_manifest_ref),
        producer_ref=dict(producer_ref),
    )
    return reveal, state_after


@dataclass(frozen=True)
class FalseNegativeRelationshipAssessment:
    assessment_id: str
    discovery_ref: dict
    assessment_input_history_cut: dict
    predecessor_stage_or_claim_refs: tuple[dict, ...]
    relationship_policy_ref: str
    result: str  # "MULTI_STAGE_FALSE_NEGATIVE", "PREVIOUS_FALSE_NEGATIVE", "NOT_ESTABLISHED", "INCONCLUSIVE"
    reason_codes: tuple[str, ...]

    def body(self) -> dict:
        return {
            "assessment_id": self.assessment_id,
            "discovery_ref": dict(self.discovery_ref),
            "assessment_input_history_cut": dict(self.assessment_input_history_cut),
            "predecessor_stage_or_claim_refs": [dict(r) for r in self.predecessor_stage_or_claim_refs],
            "relationship_policy_ref": self.relationship_policy_ref,
            "result": self.result,
            "reason_codes": list(self.reason_codes),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def ref(self) -> dict:
        return {
            "kind": "blind_origin_eligibility_assessment",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::blind_origin_eligibility_assessment/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


def evaluate_false_negative_relationship(
    discovery_ref: Mapping,
    assessment_input_history_cut: Mapping,
    predecessor_stage_refs: Sequence[Mapping],
    target_surface_ref: Mapping,
    surface_active_in_predecessor: bool,
    surface_observed_in_predecessor: bool,
    predecessor_completion_seq: int,
    relationship_policy_ref: str = "BDB_POLICY_REGISTRY::false_negative_policy/1",
) -> FalseNegativeRelationshipAssessment:
    """Evaluate whether a discovery represents a legitimate MULTI_STAGE_FALSE_NEGATIVE.

    Marked MULTI_STAGE_FALSE_NEGATIVE ONLY when accepted history cut proves prior omission:
    - Target surface was active and in-scope during predecessor stage;
    - Predecessor stage completed without observing or reporting the finding;
    - Assessment input cut is >= predecessor completion seq.

    If target surface was new scope: result is NOT_ESTABLISHED (new scope != false negative).
    If cut is stale: fails closed.
    """
    cut_seq = assessment_input_history_cut.get("accepted_head_seq", 0)
    if cut_seq < predecessor_completion_seq:
        raise ValidationError(
            "STALE_KNOWLEDGE_CUT_REJECTED",
            f"Assessment cut {cut_seq} is older than predecessor completion {predecessor_completion_seq}",
        )

    asmt_id = f"fn_asmt_{uuid4().hex[:12]}"

    if not surface_active_in_predecessor:
        # New-scope discovery != false negative
        return FalseNegativeRelationshipAssessment(
            assessment_id=asmt_id,
            discovery_ref=dict(discovery_ref),
            assessment_input_history_cut=dict(assessment_input_history_cut),
            predecessor_stage_or_claim_refs=tuple(dict(r) for r in predecessor_stage_refs),
            relationship_policy_ref=relationship_policy_ref,
            result="NOT_ESTABLISHED",
            reason_codes=("NEW_SCOPE_DISCOVERY_NOT_FALSE_NEGATIVE",),
        )

    if surface_active_in_predecessor and not surface_observed_in_predecessor:
        # Legitimate multi-stage false negative
        return FalseNegativeRelationshipAssessment(
            assessment_id=asmt_id,
            discovery_ref=dict(discovery_ref),
            assessment_input_history_cut=dict(assessment_input_history_cut),
            predecessor_stage_or_claim_refs=tuple(dict(r) for r in predecessor_stage_refs),
            relationship_policy_ref=relationship_policy_ref,
            result="MULTI_STAGE_FALSE_NEGATIVE",
            reason_codes=("PRIOR_STAGE_OMISSION_PROVEN_BY_ACCEPTED_CUT",),
        )

    # Surface was already observed in predecessor
    return FalseNegativeRelationshipAssessment(
        assessment_id=asmt_id,
        discovery_ref=dict(discovery_ref),
        assessment_input_history_cut=dict(assessment_input_history_cut),
        predecessor_stage_or_claim_refs=tuple(dict(r) for r in predecessor_stage_refs),
        relationship_policy_ref=relationship_policy_ref,
        result="NOT_ESTABLISHED",
        reason_codes=("ALREADY_OBSERVED_IN_PREDECESSOR",),
    )
