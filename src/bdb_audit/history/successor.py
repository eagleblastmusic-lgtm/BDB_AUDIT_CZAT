"""Successor Campaign Genesis and Selection Decision (WP-F4-10 / R5.3 §14.5)."""
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
import hashlib

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id, validate_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, ObjectRef
from .replay import _ref_dict


@dataclass(frozen=True)
class SuccessorCampaignGenesis:
    predecessor_campaign_ref: Any
    predecessor_conclusion_ref: Any
    successor_trigger_ref: Any
    source_generation_ref: Any
    successor_input_history_cut: dict
    challenge_freshness_policy_ref: Any
    governing_policy_ref: Any
    carried_forward_qualification_refs: Sequence[Any] = ()
    newly_required_obligation_refs: Sequence[Any] = ()
    governing_spec_refs: Sequence[Any] = ()
    campaign_id: str | None = None

    def __post_init__(self):
        if self.campaign_id is None:
            object.__setattr__(self, "campaign_id", new_id("successor_campaign_genesis"))
        elif self.campaign_id.startswith("successor_campaign_genesis_"):
            validate_id(self.campaign_id, "successor_campaign_genesis")

        # Validation: Successor campaign requires prior history cut; EMPTY_HISTORY is reserved for initial genesis
        if self.successor_input_history_cut.get("tag") == "EMPTY_HISTORY" or self.successor_input_history_cut.get("variant") == "EMPTY_HISTORY_CUT":
            raise ValidationError(
                "SUCCESSOR_REQUIRES_NON_EMPTY_HISTORY",
                "Successor campaign continuation requires prior history cut, not EMPTY_HISTORY",
            )

        object.__setattr__(
            self, "carried_forward_qualification_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.carried_forward_qualification_refs]))
        )
        object.__setattr__(
            self, "newly_required_obligation_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.newly_required_obligation_refs]))
        )
        object.__setattr__(
            self, "governing_spec_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.governing_spec_refs]))
        )

    def body(self) -> dict:
        return {
            "campaign_id": self.campaign_id or "successor_default",
            "predecessor_campaign_ref": _ref_dict(self.predecessor_campaign_ref),
            "predecessor_conclusion_ref": _ref_dict(self.predecessor_conclusion_ref),
            "successor_trigger_ref": _ref_dict(self.successor_trigger_ref),
            "source_generation_ref": _ref_dict(self.source_generation_ref),
            "successor_input_history_cut": dict(self.successor_input_history_cut),
            "carried_forward_qualification_refs": list(self.carried_forward_qualification_refs),
            "newly_required_obligation_refs": list(self.newly_required_obligation_refs),
            "challenge_freshness_policy_ref": _ref_dict(self.challenge_freshness_policy_ref),
            "governing_policy_ref": _ref_dict(self.governing_policy_ref),
            "governing_spec_refs": list(self.governing_spec_refs),
        }

    def as_object(self) -> CanonicalObject:
        lid = self.campaign_id if (self.campaign_id and self.campaign_id.startswith("successor_campaign_genesis_")) else None
        return CanonicalObject("successor_campaign_genesis", self.body(), logical_id=lid)

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class SuccessorCampaignSelectionDecision:
    predecessor_conclusion_ref: Any
    candidate_successor_campaign_refs: Sequence[Any]
    selected_successor_campaign_ref: Any
    resolution_basis_refs: Sequence[Any]
    governing_policy_ref: Any
    input_history_cut: dict
    decision_id: str | None = None

    def __post_init__(self):
        if self.decision_id is None:
            object.__setattr__(self, "decision_id", new_id("successor_campaign_selection_decision"))
        elif self.decision_id.startswith("successor_campaign_selection_decision_"):
            validate_id(self.decision_id, "successor_campaign_selection_decision")

        candidates = tuple(canonical_reference_set([_ref_dict(r) for r in self.candidate_successor_campaign_refs]))
        object.__setattr__(self, "candidate_successor_campaign_refs", candidates)

        selected = _ref_dict(self.selected_successor_campaign_ref)
        object.__setattr__(self, "selected_successor_campaign_ref", selected)

        # Normative rule: selected ref MUST belong to exact candidate set (R5.3 §14.5)
        cand_digests = {c.get("revision_digest") for c in candidates}
        if selected.get("revision_digest") not in cand_digests:
            raise ValidationError(
                "SELECTED_SUCCESSOR_NOT_IN_CANDIDATES",
                f"Selected successor {selected.get('revision_digest')} not in candidate set {cand_digests}",
            )

        object.__setattr__(
            self, "resolution_basis_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.resolution_basis_refs]))
        )

    def body(self) -> dict:
        return {
            "decision_id": self.decision_id or "selection_default",
            "predecessor_conclusion_ref": _ref_dict(self.predecessor_conclusion_ref),
            "candidate_successor_campaign_refs": list(self.candidate_successor_campaign_refs),
            "selected_successor_campaign_ref": dict(self.selected_successor_campaign_ref),
            "resolution_basis_refs": list(self.resolution_basis_refs),
            "governing_policy_ref": _ref_dict(self.governing_policy_ref),
            "input_history_cut": dict(self.input_history_cut),
        }

    def as_object(self) -> CanonicalObject:
        lid = self.decision_id if (self.decision_id and self.decision_id.startswith("successor_campaign_selection_decision_")) else None
        return CanonicalObject("successor_campaign_selection_decision", self.body(), logical_id=lid)

    @property
    def digest(self) -> str:
        return self.as_object().digest


def create_successor_campaign(
    predecessor_campaign_ref: Any,
    predecessor_conclusion_ref: Any,
    successor_trigger_ref: Any,
    source_generation_ref: Any,
    successor_input_history_cut: dict,
    challenge_freshness_policy_ref: Any,
    governing_policy_ref: Any,
    carried_forward_qualification_refs: Sequence[Any] = (),
    newly_required_obligation_refs: Sequence[Any] = (),
    governing_spec_refs: Sequence[Any] = (),
) -> SuccessorCampaignGenesis:
    """Create a successor campaign without mutating predecessor history."""
    return SuccessorCampaignGenesis(
        predecessor_campaign_ref=predecessor_campaign_ref,
        predecessor_conclusion_ref=predecessor_conclusion_ref,
        successor_trigger_ref=successor_trigger_ref,
        source_generation_ref=source_generation_ref,
        successor_input_history_cut=successor_input_history_cut,
        challenge_freshness_policy_ref=challenge_freshness_policy_ref,
        governing_policy_ref=governing_policy_ref,
        carried_forward_qualification_refs=carried_forward_qualification_refs,
        newly_required_obligation_refs=newly_required_obligation_refs,
        governing_spec_refs=governing_spec_refs,
    )


def select_successor_campaign(
    predecessor_conclusion_ref: Any,
    candidate_campaign_refs: Sequence[Any],
    selected_campaign_ref: Any,
    resolution_basis_refs: Sequence[Any],
    governing_policy_ref: Any,
    input_history_cut: dict,
) -> SuccessorCampaignSelectionDecision:
    """Resolve branch selection when competing successor campaigns exist."""
    return SuccessorCampaignSelectionDecision(
        predecessor_conclusion_ref=predecessor_conclusion_ref,
        candidate_successor_campaign_refs=candidate_campaign_refs,
        selected_successor_campaign_ref=selected_campaign_ref,
        resolution_basis_refs=resolution_basis_refs,
        governing_policy_ref=governing_policy_ref,
        input_history_cut=input_history_cut,
    )
