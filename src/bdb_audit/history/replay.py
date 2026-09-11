"""Replay Capsule manifest and Independent Replay Record models and verification (WP-F4-10 / R5.3 §65, §66)."""
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
import hashlib
import uuid

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.registry import canonical_reference_set

REPLAY_STATUSES = {"REPRODUCED", "NOT_REPRODUCED", "INCONCLUSIVE", "BLOCKED", "HARNESS_FAILURE"}


def _ref_dict(ref_or_obj: Any) -> dict:
    if hasattr(ref_or_obj, "as_ref"):
        ref = ref_or_obj.as_ref()
        return ref if isinstance(ref, dict) else ref.as_dict()
    if hasattr(ref_or_obj, "as_dict"):
        return ref_or_obj.as_dict()
    if isinstance(ref_or_obj, dict):
        return ref_or_obj
    raise ValidationError("INVALID_REFERENCE", str(ref_or_obj))


@dataclass(frozen=True)
class ReplayCapsule:
    finding_or_claim_revision_ref: Any
    subject_baseline_ref: Any
    environment_profile_ref: Any
    dependency_set_ref: Any
    harness_ref: Any
    generator_profile_ref: Any
    command_spec: dict
    expected_invariant_ref: Any
    expected_observable: dict
    producer_ref: Any
    fixture_refs: Sequence[Any] = ()
    observer_requirements: Sequence[str] = ()
    cleanup_spec: dict = field(default_factory=dict)
    artifact_raw_digests: Sequence[str] = ()
    seed_ref: Any = None
    repro_capsule_id: str | None = None

    def __post_init__(self):
        if self.repro_capsule_id is None:
            object.__setattr__(self, "repro_capsule_id", f"capsule_{uuid.uuid4().hex[:16]}")

        object.__setattr__(
            self, "fixture_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.fixture_refs]))
        )
        object.__setattr__(
            self, "observer_requirements",
            tuple(sorted(set(self.observer_requirements)))
        )
        object.__setattr__(
            self, "artifact_raw_digests",
            tuple(sorted(set(self.artifact_raw_digests)))
        )

    def body(self) -> dict:
        data = {
            "repro_capsule_id": self.repro_capsule_id or "capsule_default",
            "finding_or_claim_revision_ref": _ref_dict(self.finding_or_claim_revision_ref),
            "subject_baseline_ref": _ref_dict(self.subject_baseline_ref),
            "environment_profile_ref": _ref_dict(self.environment_profile_ref),
            "dependency_set_ref": _ref_dict(self.dependency_set_ref),
            "harness_ref": _ref_dict(self.harness_ref),
            "generator_profile_ref": _ref_dict(self.generator_profile_ref),
            "command_spec": dict(self.command_spec),
            "expected_invariant_ref": _ref_dict(self.expected_invariant_ref),
            "expected_observable": dict(self.expected_observable),
            "producer_ref": _ref_dict(self.producer_ref),
            "fixture_refs": list(self.fixture_refs),
            "observer_requirements": list(self.observer_requirements),
            "cleanup_spec": dict(self.cleanup_spec),
            "artifact_raw_digests": list(self.artifact_raw_digests),
        }
        if self.seed_ref is not None:
            data["seed_ref"] = _ref_dict(self.seed_ref)
        return data

    def as_dict(self) -> dict:
        return self.body()

    def as_ref(self) -> dict:
        return {
            "kind": "replay_capsule",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::replay_capsule/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_bytes(self.body())).hexdigest()


@dataclass(frozen=True)
class IndependentReplayRecord:
    repro_capsule_ref: Any
    replay_executor_ref: Any
    actual_subject_ref: Any
    actual_environment_ref: Any
    actual_harness_ref: Any
    actual_dependencies_ref: Any
    dependency_independence_assessment_ref: Any
    status: str
    match_expected: bool
    observation_refs: Sequence[Any] = ()
    replay_record_id: str | None = None

    def __post_init__(self):
        if self.replay_record_id is None:
            object.__setattr__(self, "replay_record_id", f"record_{uuid.uuid4().hex[:16]}")

        if self.status not in REPLAY_STATUSES:
            raise ValidationError("INVALID_REPLAY_STATUS", str(self.status))

        # Replayability does not imply independence (R5.3 §65, §66)
        if self.dependency_independence_assessment_ref is None:
            raise ValidationError(
                "INDEPENDENCE_ASSESSMENT_REQUIRED",
                "Independent replay record requires claim-relative dependency independence assessment",
            )

        object.__setattr__(
            self, "observation_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.observation_refs]))
        )

    def body(self) -> dict:
        return {
            "replay_record_id": self.replay_record_id or "record_default",
            "repro_capsule_ref": _ref_dict(self.repro_capsule_ref),
            "replay_executor_ref": _ref_dict(self.replay_executor_ref),
            "actual_subject_ref": _ref_dict(self.actual_subject_ref),
            "actual_environment_ref": _ref_dict(self.actual_environment_ref),
            "actual_harness_ref": _ref_dict(self.actual_harness_ref),
            "actual_dependencies_ref": _ref_dict(self.actual_dependencies_ref),
            "dependency_independence_assessment_ref": _ref_dict(self.dependency_independence_assessment_ref),
            "status": self.status,
            "match_expected": self.match_expected,
            "observation_refs": list(self.observation_refs),
        }

    def as_dict(self) -> dict:
        return self.body()

    def as_ref(self) -> dict:
        return {
            "kind": "independent_replay_record",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::independent_replay_record/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_bytes(self.body())).hexdigest()


def execute_replay_verification(
    capsule: ReplayCapsule,
    replay_executor_ref: Any,
    actual_subject_ref: Any,
    actual_environment_ref: Any,
    actual_harness_ref: Any,
    actual_dependencies_ref: Any,
    independence_assessment_ref: Any,
    observed_result: dict,
    observation_refs: Sequence[Any] = (),
    harness_succeeded: bool = True,
) -> IndependentReplayRecord:
    """Execute and qualify replay verification against an immutable ReplayCapsule."""
    if not harness_succeeded:
        status = "HARNESS_FAILURE"
        match_expected = False
    else:
        # Compare observed result with expected_observable
        expected = capsule.expected_observable
        match_expected = (observed_result == expected)
        status = "REPRODUCED" if match_expected else "NOT_REPRODUCED"

    return IndependentReplayRecord(
        repro_capsule_ref=capsule.as_ref(),
        replay_executor_ref=replay_executor_ref,
        actual_subject_ref=actual_subject_ref,
        actual_environment_ref=actual_environment_ref,
        actual_harness_ref=actual_harness_ref,
        actual_dependencies_ref=actual_dependencies_ref,
        dependency_independence_assessment_ref=independence_assessment_ref,
        status=status,
        match_expected=match_expected,
        observation_refs=observation_refs,
    )
