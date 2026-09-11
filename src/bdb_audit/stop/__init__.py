"""BDB Audit v2 STOP gate and completion package (M24 / PR-027)."""
from .models import (
    LaneCompletion,
    StageCompletion,
    StopInput,
    StopEvaluation,
    Snapshot,
)
from .evaluator import (
    evaluate_stop,
    validate_intermediate_stop,
    validate_stop_snapshot_binding,
)
from .e6 import (
    AdaptiveE6Spec,
    AdaptiveE6Generator,
)

__all__ = [
    "LaneCompletion",
    "StageCompletion",
    "StopInput",
    "StopEvaluation",
    "Snapshot",
    "evaluate_stop",
    "validate_intermediate_stop",
    "validate_stop_snapshot_binding",
    "AdaptiveE6Spec",
    "AdaptiveE6Generator",
]
