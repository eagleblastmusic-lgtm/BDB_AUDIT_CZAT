"""RU13-C continuous methodology qualification, holdout exposure, and mutation controls."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .holdout_corpus import holdout_cases, holdout_corpus_digest
from .holdout_truth import holdout_truth_manifests
from .real_target_harness import _execute_case, score_reference_controls

HOLDOUT_STATES = {"UNSEEN", "ASSIGNED", "POTENTIALLY_EXPOSED", "CONSUMED", "RETIRED"}
_MUTATION_STATES = {"KILLED", "SURVIVED", "NOT_ACTIVATED", "INVALID", "HARNESS_FAILURE", "BLOCKED"}
_ALLOWED_TRANSITIONS = {
    "UNSEEN": {"ASSIGNED"},
    "ASSIGNED": {"POTENTIALLY_EXPOSED"},
    "POTENTIALLY_EXPOSED": {"CONSUMED"},
    "CONSUMED": {"RETIRED"},
    "RETIRED": set(),
}


@dataclass(frozen=True)
class HoldoutExposureRecord:
    benchmark_id: str
    evaluator_profile: str
    state: str
    corpus_digest: str

    def __post_init__(self) -> None:
        if not self.benchmark_id or not self.evaluator_profile or self.state not in HOLDOUT_STATES:
            raise ValidationError("HOLDOUT_EXPOSURE_INVALID")
        if len(self.corpus_digest) != 64:
            raise ValidationError("HOLDOUT_CORPUS_DIGEST_INVALID")

    def as_dict(self) -> dict[str, str]:
        return {
            "benchmark_id": self.benchmark_id,
            "evaluator_profile": self.evaluator_profile,
            "state": self.state,
            "corpus_digest": self.corpus_digest,
        }


@dataclass(frozen=True)
class MutationChallengeResult:
    case_id: str
    target_class: str
    oracle_strength: str
    state: str
    observed_label: str

    def __post_init__(self) -> None:
        if self.target_class not in {"CLEAN", "DEFECTIVE"}:
            raise ValidationError("MUTATION_TARGET_CLASS_INVALID")
        if self.oracle_strength not in {"STRONG", "WEAK"}:
            raise ValidationError("MUTATION_ORACLE_STRENGTH_INVALID")
        if self.state not in _MUTATION_STATES:
            raise ValidationError("MUTATION_STATE_INVALID")

    def as_dict(self) -> dict[str, str]:
        return {
            "case_id": self.case_id,
            "target_class": self.target_class,
            "oracle_strength": self.oracle_strength,
            "state": self.state,
            "observed_label": self.observed_label,
        }


def transition_holdout(record: HoldoutExposureRecord, next_state: str) -> HoldoutExposureRecord:
    if next_state not in HOLDOUT_STATES or next_state not in _ALLOWED_TRANSITIONS[record.state]:
        raise ValidationError("HOLDOUT_TRANSITION_INVALID", f"{record.state}->{next_state}")
    return HoldoutExposureRecord(record.benchmark_id, record.evaluator_profile, next_state, record.corpus_digest)


def assign_holdout(
    existing: Sequence[HoldoutExposureRecord], benchmark_id: str, evaluator_profile: str, corpus_digest: str
) -> HoldoutExposureRecord:
    same = [item for item in existing if item.benchmark_id == benchmark_id and item.evaluator_profile == evaluator_profile]
    if same:
        # Once assigned/exposed/consumed/retired, the same holdout is never
        # representable as UNSEEN for the same evaluation path again.
        raise ValidationError("HOLDOUT_REUSE_FORBIDDEN", benchmark_id)
    return transition_holdout(HoldoutExposureRecord(benchmark_id, evaluator_profile, "UNSEEN", corpus_digest), "ASSIGNED")


def _challenge(case_id: str, target_class: str, oracle_strength: str, observed: str) -> MutationChallengeResult:
    if oracle_strength == "WEAK":
        state = "BLOCKED"
    elif target_class == "DEFECTIVE":
        state = "KILLED" if observed == "DEFECTIVE" else "SURVIVED"
    else:
        state = "KILLED" if observed == "CLEAN" else "SURVIVED"
    return MutationChallengeResult(case_id, target_class, oracle_strength, state, observed)


def oracle_challenge_matrix(observed: Mapping[str, str]) -> list[dict[str, str]]:
    clean = str(observed.get("v21_holdout_clean", "UNKNOWN"))
    defective = str(observed.get("v21_holdout_corrupt", "UNKNOWN"))
    results = (
        _challenge("clean_strong", "CLEAN", "STRONG", clean),
        _challenge("clean_weak", "CLEAN", "WEAK", clean),
        _challenge("defective_strong", "DEFECTIVE", "STRONG", defective),
        _challenge("defective_weak", "DEFECTIVE", "WEAK", defective),
    )
    return [item.as_dict() for item in results]


def _canonical_metrics(metrics: Any) -> dict[str, Any]:
    body = metrics.to_dict()
    for key in ("precision", "recall", "anti_bypass_rate"):
        value = body.get(key)
        if not isinstance(value, float):
            raise ValidationError("CONTINUOUS_METRIC_RATIO_INVALID", key)
        body[key] = f"{value:.4f}"
    return body


def _digest(body: Mapping[str, Any]) -> str:
    value = dict(body)
    value.pop("result_digest", None)
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def run_continuous_qualification(workspace: str | Path, evaluator_profile: str) -> dict[str, Any]:
    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    cases = holdout_cases()
    corpus_digest = holdout_corpus_digest(cases)
    exposure: list[HoldoutExposureRecord] = []
    observed: dict[str, str] = {}
    receipt_digests: list[str] = []

    # Execution sees public case bodies only. Oracle truth is imported after all
    # actual public-boundary observations have been collected.
    for case in cases:
        record = assign_holdout(exposure, case.case_id, evaluator_profile, corpus_digest)
        record = transition_holdout(record, "POTENTIALLY_EXPOSED")
        label, receipt = _execute_case(root, case)
        record = transition_holdout(record, "CONSUMED")
        record = transition_holdout(record, "RETIRED")
        exposure.append(record)
        observed[case.target_id] = label
        receipt_digests.append(receipt.receipt_digest())

    manifests = holdout_truth_manifests()
    metrics = score_reference_controls(manifests, observed)
    challenge = oracle_challenge_matrix(observed)
    strong_results = [item for item in challenge if item["oracle_strength"] == "STRONG"]
    mutation_ok = bool(strong_results) and all(item["state"] == "KILLED" for item in strong_results)
    qualified = metrics.is_methodology_qualified and mutation_ok
    body: dict[str, Any] = {
        "schema_version": "RU13C-CONTINUOUS-QUALIFICATION-1",
        "status": "QUALIFIED" if qualified else "FAILED",
        "evaluator_profile": evaluator_profile,
        "corpus_digest": corpus_digest,
        "truth_manifest_digests": [item.manifest_digest() for item in manifests],
        "observed_results": dict(sorted(observed.items())),
        "actual_receipt_digests": receipt_digests,
        "exposure_records": [item.as_dict() for item in exposure],
        "metrics": _canonical_metrics(metrics),
        "oracle_challenge_matrix": challenge,
    }
    body["result_digest"] = _digest(body)
    return body


def verify_continuous_qualification(result: Mapping[str, Any]) -> dict[str, Any]:
    if result.get("schema_version") != "RU13C-CONTINUOUS-QUALIFICATION-1":
        raise ValidationError("CONTINUOUS_RESULT_SCHEMA_INVALID")
    if result.get("result_digest") != _digest(result):
        raise ValidationError("CONTINUOUS_RESULT_DIGEST_MISMATCH")
    if result.get("corpus_digest") != holdout_corpus_digest():
        raise ValidationError("CONTINUOUS_CORPUS_DIGEST_MISMATCH")
    manifests = holdout_truth_manifests()
    expected_truth = [item.manifest_digest() for item in manifests]
    if result.get("truth_manifest_digests") != expected_truth:
        raise ValidationError("CONTINUOUS_TRUTH_PARTITION_MISMATCH")
    observed = result.get("observed_results")
    if not isinstance(observed, dict):
        raise ValidationError("CONTINUOUS_OBSERVED_RESULTS_REQUIRED")
    metrics = score_reference_controls(manifests, {str(k): str(v) for k, v in observed.items()})
    if result.get("metrics") != _canonical_metrics(metrics):
        raise ValidationError("CONTINUOUS_METRICS_MISMATCH")
    challenge = oracle_challenge_matrix({str(k): str(v) for k, v in observed.items()})
    if result.get("oracle_challenge_matrix") != challenge:
        raise ValidationError("CONTINUOUS_CHALLENGE_MISMATCH")
    records = result.get("exposure_records")
    if not isinstance(records, list) or len(records) != len(holdout_cases()):
        raise ValidationError("CONTINUOUS_HOLDOUT_DENOMINATOR_MISMATCH")
    if any(not isinstance(item, dict) or item.get("state") != "RETIRED" for item in records):
        raise ValidationError("CONTINUOUS_HOLDOUT_NOT_RETIRED")
    strong = [item for item in challenge if item["oracle_strength"] == "STRONG"]
    expected = "QUALIFIED" if metrics.is_methodology_qualified and all(item["state"] == "KILLED" for item in strong) else "FAILED"
    if result.get("status") != expected:
        raise ValidationError("CONTINUOUS_STATUS_MISMATCH")
    return {"status": "PASS" if expected == "QUALIFIED" else "FAIL", "qualification_status": expected, "result_digest": result["result_digest"], "corpus_digest": result["corpus_digest"]}


__all__ = [
    "HoldoutExposureRecord", "MutationChallengeResult", "transition_holdout", "assign_holdout",
    "oracle_challenge_matrix", "run_continuous_qualification", "verify_continuous_qualification",
]
