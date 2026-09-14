"""Astra/R5.3 external-stage lane profile corrections.

The first transport draft used shortened lane slots.  The normative orchestration
uses fully qualified E2/E3 slot names, so the continuation path installs those
names before creating any new durable assignments.  Existing accepted history is
never rewritten; this affects only new post-E1 work on the continuation branch.
"""
from __future__ import annotations

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


def apply_astra_stage_profiles() -> None:
    """Install the branch-local lane profile for future assignments."""
    stage_transport.POST_E1_STAGE_LANES.update(ASTRA_POST_E1_STAGE_LANES)


__all__ = ["ASTRA_POST_E1_STAGE_LANES", "apply_astra_stage_profiles"]
