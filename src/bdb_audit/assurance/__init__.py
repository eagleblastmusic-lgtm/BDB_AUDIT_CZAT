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
from .residual_risk_finalization import install_residual_risk_finalization

# Finalization must carry the exact accepted residual-risk set that STOP saw.
# Zero-risk finalization remains the existing implementation; the installed
# adapter only handles the residual-risk path and post-STOP risk drift.
install_residual_risk_finalization(FinalizationService)
