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
from .planner_compat import install_adaptive_e6_planner_compat

# Compatibility is deliberately limited to pure-planner construction.  The
# authoritative history-store boundary still re-proves canonical current STOP
# provenance before any E6 StageSpec can become accepted state.
install_adaptive_e6_planner_compat(AdaptiveE6Spec, AdaptiveE6Generator)

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
