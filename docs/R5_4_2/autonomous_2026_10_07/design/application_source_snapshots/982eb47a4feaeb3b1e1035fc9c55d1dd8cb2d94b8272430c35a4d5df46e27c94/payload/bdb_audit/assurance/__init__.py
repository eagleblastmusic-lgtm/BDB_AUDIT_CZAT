"""Assurance models, assessments, and lifecycle components."""
from .residual_risk import (
    ResidualRiskRecord,
    ResidualRiskRegister,
    ResidualRiskService,
    RISK_DISPOSITIONS,
    RISK_MATERIALITIES,
)
from .candidate_case import (
    CandidateAssuranceCase,
    CandidateAssuranceCaseBuilder,
)
from .challenger import (
    ChallengerAssignment,
    ChallengerResult,
    E5ChallengerOrchestrator,
    REQUIRED_BASELINE_CHALLENGER_TYPES,
    CHALLENGER_OUTCOME_STATUSES,
)
from .conclusion import (
    CampaignConclusion,
    FinalAssuranceCase,
    TERMINATION_STATES,
)
from .release import (
    ReleaseQualification,
    SuccessorCampaignGenesis,
    SuccessorCampaignSelectionDecision,
    ReleaseLifecycleManager,
    RELEASE_BASES,
    RELEASE_RESULTS,
)
from .finalization_service import FinalizationService
from . import residual_risk_finalization as _residual_risk_finalization_module
from .residual_risk_finalization import install_residual_risk_finalization
from .finalization_identity import install_full_identity_stop_lookup

# Finalization must carry the exact accepted residual-risk set that STOP saw.
# The identity adapter first reconstructs the full accepted StopInput identity
# from canonical history; the finalization adapter then propagates the exact
# risk set through the three existing prior-accepted boundaries.
install_full_identity_stop_lookup(_residual_risk_finalization_module)
install_residual_risk_finalization(FinalizationService)
