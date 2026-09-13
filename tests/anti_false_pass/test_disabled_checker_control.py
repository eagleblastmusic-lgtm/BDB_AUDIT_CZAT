"""Tests for anti-false-PASS: Disabled checker, NOT_RUN checker, and Zero-cases controls (RU13-A)."""
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.qualification.receipts import ActualRunReceipt, QualificationReceipt
from bdb_audit.qualification.runner import (
    MANDATORY_QUALIFICATION_CHECKERS,
    MethodologyQualifier,
)


def test_mandatory_checker_not_run_cannot_award_qualified():
    """A mandatory checker marked NOT_RUN strictly prohibits QUALIFIED status."""
    qualifier = MethodologyQualifier(app_version="2.0.3", candidate_sha="a" * 40)

    # 10_same_environment_rebuild_identity is NOT_RUN
    checkers = {k: "PASS" for k in MANDATORY_QUALIFICATION_CHECKERS}
    checkers["10_same_environment_rebuild_identity"] = "NOT_RUN"

    eval_result = qualifier.evaluate_checker_receipts(checkers)
    assert eval_result["status"] == "INSUFFICIENT"
    assert eval_result["overall_outcome"] == "INSUFFICIENT_EVIDENCE"
    assert any("10_same_environment_rebuild_identity" in r for r in eval_result["unresolved_reasons"])

    # Attempting to directly construct a QualificationReceipt with QUALIFIED and NOT_RUN must fail closed
    with pytest.raises(ValidationError) as exc_info:
        QualificationReceipt(
            receipt_id="test_rcpt_1",
            candidate_sha="a" * 40,
            app_version="2.0.3",
            qualification_scope="TEST",
            status="QUALIFIED",
            overall_outcome="PASS",
            total_required_checkers=len(MANDATORY_QUALIFICATION_CHECKERS),
            evaluated_checkers_count=len(MANDATORY_QUALIFICATION_CHECKERS) - 1,
            checkers=checkers,
            denominator=len(MANDATORY_QUALIFICATION_CHECKERS),
        )
    assert "NOT_RUN_CHECKER_CANNOT_QUALIFY" in str(exc_info.value)


def test_missing_mandatory_checker_fails_closed():
    """A missing mandatory checker is treated as unexecuted and prevents qualification."""
    qualifier = MethodologyQualifier(app_version="2.0.3", candidate_sha="a" * 40)

    # Omit 'anti_bypass_suite'
    checkers = {k: "PASS" for k in MANDATORY_QUALIFICATION_CHECKERS if k != "anti_bypass_suite"}

    eval_result = qualifier.evaluate_checker_receipts(checkers)
    assert eval_result["status"] == "INSUFFICIENT"
    assert any("anti_bypass_suite" in r for r in eval_result["unresolved_reasons"])


def test_intentionally_disabled_critical_validator_fails_qualification():
    """If a critical validator is disabled (returns FAIL or non-PASS), qualification FAILS."""
    qualifier = MethodologyQualifier(app_version="2.0.3", candidate_sha="a" * 40)

    checkers = {k: "PASS" for k in MANDATORY_QUALIFICATION_CHECKERS}
    checkers["1_startup_integrity"] = "FAIL"

    eval_result = qualifier.evaluate_checker_receipts(checkers)
    assert eval_result["status"] == "FAILED"
    assert eval_result["overall_outcome"] == "FAIL"
    assert any("1_startup_integrity" in r for r in eval_result["unresolved_reasons"])


def test_zero_cases_evaluated_prohibits_pass_receipt():
    """An actual run receipt with 0 evaluated cases cannot claim PASS status."""
    with pytest.raises(ValidationError) as exc_info:
        ActualRunReceipt(
            receipt_id="zero_case_rcpt",
            benchmark_id="bm_test",
            target_id="target_test",
            checker_id="defect_detector",
            execution_timestamp="2026-09-13T00:00:00Z",
            exit_code=0,
            status="PASS",
            raw_output_digest="0" * 64,
            evaluated_cases_count=0,
            passed_cases_count=0,
            failed_cases_count=0,
        )
    assert "ZERO_CASES_PASS_FORBIDDEN" in str(exc_info.value)


def test_zero_cases_receipt_fails_qualification():
    """Even if checkers map claims PASS, a receipt with 0 evaluated cases fails qualification."""
    qualifier = MethodologyQualifier(app_version="2.0.3", candidate_sha="a" * 40)

    checkers = {k: "PASS" for k in MANDATORY_QUALIFICATION_CHECKERS}

    bad_receipt = ActualRunReceipt(
        receipt_id="rcpt_bad",
        benchmark_id="bm_test",
        target_id="target_test",
        checker_id="anti_bypass_suite",
        execution_timestamp="2026-09-13T00:00:00Z",
        exit_code=1,
        status="FAIL",
        raw_output_digest="0" * 64,
        evaluated_cases_count=0,
        passed_cases_count=0,
        failed_cases_count=0,
    )

    eval_result = qualifier.evaluate_checker_receipts(checkers, receipts=[bad_receipt])
    assert eval_result["status"] == "FAILED"
    assert any("anti_bypass_suite" in r for r in eval_result["unresolved_reasons"])
