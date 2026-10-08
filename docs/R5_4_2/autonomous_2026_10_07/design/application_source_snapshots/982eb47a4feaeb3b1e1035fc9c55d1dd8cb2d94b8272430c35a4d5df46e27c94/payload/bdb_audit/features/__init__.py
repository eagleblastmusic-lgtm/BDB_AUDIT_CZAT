"""RU11 functional verification public API."""
from .discovery import discover_api_features, discover_cli_features, discover_features
from .models import (
    BehaviorAssessment,
    BehaviorCase,
    FeatureRevision,
    OracleAssessment,
    TestabilityAssessment,
    VerificationPlan,
)
from .oracles import qualify_oracle
from .planner import build_verification_plan
from .projection import feature_status_matrix, project_feature_status
from .testability import assess_testability
from .verification import execute_verification_plan

__all__ = [
    "FeatureRevision", "BehaviorCase", "OracleAssessment", "TestabilityAssessment",
    "VerificationPlan", "BehaviorAssessment", "discover_cli_features", "discover_api_features",
    "discover_features", "qualify_oracle", "assess_testability", "build_verification_plan",
    "execute_verification_plan", "project_feature_status", "feature_status_matrix",
]
