"""BDB Audit v2 StageCompletion, LaneCompletion, StopInput, and StopEvaluation models (M24 / PR-027)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import object_digest
from ..core.ids import new_id, validate_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject


_EVAL_CONTEXTS = {"INTERMEDIATE", "FINAL_POST_E5", "POST_E6"}
_CONTINUATION_DECISIONS = {"PASS", "CONTINUE_REQUIRED", "E6_REQUIRED", "BLOCKED"}
_ASSURANCE_LEVELS = {"ADEQUATE_FOR_DECLARED_SCOPE", "BOUNDED", "INSUFFICIENT"}
_RELEASE_READINESS = {
    "READY", "READY_WITH_RESIDUAL_RISK",
    "TECHNICALLY_NOT_READY", "QUALIFICATION_BLOCKED",
}


def _ref_dict(ref: Any) -> dict:
    if isinstance(ref, dict):
        return dict(ref)
    if hasattr(ref, "ref"):
        return dict(ref.ref)
    if hasattr(ref, "as_dict"):
        return dict(ref.as_dict())
    return dict(ref)


@dataclass(frozen=True)
class LaneCompletion:
    """Immutable canonical decision for lane completion."""
    lane_run_ref: Mapping[str, Any]
    lane_spec_ref: Mapping[str, Any]
    input_history_cut: Mapping[str, Any]
    final_knowledge_state_ref: Mapping[str, Any]
    isolation_qualification_ref: Mapping[str, Any]
    attempt_refs: Sequence[Mapping[str, Any]] = ()
    required_output_refs: Sequence[Mapping[str, Any]] = ()
    contamination_assessment_refs: Sequence[Mapping[str, Any]] = ()
    completion_predicate_result: str = "LANE_COMPLETED"
    lane_completion_id: str | None = None

    def __post_init__(self):
        if self.lane_completion_id is None:
            object.__setattr__(self, "lane_completion_id", new_id("lane_completion"))
        elif self.lane_completion_id.startswith("lane_completion_"):
            validate_id(self.lane_completion_id, "lane_completion")

        if self.completion_predicate_result not in {"LANE_COMPLETED", "LANE_COMPLETION_BLOCKED"}:
            raise ValidationError(f"INVALID_LANE_COMPLETION_RESULT: {self.completion_predicate_result}")

        object.__setattr__(self, "attempt_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.attempt_refs])))
        object.__setattr__(self, "required_output_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.required_output_refs])))
        object.__setattr__(
            self, "contamination_assessment_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.contamination_assessment_refs])),
        )

    def body(self) -> dict[str, Any]:
        return {
            "lane_completion_id": self.lane_completion_id,
            "lane_run_ref": _ref_dict(self.lane_run_ref),
            "lane_spec_ref": _ref_dict(self.lane_spec_ref),
            "input_history_cut": dict(self.input_history_cut),
            "attempt_refs": list(self.attempt_refs),
            "final_knowledge_state_ref": _ref_dict(self.final_knowledge_state_ref),
            "required_output_refs": list(self.required_output_refs),
            "isolation_qualification_ref": _ref_dict(self.isolation_qualification_ref),
            "contamination_assessment_refs": list(self.contamination_assessment_refs),
            "completion_predicate_result": self.completion_predicate_result,
        }

    def as_object(self) -> CanonicalObject:
        lid = self.lane_completion_id if (self.lane_completion_id and self.lane_completion_id.startswith("lane_completion_")) else None
        return CanonicalObject("lane_completion", self.body(), logical_id=lid)

    @property
    def ref(self) -> dict[str, Any]:
        obj = self.as_object()
        return {
            "kind": "lane_completion",
            "revision_digest": obj.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::lane_completion/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


@dataclass(frozen=True)
class StageCompletion:
    """Immutable canonical decision for stage completion on an exact cut."""
    stage_run_ref: Mapping[str, Any]
    stage_spec_ref: Mapping[str, Any]
    input_history_cut: Mapping[str, Any]
    required_lane_slot_results: Sequence[Mapping[str, Any]]
    required_output_refs: Sequence[Mapping[str, Any]] = ()
    mandatory_obligation_summary: Mapping[str, Any] = field(default_factory=dict)
    unresolved_material_refs: Sequence[Mapping[str, Any]] = ()
    unknown_blocked_summary: Mapping[str, Any] = field(default_factory=dict)
    completion_predicate_result: str = "STAGE_COMPLETED"
    stage_completion_id: str | None = None

    def __post_init__(self):
        if self.stage_completion_id is None:
            object.__setattr__(self, "stage_completion_id", new_id("stage_completion"))
        elif self.stage_completion_id.startswith("stage_completion_"):
            validate_id(self.stage_completion_id, "stage_completion")

        if self.completion_predicate_result not in {"STAGE_COMPLETED", "STAGE_COMPLETION_BLOCKED"}:
            raise ValidationError(f"INVALID_STAGE_COMPLETION_RESULT: {self.completion_predicate_result}")

        # Fail-closed checks: if unresolved material refs or unknown blocked exist, must be STAGE_COMPLETION_BLOCKED
        if self.unresolved_material_refs and self.completion_predicate_result == "STAGE_COMPLETED":
            raise ValidationError("STAGE_COMPLETION_BLOCKED: unresolved material refs present")

        if self.unknown_blocked_summary.get("unknown_surfaces_count", 0) > 0 and self.completion_predicate_result == "STAGE_COMPLETED":
            raise ValidationError("STAGE_COMPLETION_BLOCKED: unknown surfaces in denominator")

        object.__setattr__(
            self, "required_lane_slot_results",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.required_lane_slot_results])),
        )
        object.__setattr__(self, "required_output_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.required_output_refs])))
        object.__setattr__(
            self, "unresolved_material_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.unresolved_material_refs])),
        )

    def body(self) -> dict[str, Any]:
        return {
            "stage_completion_id": self.stage_completion_id,
            "stage_run_ref": _ref_dict(self.stage_run_ref),
            "stage_spec_ref": _ref_dict(self.stage_spec_ref),
            "input_history_cut": dict(self.input_history_cut),
            "required_lane_slot_results": list(self.required_lane_slot_results),
            "required_output_refs": list(self.required_output_refs),
            "mandatory_obligation_summary": dict(self.mandatory_obligation_summary),
            "unresolved_material_refs": list(self.unresolved_material_refs),
            "unknown_blocked_summary": dict(self.unknown_blocked_summary),
            "completion_predicate_result": self.completion_predicate_result,
        }

    def as_object(self) -> CanonicalObject:
        lid = self.stage_completion_id if (self.stage_completion_id and self.stage_completion_id.startswith("stage_completion_")) else None
        return CanonicalObject("stage_completion", self.body(), logical_id=lid)

    @property
    def ref(self) -> dict[str, Any]:
        obj = self.as_object()
        return {
            "kind": "stage_completion",
            "revision_digest": obj.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stage_completion/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


@dataclass(frozen=True)
class StopInput:
    """Exact reproducible STOP input snapshot and required/completed/pending closure."""
    campaign_id: str
    source_generation_ref: Mapping[str, Any]
    input_history_cut: Mapping[str, Any]
    evaluation_context: str
    governing_policy_ref: Mapping[str, Any]
    policy_spec_refs: Sequence[Mapping[str, Any]]
    evaluator_revision_ref: Mapping[str, Any]
    required_stage_set_ref: Mapping[str, Any]
    required_stage_spec_refs: Sequence[Mapping[str, Any]]
    completed_stage_refs: Sequence[Mapping[str, Any]]
    pending_required_stage_refs: Sequence[Mapping[str, Any]]
    stop_input_snapshot_ref: Mapping[str, Any]
    inventory_revision_ref: Mapping[str, Any]
    mandatory_obligation_refs: Sequence[Mapping[str, Any]]
    current_obligation_qualification_refs: Sequence[Mapping[str, Any]]
    evidence_invalidation_refs: Sequence[Mapping[str, Any]]
    contradiction_refs: Sequence[Mapping[str, Any]]
    residual_risk_refs: Sequence[Mapping[str, Any]]
    evidence_invalidation_state: Mapping[str, Any] | str
    release_policy_ref: Mapping[str, Any]
    effort_profile_ref: Mapping[str, Any]
    effort_results_ref: Mapping[str, Any]
    unknown_blocked_summary: Mapping[str, Any]
    continuation_budget_authorization_ref: Mapping[str, Any] | None = None
    candidate_assurance_case_ref: Mapping[str, Any] | None = None
    challenger_refs: Sequence[Mapping[str, Any]] = ()
    challenger_freshness_profile_ref: Mapping[str, Any] | None = None
    release_basis_refs: Sequence[Mapping[str, Any]] = ()
    stop_input_id: str | None = None

    def __post_init__(self):
        if self.stop_input_id is None:
            object.__setattr__(self, "stop_input_id", new_id("stop_input"))
        elif self.stop_input_id.startswith("stop_input_"):
            validate_id(self.stop_input_id, "stop_input")

        if self.evaluation_context not in _EVAL_CONTEXTS:
            raise ValidationError(f"INVALID_EVALUATION_CONTEXT: {self.evaluation_context}")

        object.__setattr__(self, "policy_spec_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.policy_spec_refs])))
        object.__setattr__(self, "required_stage_spec_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.required_stage_spec_refs])))
        object.__setattr__(self, "completed_stage_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.completed_stage_refs])))
        object.__setattr__(self, "pending_required_stage_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.pending_required_stage_refs])))
        object.__setattr__(self, "mandatory_obligation_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.mandatory_obligation_refs])))
        object.__setattr__(
            self, "current_obligation_qualification_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.current_obligation_qualification_refs])),
        )
        object.__setattr__(self, "evidence_invalidation_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.evidence_invalidation_refs])))
        object.__setattr__(self, "contradiction_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.contradiction_refs])))
        object.__setattr__(self, "residual_risk_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.residual_risk_refs])))
        object.__setattr__(self, "challenger_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.challenger_refs])))
        object.__setattr__(self, "release_basis_refs", tuple(canonical_reference_set([_ref_dict(r) for r in self.release_basis_refs])))

    def body(self) -> dict[str, Any]:
        res = {
            "stop_input_id": self.stop_input_id,
            "campaign_id": self.campaign_id,
            "source_generation_ref": _ref_dict(self.source_generation_ref),
            "input_history_cut": dict(self.input_history_cut),
            "evaluation_context": self.evaluation_context,
            "governing_policy_ref": _ref_dict(self.governing_policy_ref),
            "policy_spec_refs": list(self.policy_spec_refs),
            "evaluator_revision_ref": _ref_dict(self.evaluator_revision_ref),
            "required_stage_set_ref": _ref_dict(self.required_stage_set_ref),
            "required_stage_spec_refs": list(self.required_stage_spec_refs),
            "completed_stage_refs": list(self.completed_stage_refs),
            "pending_required_stage_refs": list(self.pending_required_stage_refs),
            "stop_input_snapshot_ref": _ref_dict(self.stop_input_snapshot_ref),
            "inventory_revision_ref": _ref_dict(self.inventory_revision_ref),
            "mandatory_obligation_refs": list(self.mandatory_obligation_refs),
            "current_obligation_qualification_refs": list(self.current_obligation_qualification_refs),
            "evidence_invalidation_refs": list(self.evidence_invalidation_refs),
            "contradiction_refs": list(self.contradiction_refs),
            "residual_risk_refs": list(self.residual_risk_refs),
            "evidence_invalidation_state": dict(self.evidence_invalidation_state) if isinstance(self.evidence_invalidation_state, dict) else self.evidence_invalidation_state,
            "release_policy_ref": _ref_dict(self.release_policy_ref),
            "effort_profile_ref": _ref_dict(self.effort_profile_ref),
            "effort_results_ref": dict(self.effort_results_ref),
            "unknown_blocked_summary": dict(self.unknown_blocked_summary),
        }
        if self.continuation_budget_authorization_ref is not None:
            res["continuation_budget_authorization_ref"] = _ref_dict(self.continuation_budget_authorization_ref)
        if self.candidate_assurance_case_ref is not None:
            res["candidate_assurance_case_ref"] = _ref_dict(self.candidate_assurance_case_ref)
        if self.challenger_refs:
            res["challenger_refs"] = list(self.challenger_refs)
        if self.challenger_freshness_profile_ref is not None:
            res["challenger_freshness_profile_ref"] = _ref_dict(self.challenger_freshness_profile_ref)
        if self.release_basis_refs:
            res["release_basis_refs"] = list(self.release_basis_refs)
        return res

    def as_object(self) -> CanonicalObject:
        lid = self.stop_input_id if (self.stop_input_id and self.stop_input_id.startswith("stop_input_")) else None
        return CanonicalObject("stop_input", self.body(), logical_id=lid)

    @property
    def ref(self) -> dict[str, Any]:
        obj = self.as_object()
        return {
            "kind": "stop_input",
            "revision_digest": obj.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stop_input/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


@dataclass(frozen=True)
class StopEvaluation:
    """Four-axis pure STOP evaluation on exact input."""
    stop_input_ref: Mapping[str, Any]
    continuation_decision: str
    assurance_level: str
    release_readiness: str
    reason_codes: Sequence[str] = ()
    blocking_obligation_refs: Sequence[Mapping[str, Any]] = ()
    remaining_obligation_refs: Sequence[Mapping[str, Any]] = ()
    stop_evaluation_id: str | None = None

    def __post_init__(self):
        if self.stop_evaluation_id is None:
            object.__setattr__(self, "stop_evaluation_id", new_id("stop_evaluation"))
        elif self.stop_evaluation_id.startswith("stop_evaluation_"):
            validate_id(self.stop_evaluation_id, "stop_evaluation")

        if self.continuation_decision not in _CONTINUATION_DECISIONS:
            raise ValidationError(f"INVALID_CONTINUATION_DECISION: {self.continuation_decision}")
        if self.assurance_level not in _ASSURANCE_LEVELS:
            raise ValidationError(f"INVALID_ASSURANCE_LEVEL: {self.assurance_level}")
        if self.release_readiness not in _RELEASE_READINESS:
            raise ValidationError(f"INVALID_RELEASE_READINESS: {self.release_readiness}")

        # PASS requires both blocking and remaining obligations to be empty
        if self.continuation_decision == "PASS":
            if self.blocking_obligation_refs or self.remaining_obligation_refs:
                raise ValidationError("STOP_PASS_REQUIRES_EMPTY_REMAINING_OBLIGATIONS")
            if self.assurance_level != "ADEQUATE_FOR_DECLARED_SCOPE":
                raise ValidationError("STOP_PASS_REQUIRES_ADEQUATE_ASSURANCE")

        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(
            self, "blocking_obligation_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.blocking_obligation_refs])),
        )
        object.__setattr__(
            self, "remaining_obligation_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.remaining_obligation_refs])),
        )

    def body(self) -> dict[str, Any]:
        return {
            "stop_evaluation_id": self.stop_evaluation_id,
            "stop_input_ref": _ref_dict(self.stop_input_ref),
            "continuation_decision": self.continuation_decision,
            "assurance_level": self.assurance_level,
            "release_readiness": self.release_readiness,
            "reason_codes": list(self.reason_codes),
            "blocking_obligation_refs": list(self.blocking_obligation_refs),
            "remaining_obligation_refs": list(self.remaining_obligation_refs),
        }

    def as_object(self) -> CanonicalObject:
        lid = self.stop_evaluation_id if (self.stop_evaluation_id and self.stop_evaluation_id.startswith("stop_evaluation_")) else None
        return CanonicalObject("stop_evaluation", self.body(), logical_id=lid)

    @property
    def ref(self) -> dict[str, Any]:
        obj = self.as_object()
        return {
            "kind": "stop_evaluation",
            "revision_digest": obj.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stop_evaluation/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


@dataclass(frozen=True)
class Snapshot:
    """Canonical derived projection representing an exact reproducible state snapshot."""
    snapshot_type: str
    as_of_head: Mapping[str, Any]
    projection_code_revision: str
    projection_input_refs: Sequence[Mapping[str, Any]]
    snapshot_artifact_ref: Mapping[str, Any]
    snapshot_id: str | None = None

    def __post_init__(self):
        if self.snapshot_id is None:
            object.__setattr__(self, "snapshot_id", new_id("snapshot"))
        elif self.snapshot_id.startswith("snapshot_"):
            validate_id(self.snapshot_id, "snapshot")

        object.__setattr__(
            self, "projection_input_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.projection_input_refs]))
        )

    def body(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_type": self.snapshot_type,
            "as_of_head": dict(self.as_of_head),
            "projection_code_revision": self.projection_code_revision,
            "projection_input_refs": list(self.projection_input_refs),
            "snapshot_artifact_ref": _ref_dict(self.snapshot_artifact_ref),
        }

    def as_object(self) -> CanonicalObject:
        lid = self.snapshot_id if (self.snapshot_id and self.snapshot_id.startswith("snapshot_")) else None
        return CanonicalObject("snapshot", self.body(), logical_id=lid)

    @property
    def digest(self) -> str:
        return self.as_object().digest

    @property
    def ref(self) -> dict[str, Any]:
        return {
            "kind": "snapshot",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::snapshot/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }

