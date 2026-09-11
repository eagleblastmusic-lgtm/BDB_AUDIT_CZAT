"""Release Lifecycle and Successor Assurance (WP-E5-12 / M45A / §§14.5, 80.1, 105.1).

Implements:
1. Three Release Bases:
   - STOP_AXIS_MATERIALIZATION (no drift since STOP, copies stop release_readiness, no previous qualification)
   - FRESH_RELEASE_QUALIFICATION (first qualification after release-only drift, no predecessor)
   - RELEASE_REASSESSMENT (subsequent qualifications, requires previous_release_qualification_ref)
2. Invalidation semantics:
   - Audit-basis invalidation is NOT release-only drift; triggers SuccessorCampaignGenesis.
3. Successor campaign lineage:
   - Backward links to predecessor campaign, predecessor conclusion, and trigger ref.
4. Competing branch resolution:
   - SuccessorCampaignSelectionDecision resolves competing successor branches.
   - Unresolved competing branches fail closed with ASSURANCE_SUCCESSOR_CONFLICT.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .conclusion import CampaignConclusion, FinalAssuranceCase
from ..stop.models import StopEvaluation


RELEASE_BASES = {
    "STOP_AXIS_MATERIALIZATION",
    "FRESH_RELEASE_QUALIFICATION",
    "RELEASE_REASSESSMENT",
}

RELEASE_RESULTS = {
    "READY",
    "READY_WITH_RESIDUAL_RISK",
    "TECHNICALLY_NOT_READY",
    "QUALIFICATION_BLOCKED",
}


@dataclass(frozen=True)
class ReleaseQualification:
    release_qualification_id: str
    campaign_conclusion_ref: dict[str, Any]
    final_assurance_case_ref: dict[str, Any]
    stop_evaluation_ref: dict[str, Any]
    source_generation_ref: dict[str, Any]
    release_policy_ref: dict[str, Any]
    release_assessment_basis_cut: dict[str, Any]
    qualification_command_input_history_cut: dict[str, Any]
    assessment_basis: str
    result: str
    blocking_finding_or_risk_refs: tuple[dict[str, Any], ...] = ()
    accepted_residual_risk_refs: tuple[dict[str, Any], ...] = ()
    reason_codes: tuple[str, ...] = ()
    previous_release_qualification_ref: dict[str, Any] | None = None
    release_reassessment_input_refs: tuple[dict[str, Any], ...] = ()

    def __post_init__(self):
        if not self.release_qualification_id:
            raise ValidationError("MISSING_RELEASE_QUAL_ID", "ReleaseQualification requires id")
        if self.assessment_basis not in RELEASE_BASES:
            raise ValidationError("INVALID_RELEASE_BASIS", f"Unknown assessment_basis {self.assessment_basis}")
        if self.result not in RELEASE_RESULTS:
            raise ValidationError("INVALID_RELEASE_RESULT", f"Unknown result {self.result}")

        # Invariant 1: STOP_AXIS_MATERIALIZATION forbids previous_release_qualification_ref
        if self.assessment_basis == "STOP_AXIS_MATERIALIZATION":
            if self.previous_release_qualification_ref is not None:
                raise ValidationError(
                    "PREVIOUS_REF_FORBIDDEN_IN_MATERIALIZATION",
                    "STOP_AXIS_MATERIALIZATION cannot reference a previous release qualification",
                )

        # Invariant 2: FRESH_RELEASE_QUALIFICATION forbids previous_release_qualification_ref
        if self.assessment_basis == "FRESH_RELEASE_QUALIFICATION":
            if self.previous_release_qualification_ref is not None:
                raise ValidationError(
                    "PREVIOUS_REF_FORBIDDEN_IN_FRESH_QUALIFICATION",
                    "FRESH_RELEASE_QUALIFICATION cannot reference a previous release qualification",
                )

        # Invariant 3: RELEASE_REASSESSMENT requires previous_release_qualification_ref
        if self.assessment_basis == "RELEASE_REASSESSMENT":
            if self.previous_release_qualification_ref is None:
                raise ValidationError(
                    "PREVIOUS_REF_REQUIRED_IN_REASSESSMENT",
                    "RELEASE_REASSESSMENT strictly requires previous_release_qualification_ref",
                )

    def body(self) -> dict[str, Any]:
        data = {
            "release_qualification_id": self.release_qualification_id,
            "campaign_conclusion_ref": dict(self.campaign_conclusion_ref),
            "final_assurance_case_ref": dict(self.final_assurance_case_ref),
            "stop_evaluation_ref": dict(self.stop_evaluation_ref),
            "source_generation_ref": dict(self.source_generation_ref),
            "release_policy_ref": dict(self.release_policy_ref),
            "release_assessment_basis_cut": dict(self.release_assessment_basis_cut),
            "qualification_command_input_history_cut": dict(self.qualification_command_input_history_cut),
            "assessment_basis": self.assessment_basis,
            "result": self.result,
            "blocking_finding_or_risk_refs": [dict(r) for r in self.blocking_finding_or_risk_refs],
            "accepted_residual_risk_refs": [dict(r) for r in self.accepted_residual_risk_refs],
            "reason_codes": list(self.reason_codes),
        }
        if self.previous_release_qualification_ref is not None:
            data["previous_release_qualification_ref"] = dict(self.previous_release_qualification_ref)
        if self.release_reassessment_input_refs:
            data["release_reassessment_input_refs"] = [dict(r) for r in self.release_reassessment_input_refs]
        return data

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()

    @property
    def ref(self) -> dict[str, Any]:
        return {
            "kind": "release_qualification",
            "revision_digest": self.digest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::release_qualification/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


@dataclass(frozen=True)
class SuccessorCampaignGenesis:
    campaign_id: str
    predecessor_campaign_ref: dict[str, Any]
    predecessor_conclusion_ref: dict[str, Any]
    successor_trigger_ref: dict[str, Any]
    source_generation_ref: dict[str, Any]
    successor_input_history_cut: dict[str, Any]
    governing_policy_ref: dict[str, Any]
    challenge_freshness_policy_ref: dict[str, Any]
    governing_spec_refs: tuple[dict[str, Any], ...]
    carried_forward_qualification_refs: tuple[dict[str, Any], ...] = ()
    newly_required_obligation_refs: tuple[dict[str, Any], ...] = ()

    def __post_init__(self):
        if not self.campaign_id:
            raise ValidationError("MISSING_CAMPAIGN_ID", "SuccessorCampaignGenesis requires campaign_id")
        if not self.predecessor_campaign_ref or not self.predecessor_conclusion_ref or not self.successor_trigger_ref:
            raise ValidationError("MISSING_SUCCESSOR_ANCESTRY", "Successor requires predecessor and trigger refs")

    def body(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "predecessor_campaign_ref": dict(self.predecessor_campaign_ref),
            "predecessor_conclusion_ref": dict(self.predecessor_conclusion_ref),
            "successor_trigger_ref": dict(self.successor_trigger_ref),
            "source_generation_ref": dict(self.source_generation_ref),
            "successor_input_history_cut": dict(self.successor_input_history_cut),
            "carried_forward_qualification_refs": [dict(r) for r in self.carried_forward_qualification_refs],
            "newly_required_obligation_refs": [dict(r) for r in self.newly_required_obligation_refs],
            "challenge_freshness_policy_ref": dict(self.challenge_freshness_policy_ref),
            "governing_policy_ref": dict(self.governing_policy_ref),
            "governing_spec_refs": [dict(r) for r in self.governing_spec_refs],
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()

    @property
    def ref(self) -> dict[str, Any]:
        return {
            "kind": "successor_campaign_genesis",
            "revision_digest": self.digest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::successor_campaign_genesis/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


@dataclass(frozen=True)
class SuccessorCampaignSelectionDecision:
    selection_decision_id: str
    predecessor_conclusion_ref: dict[str, Any]
    candidate_successor_campaign_refs: tuple[dict[str, Any], ...]
    selected_successor_campaign_ref: dict[str, Any]
    resolution_basis_refs: tuple[dict[str, Any], ...]
    governing_policy_ref: dict[str, Any]
    input_history_cut: dict[str, Any]

    def __post_init__(self):
        if not self.selection_decision_id:
            raise ValidationError("MISSING_DECISION_ID", "Decision requires id")
        if len(self.candidate_successor_campaign_refs) < 2:
            raise ValidationError(
                "SELECTION_REQUIRES_MULTIPLE_CANDIDATES",
                "Selection decision requires at least 2 candidate successor campaign refs",
            )
        cand_digests = {
            r.get("revision_digest") for r in self.candidate_successor_campaign_refs if r.get("revision_digest")
        }
        selected_dig = self.selected_successor_campaign_ref.get("revision_digest")
        if selected_dig not in cand_digests:
            raise ValidationError(
                "SELECTED_NOT_IN_CANDIDATE_SET",
                f"Selected successor {selected_dig} not in candidate set {cand_digests}",
            )

    def body(self) -> dict[str, Any]:
        return {
            "selection_decision_id": self.selection_decision_id,
            "predecessor_conclusion_ref": dict(self.predecessor_conclusion_ref),
            "candidate_successor_campaign_refs": [dict(r) for r in self.candidate_successor_campaign_refs],
            "selected_successor_campaign_ref": dict(self.selected_successor_campaign_ref),
            "resolution_basis_refs": [dict(r) for r in self.resolution_basis_refs],
            "governing_policy_ref": dict(self.governing_policy_ref),
            "input_history_cut": dict(self.input_history_cut),
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()

    @property
    def ref(self) -> dict[str, Any]:
        return {
            "kind": "successor_campaign_selection_decision",
            "revision_digest": self.digest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::successor_campaign_selection_decision/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


class ReleaseLifecycleManager:
    """Orchestrates release qualifications and successor branch resolution."""

    @staticmethod
    def evaluate_release_qualification(
        qualification_id: str,
        conclusion: CampaignConclusion,
        final_case: FinalAssuranceCase,
        stop_eval: StopEvaluation,
        source_generation_ref: dict[str, Any],
        release_policy_ref: dict[str, Any],
        release_assessment_basis_cut: dict[str, Any],
        qualification_command_cut: dict[str, Any],
        assessment_basis: str,
        has_release_drift: bool = False,
        audit_basis_invalidated: bool = False,
        previous_qualification_ref: dict[str, Any] | None = None,
        reassessment_input_refs: Sequence[dict[str, Any]] = (),
    ) -> ReleaseQualification:
        # Invariant 1: Audit basis invalidation CANNOT be handled as release-only drift
        if audit_basis_invalidated:
            raise ValidationError(
                "AUDIT_BASIS_INVALIDATED_REQUIRES_SUCCESSOR",
                "Audit-basis invalidation cannot be resolved by release reassessment; requires successor campaign",
            )

        # Cross-axis binding checks
        if final_case.campaign_conclusion_ref.get("revision_digest") != conclusion.digest():
            raise ValidationError("FINALIZATION_BINDING_CONFLICT", "final_case does not bind conclusion")
        stop_eval_digest = stop_eval.ref.get("revision_digest") if hasattr(stop_eval, "ref") else getattr(stop_eval, "digest", lambda: "")()
        if final_case.stop_evaluation_ref.get("revision_digest") != stop_eval_digest:
            raise ValidationError("FINALIZATION_BINDING_CONFLICT", "final_case does not bind stop_eval")

        if assessment_basis == "STOP_AXIS_MATERIALIZATION":
            if has_release_drift:
                raise ValidationError("DRIFT_DETECTED_MATERIALIZATION_INVALID", "Cannot materialize STOP axis if release drift occurred")
            result = stop_eval.release_readiness
            prev_ref = None
        elif assessment_basis == "FRESH_RELEASE_QUALIFICATION":
            result = stop_eval.release_readiness
            prev_ref = None
        elif assessment_basis == "RELEASE_REASSESSMENT":
            if previous_qualification_ref is None:
                raise ValidationError("PREVIOUS_REF_REQUIRED", "Reassessment requires previous qualification ref")
            result = stop_eval.release_readiness
            prev_ref = previous_qualification_ref
        else:
            raise ValidationError("INVALID_ASSESSMENT_BASIS", f"Unknown {assessment_basis}")

        return ReleaseQualification(
            release_qualification_id=qualification_id,
            campaign_conclusion_ref=dict(conclusion.ref),
            final_assurance_case_ref=dict(final_case.ref),
            stop_evaluation_ref=dict(stop_eval.ref),
            source_generation_ref=dict(source_generation_ref),
            release_policy_ref=dict(release_policy_ref),
            release_assessment_basis_cut=dict(release_assessment_basis_cut),
            qualification_command_input_history_cut=dict(qualification_command_cut),
            assessment_basis=assessment_basis,
            result=result,
            blocking_finding_or_risk_refs=(),
            accepted_residual_risk_refs=tuple(conclusion.residual_risk_refs),
            reason_codes=(f"{assessment_basis}_QUALIFIED",),
            previous_release_qualification_ref=prev_ref,
            release_reassessment_input_refs=tuple(reassessment_input_refs),
        )

    @staticmethod
    def resolve_successor_branches(
        predecessor_conclusion_ref: dict[str, Any],
        candidate_successor_campaigns: Sequence[SuccessorCampaignGenesis],
        selection_decision: SuccessorCampaignSelectionDecision | None,
    ) -> SuccessorCampaignGenesis:
        """Resolve competing successor campaign branches. Fails closed on unselected conflict."""
        if len(candidate_successor_campaigns) == 0:
            raise ValidationError("NO_SUCCESSOR_CAMPAIGNS", "No successor campaigns provided")
        if len(candidate_successor_campaigns) == 1:
            return candidate_successor_campaigns[0]

        # Competing branches: selection decision is mandatory!
        if selection_decision is None:
            raise ValidationError(
                "ASSURANCE_SUCCESSOR_CONFLICT",
                "Multiple competing successor branches exist without accepted selection decision",
            )

        selected_digest = selection_decision.selected_successor_campaign_ref.get("revision_digest")
        for sc in candidate_successor_campaigns:
            if sc.digest() == selected_digest:
                return sc

        raise ValidationError("SELECTED_BRANCH_NOT_FOUND", "Selected branch not in candidate branches")
