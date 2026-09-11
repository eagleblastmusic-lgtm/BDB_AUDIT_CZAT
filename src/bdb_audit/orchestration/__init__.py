"""Small, pure orchestration primitives used by the F2 reference profile."""

from .fsm import (
    CampaignState,
    StageRunState,
    LaneRunState,
    AttemptState,
    TransitionFact,
    legal_transition,
    project_states,
)

__all__ = [
    "CampaignState", "StageRunState", "LaneRunState", "AttemptState",
    "TransitionFact", "legal_transition", "project_states",
]
