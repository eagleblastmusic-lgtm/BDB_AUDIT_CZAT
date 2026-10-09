"""BDB Audit v2 STOP gate and completion package (M24 / PR-027)."""
from .models import (
    LaneCompletion,
    StageCompletion,
    StopInput,
    StopEvaluation,
    Snapshot,
)
from . import evaluator as _evaluator_module
from .evaluator import validate_intermediate_stop
from .e6 import (
    AdaptiveE6Spec,
    AdaptiveE6Generator,
)
from .planner_compat import install_adaptive_e6_planner_compat
from .input_builder import StopInputBuilder
from .residual_risk_projection import install_residual_risk_stop_projection
from .residual_risk_evaluator import install_residual_risk_evaluator

# Compatibility is deliberately limited to pure-planner construction. The
# authoritative history-store boundary still re-proves canonical current STOP
# provenance before any E6 StageSpec can become accepted state.
install_adaptive_e6_planner_compat(AdaptiveE6Spec, AdaptiveE6Generator)

# Residual-risk projection is authoritative input preparation, not caller
# supplied readiness. The history-store equality validator independently
# re-proves the exact risk set before an accepted StopInput can be durable.
install_residual_risk_stop_projection(StopInputBuilder)
install_residual_risk_evaluator(_evaluator_module)
evaluate_stop = _evaluator_module.evaluate_stop
validate_stop_snapshot_binding = _evaluator_module.validate_stop_snapshot_binding

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
