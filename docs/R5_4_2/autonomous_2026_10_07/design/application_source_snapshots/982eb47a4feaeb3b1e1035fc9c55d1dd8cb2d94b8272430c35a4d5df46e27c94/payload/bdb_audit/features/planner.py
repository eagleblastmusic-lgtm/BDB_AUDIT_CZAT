"""RU11 verification-plan construction."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..runner.environments import environment_manifest, source_manifest
from ..runner.specs import CapabilityProfile
from .models import BehaviorCase, FeatureRevision, OracleAssessment, VerificationPlan
from .testability import assess_testability


def build_verification_plan(
    feature: FeatureRevision,
    cases: Sequence[BehaviorCase],
    oracles: Sequence[OracleAssessment],
    source_root: str | Path,
    *,
    profile: CapabilityProfile | None = None,
) -> VerificationPlan:
    runner_profile = profile or CapabilityProfile()
    source = source_manifest(source_root)
    env = environment_manifest(source_root, runner_profile)
    return VerificationPlan(
        feature=feature,
        cases=tuple(cases),
        oracles=tuple(oracles),
        testability=assess_testability(feature),
        source_manifest_digest=source["manifest_digest"],
        environment_manifest_digest=env["manifest_digest"],
    )


__all__ = ["build_verification_plan"]
