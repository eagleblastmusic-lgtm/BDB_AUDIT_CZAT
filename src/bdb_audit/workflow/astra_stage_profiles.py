"""Astra/R5.3 external-stage lane profile corrections.

The continuation branch keeps user-facing lane order separate from canonical
reference-set order.  StageRun reference arrays are canonicalized according to
the pinned registry without changing the semantic/UI order of the lane batch.
"""
from __future__ import annotations

import hashlib
from typing import Any

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, CommandEnvelope, HistoryCut
from . import stage_transport
from .stage_transport import StageLaneDefinition


ASTRA_POST_E1_STAGE_LANES: dict[str, tuple[StageLaneDefinition, ...]] = {
    "E2": (
        StageLaneDefinition(
            "E2-CONVERGENCE",
            "Claim convergence, quarantine normalization and evidence cross-review",
            "CONVERGENCE_AND_CROSS_REVIEW",
            "DECLARED",
        ),
        StageLaneDefinition(
            "E2-ADJUDICATION",
            "Four-axis finding adjudication and contradiction review",
            "FOUR_AXIS_ADJUDICATION",
            "DECLARED",
        ),
    ),
    "E3": (
        StageLaneDefinition(
            "E3-X",
            "Security, Authority & Trust blind novelty search",
            "AUTHORITY_TRUST_NOVELTY_SEARCH",
            "ENFORCED",
        ),
        StageLaneDefinition(
            "E3-Y",
            "State, Data, Catalog & Recovery blind novelty search",
            "STATE_CATALOG_RECOVERY_SEARCH",
            "ENFORCED",
        ),
        StageLaneDefinition(
            "E3-Z",
            "Frontend, Concurrency, Resources & Cross-Layer blind novelty search",
            "CROSS_LAYER_CONCURRENCY_SEARCH",
            "ENFORCED",
        ),
    ),
    "E4": (
        StageLaneDefinition(
            "E4-DEEPEN",
            "Deepening, state, recovery and concurrency verification",
            "DEEPEN",
            "DECLARED",
        ),
    ),
    "E5": (
        StageLaneDefinition(
            "E5-CANDIDATE",
            "Candidate assurance synthesis",
            "CANDIDATE_SYNTHESIS",
            "DECLARED",
        ),
        StageLaneDefinition(
            "E5-SKEPTIC",
            "False-positive skeptic",
            "FALSE_POSITIVE_SKEPTIC",
            "DECLARED",
            "FALSE_POSITIVE_SKEPTIC",
        ),
        StageLaneDefinition(
            "E5-HUNTER",
            "False-negative hunter",
            "FALSE_NEGATIVE_HUNTER",
            "DECLARED",
            "FALSE_NEGATIVE_HUNTER",
        ),
    ),
    "E6": (
        StageLaneDefinition(
            "E6-VERIFY",
            "Targeted verification of remaining material gaps",
            "TARGETED_VERIFICATION",
            "DECLARED",
        ),
    ),
}


class AstraStageAssignmentService(stage_transport.StageAssignmentService):
    """Stage assignment service with registry-canonical StageRun ref arrays."""

    def _stage_run(
        self,
        stage: str,
        cut: dict[str, Any],
        stage_spec: dict[str, Any],
        source: dict[str, Any],
        prior_commit: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        matching = [
            row
            for row in self.store.accepted_records("stage_run", cut)
            if stage_transport._same_ref(row["body"].get("stage_spec_ref"), stage_spec["ref"])
        ]
        if len(matching) > 1:
            raise ValidationError("MULTIPLE_STAGE_RUNS_FOR_STAGE", stage)
        if matching:
            return matching[0], cut

        predecessor = {
            "E2": "E1",
            "E3": "E2",
            "E4": "E3",
            "E5": "E4",
            "E6": "E5",
        }.get(stage)
        predecessor_refs: list[dict[str, Any]] = []
        if predecessor:
            stage_specs = self.store.accepted_records("stage_spec", cut)
            by_digest = {
                row["ref"]["revision_digest"]: row["body"].get("stage_key")
                for row in stage_specs
            }
            candidates = []
            for row in self.store.accepted_records("stage_completion", cut):
                spec_ref = row["body"].get("stage_spec_ref", {})
                if by_digest.get(spec_ref.get("revision_digest")) == predecessor:
                    candidates.append(row)
            if not candidates:
                raise ValidationError("PREDECESSOR_STAGE_NOT_COMPLETED", predecessor)
            predecessor_refs = canonical_reference_set([
                stage_transport._ref(candidates[-1], "PRIOR_ACCEPTED_ONLY")
            ])

        required_slot_refs = canonical_reference_set([
            stage_transport._external_ref(
                "result_slot_contract_ref",
                f"{stage}:{slot}",
                "HISTORY_CONTEXT_BINDING",
            )
            for slot in stage_transport.stage_slots(stage)
        ])
        stage_run = CanonicalObject(
            "stage_run",
            {
                "stage_run_id": f"stage_run_{stage}_{hashlib.sha256(canonical_bytes(cut)).hexdigest()[:16]}",
                "campaign_ref": cut["campaign_id"],
                "stage_spec_ref": stage_transport._ref(stage_spec, "HISTORY_CONTEXT_BINDING"),
                "source_generation_ref": stage_transport._ref(source, "PRIOR_ACCEPTED_ONLY"),
                "creation_input_history_cut": cut,
                "assigned_history_cut": cut,
                "predecessor_stage_completion_refs": predecessor_refs,
                "required_lane_slot_contract_refs": required_slot_refs,
            },
        )
        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        command = CommandEnvelope(
            command_id=stage_transport._command_id(f"stage_run:{stage}:{head.commit_hash}"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit["governing_policy_ref"],
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ())),
            idempotency_scope=f"stage_run:{stage}:{stage_run.digest}",
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=[stage_run],
            expected_head=head,
        )
        new_cut = HistoryCut.accepted(
            accepted.head,
            accepted.commit.governing_policy_ref,
            accepted.commit.governing_spec_refs,
        ).as_dict()
        record = self.store.resolve_accepted(stage_run.as_ref().as_dict(), new_cut)
        return record, new_cut


def apply_astra_stage_profiles() -> None:
    """Install branch-local lane and assignment profiles for future work."""
    stage_transport.POST_E1_STAGE_LANES.update(ASTRA_POST_E1_STAGE_LANES)
    stage_transport.StageAssignmentService = AstraStageAssignmentService


__all__ = [
    "ASTRA_POST_E1_STAGE_LANES",
    "AstraStageAssignmentService",
    "apply_astra_stage_profiles",
]
