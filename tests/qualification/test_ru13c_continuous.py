from __future__ import annotations

from pathlib import Path

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.qualification.continuous import (
    HoldoutExposureRecord,
    assign_holdout,
    oracle_challenge_matrix,
    run_continuous_qualification,
    transition_holdout,
    verify_continuous_qualification,
)
from bdb_audit.qualification.holdout_corpus import holdout_corpus_digest


def test_ru13c_holdout_cannot_be_reused_for_same_evaluator() -> None:
    digest = holdout_corpus_digest()
    assigned = assign_holdout((), "case-a", "evaluator-a", digest)
    assert assigned.state == "ASSIGNED"
    with pytest.raises(ValidationError, match="HOLDOUT_REUSE_FORBIDDEN"):
        assign_holdout((assigned,), "case-a", "evaluator-a", digest)
    other = assign_holdout((assigned,), "case-a", "evaluator-b", digest)
    assert other.evaluator_profile == "evaluator-b"


def test_ru13c_holdout_lifecycle_is_monotonic() -> None:
    record = HoldoutExposureRecord("case-a", "evaluator", "UNSEEN", holdout_corpus_digest())
    for state in ("ASSIGNED", "POTENTIALLY_EXPOSED", "CONSUMED", "RETIRED"):
        record = transition_holdout(record, state)
    assert record.state == "RETIRED"
    with pytest.raises(ValidationError, match="HOLDOUT_TRANSITION_INVALID"):
        transition_holdout(record, "ASSIGNED")


def test_ru13c_oracle_challenge_matrix_is_two_by_two_and_weak_never_qualifies() -> None:
    matrix = oracle_challenge_matrix({"v21_holdout_clean": "CLEAN", "v21_holdout_corrupt": "DEFECTIVE"})
    assert {(row["target_class"], row["oracle_strength"]) for row in matrix} == {
        ("CLEAN", "STRONG"), ("CLEAN", "WEAK"), ("DEFECTIVE", "STRONG"), ("DEFECTIVE", "WEAK")
    }
    assert all(row["state"] == "BLOCKED" for row in matrix if row["oracle_strength"] == "WEAK")
    assert all(row["state"] == "KILLED" for row in matrix if row["oracle_strength"] == "STRONG")


def test_ru13c_continuous_holdout_runs_real_public_boundaries_and_verifies(tmp_path: Path) -> None:
    result = run_continuous_qualification(tmp_path / "holdout", "independent-profile")
    assert result["status"] == "QUALIFIED"
    assert len(result["actual_receipt_digests"]) == 3
    assert all(item["state"] == "RETIRED" for item in result["exposure_records"])
    verified = verify_continuous_qualification(result)
    assert verified["status"] == "PASS"


def test_ru13c_tamper_changes_digest_and_fails_verification(tmp_path: Path) -> None:
    result = run_continuous_qualification(tmp_path / "holdout", "independent-profile")
    result["observed_results"]["v21_holdout_corrupt"] = "CLEAN"
    with pytest.raises(ValidationError, match="CONTINUOUS_RESULT_DIGEST_MISMATCH"):
        verify_continuous_qualification(result)
