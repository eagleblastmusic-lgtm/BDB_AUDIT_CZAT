"""BDB Audit v2 STOP gate and completion package (M24 / PR-027)."""
from .models import (
    LaneCompletion,
    StageCompletion,
    StopInput,
    StopEvaluation,
)
from .evaluator import (
    evaluate_stop,
    validate_intermediate_stop,
)

__all__ = [
    "LaneCompletion",
    "StageCompletion",
    "StopInput",
    "StopEvaluation",
    "evaluate_stop",
    "validate_intermediate_stop",
]
