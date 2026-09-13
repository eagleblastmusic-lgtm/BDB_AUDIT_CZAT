"""Tests for benchmark manifests, actual run receipts, and methodology metrics (RU13-A)."""
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.qualification.methodology_metrics import MethodologyMetrics
from bdb_audit.qualification.receipts import (
    ActualRunReceipt,
    BenchmarkManifest,
    QualificationReceipt,
)
from bdb_audit.qualification.runner import MethodologyQualifier


def test_benchmark_manifest_separate_truth_partition():
    """BenchmarkManifest stores expected_label separately with immutable digests."""
    manifest = BenchmarkManifest(
        benchmark_id="bm_001",
        target_id="target_alpha",
        target_sha="a" * 40,
        expected_label="DEFECTIVE",
        defect_id="DEFECT_AUTH_BYPASS",
        split_membership="HOLDOUT",
        domain_tags=("AUTH", "SESSION"),
    )
    digest1 = manifest.manifest_digest()
    assert len(digest1) == 64

    # The manifest digest changes if expected_label is different
    manifest2 = BenchmarkManifest(
        benchmark_id="bm_001",
        target_id="target_alpha",
        target_sha="a" * 40,
        expected_label="CLEAN",
        defect_id="DEFECT_AUTH_BYPASS",
        split_membership="HOLDOUT",
        domain_tags=("AUTH", "SESSION"),
    )
    assert manifest2.manifest_digest() != digest1


def test_actual_run_receipt_determinism():
    """ActualRunReceipt produces deterministic digests of execution evidence."""
    receipt = ActualRunReceipt(
        receipt_id="rcpt_001",
        benchmark_id="bm_001",
        target_id="target_alpha",
        checker_id="auth_checker",
        execution_timestamp="2026-09-13T02:00:00Z",
        exit_code=0,
        status="PASS",
        raw_output_digest="b" * 64,
        evaluated_cases_count=10,
        passed_cases_count=10,
        failed_cases_count=0,
    )
    d1 = receipt.receipt_digest()
    d2 = receipt.receipt_digest()
    assert d1 == d2
    assert len(d1) == 64


def test_methodology_metrics_explicit_denominator():
    """MethodologyMetrics enforces explicit positive denominator and fails on unexecuted targets."""
    # Complete, perfect metrics
    metrics = MethodologyMetrics(
        total_targets=5,
        evaluated_targets=5,
        true_positives=2,
        false_positives=0,
        true_negatives=3,
        false_negatives=0,
        unsupported_cases=0,
        unknown_cases=0,
        anti_bypass_total=10,
        anti_bypass_passed=10,
        denominator=5,
    )
    assert metrics.is_methodology_qualified is True
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.anti_bypass_rate == 1.0

    # Unexecuted targets -> CANNOT qualify
    incomplete_metrics = MethodologyMetrics(
        total_targets=5,
        evaluated_targets=4,  # 1 target unexecuted!
        true_positives=2,
        false_positives=0,
        true_negatives=2,
        false_negatives=0,
        denominator=5,
        anti_bypass_total=10,
        anti_bypass_passed=10,
    )
    assert incomplete_metrics.is_methodology_qualified is False

    # False negative on defect -> CANNOT qualify
    fn_metrics = MethodologyMetrics(
        total_targets=5,
        evaluated_targets=5,
        true_positives=1,
        false_positives=0,
        true_negatives=3,
        false_negatives=1,  # Defect missed!
        denominator=5,
        anti_bypass_total=10,
        anti_bypass_passed=10,
    )
    assert fn_metrics.is_methodology_qualified is False

    # Failed anti-bypass check -> CANNOT qualify
    bypass_failed_metrics = MethodologyMetrics(
        total_targets=5,
        evaluated_targets=5,
        true_positives=2,
        false_positives=0,
        true_negatives=3,
        false_negatives=0,
        denominator=5,
        anti_bypass_total=10,
        anti_bypass_passed=9,  # 1 anti-bypass check failed!
    )
    assert bypass_failed_metrics.is_methodology_qualified is False


def test_benchmark_scoring_separate_labels():
    """Scorer compares actual results against hidden benchmark labels without exposing them to system."""
    benchmarks = [
        BenchmarkManifest("bm1", "t1", "1" * 40, expected_label="CLEAN"),
        BenchmarkManifest("bm2", "t2", "2" * 40, expected_label="DEFECTIVE"),
        BenchmarkManifest("bm3", "t3", "3" * 40, expected_label="UNSUPPORTED"),
    ]

    # Pipeline evaluated t1 as CLEAN, t2 as DEFECTIVE, t3 as UNSUPPORTED
    actual_results = {
        "t1": "CLEAN",
        "t2": "DEFECTIVE",
        "t3": "UNSUPPORTED",
    }

    metrics = MethodologyQualifier.score_benchmark_corpus(benchmarks, actual_results)
    assert metrics.total_targets == 3
    assert metrics.evaluated_targets == 3
    assert metrics.true_negatives == 1
    assert metrics.true_positives == 1
    assert metrics.unsupported_cases == 1
    assert metrics.false_positives == 0
    assert metrics.false_negatives == 0
