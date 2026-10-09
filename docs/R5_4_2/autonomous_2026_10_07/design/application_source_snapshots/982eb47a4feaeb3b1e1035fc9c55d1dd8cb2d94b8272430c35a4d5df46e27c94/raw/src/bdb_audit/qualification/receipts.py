"""Benchmark Manifests and Verifiable Execution Receipts (R5.3 §111 / B08).

Provides immutable dataclasses for benchmark manifests, actual run receipts,
and qualification receipts. Ensures explicit denominators, separate truth partitions,
and fail-closed integrity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


@dataclass(frozen=True)
class BenchmarkManifest:
    """Benchmark target definition stored in a separate truth partition.

    The audited pipeline MUST NOT be granted access to expected_label.
    """
    benchmark_id: str
    target_id: str
    target_sha: str
    expected_label: str = "CLEAN"  # CLEAN, DEFECTIVE, AMBIGUOUS, BLOCKED, UNSUPPORTED
    defect_id: str | None = None
    allowed_exposures: tuple[str, ...] = ()
    split_membership: str = "VALIDATION"  # HOLDOUT, CALIBRATION, VALIDATION
    domain_tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.benchmark_id:
            raise ValidationError("BENCHMARK_ID_MISSING", "benchmark_id must not be empty")
        if not self.target_id:
            raise ValidationError("TARGET_ID_MISSING", "target_id must not be empty")
        if not self.target_sha or len(self.target_sha) < 40:
            raise ValidationError("TARGET_SHA_INVALID", "target_sha must be a valid commit SHA")
        valid_splits = {"HOLDOUT", "CALIBRATION", "VALIDATION"}
        if self.split_membership not in valid_splits:
            raise ValidationError("SPLIT_INVALID", f"split_membership must be in {valid_splits}")
        valid_labels = {"CLEAN", "DEFECTIVE", "AMBIGUOUS", "BLOCKED", "UNSUPPORTED"}
        if self.expected_label not in valid_labels:
            raise ValidationError("LABEL_INVALID", f"expected_label must be in {valid_labels}")

    def manifest_digest(self) -> str:
        body = {
            "benchmark_id": self.benchmark_id,
            "target_id": self.target_id,
            "target_sha": self.target_sha,
            "defect_id": self.defect_id,
            "expected_label": self.expected_label,
            "allowed_exposures": list(self.allowed_exposures),
            "split_membership": self.split_membership,
            "domain_tags": list(self.domain_tags),
            "metadata": self.metadata,
        }
        return hashlib.sha256(canonical_bytes(body)).hexdigest()


@dataclass(frozen=True)
class ActualRunReceipt:
    """Receipt proving actual execution of a specific checker/tool against a target."""
    receipt_id: str
    benchmark_id: str
    target_id: str
    checker_id: str
    execution_timestamp: str
    exit_code: int
    status: str  # PASS, FAIL, INSUFFICIENT, NOT_RUN, ERROR, BLOCKED, UNKNOWN
    raw_output_digest: str
    evaluated_cases_count: int
    passed_cases_count: int
    failed_cases_count: int
    unsupported_cases_count: int = 0
    unknown_cases_count: int = 0
    execution_duration_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.receipt_id:
            raise ValidationError("RECEIPT_ID_MISSING", "receipt_id must not be empty")
        if not self.checker_id:
            raise ValidationError("CHECKER_ID_MISSING", "checker_id must not be empty")
        valid_statuses = {"PASS", "FAIL", "INSUFFICIENT", "NOT_RUN", "ERROR", "BLOCKED", "UNKNOWN"}
        if self.status not in valid_statuses:
            raise ValidationError("STATUS_INVALID", f"status must be in {valid_statuses}")
        if self.status == "PASS" and self.evaluated_cases_count == 0:
            raise ValidationError("ZERO_CASES_PASS_FORBIDDEN", "Status cannot be PASS with 0 evaluated cases")
        if self.passed_cases_count + self.failed_cases_count + self.unsupported_cases_count + self.unknown_cases_count > self.evaluated_cases_count:
            raise ValidationError("CASES_COUNT_INCONSISTENT", "Sum of case counts exceeds evaluated_cases_count")

    def receipt_digest(self) -> str:
        body = {
            "receipt_id": self.receipt_id,
            "benchmark_id": self.benchmark_id,
            "target_id": self.target_id,
            "checker_id": self.checker_id,
            "execution_timestamp": self.execution_timestamp,
            "exit_code": self.exit_code,
            "status": self.status,
            "raw_output_digest": self.raw_output_digest,
            "evaluated_cases_count": self.evaluated_cases_count,
            "passed_cases_count": self.passed_cases_count,
            "failed_cases_count": self.failed_cases_count,
            "unsupported_cases_count": self.unsupported_cases_count,
            "unknown_cases_count": self.unknown_cases_count,
            "execution_duration_ms": self.execution_duration_ms,
            "details": self.details,
        }
        return hashlib.sha256(canonical_bytes(body)).hexdigest()


@dataclass(frozen=True)
class QualificationReceipt:
    """Verifiable release/methodology qualification receipt with explicit denominator."""
    receipt_id: str
    candidate_sha: str
    app_version: str
    qualification_scope: str
    status: str  # QUALIFIED, FAILED, INSUFFICIENT
    overall_outcome: str
    total_required_checkers: int
    evaluated_checkers_count: int
    checkers: dict[str, str]
    denominator: int
    actual_receipts: tuple[ActualRunReceipt, ...] = ()
    unsupported_count: int = 0
    unknown_count: int = 0
    unresolved_reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.receipt_id:
            raise ValidationError("QUALIFICATION_RECEIPT_ID_MISSING", "receipt_id required")
        if not self.candidate_sha:
            raise ValidationError("CANDIDATE_SHA_MISSING", "candidate_sha required")
        if self.denominator <= 0:
            raise ValidationError("ZERO_DENOMINATOR_FORBIDDEN", "Qualification requires an explicit positive denominator")
        valid_statuses = {"QUALIFIED", "FAILED", "INSUFFICIENT"}
        if self.status not in valid_statuses:
            raise ValidationError("QUALIFICATION_STATUS_INVALID", f"status must be in {valid_statuses}")
        # A required checker marked NOT_RUN strictly prohibits QUALIFIED status
        if self.status == "QUALIFIED":
            for name, outcome in self.checkers.items():
                if outcome == "NOT_RUN":
                    raise ValidationError(
                        "NOT_RUN_CHECKER_CANNOT_QUALIFY",
                        f"Checker '{name}' is NOT_RUN; cannot award QUALIFIED status",
                    )
                if outcome != "PASS":
                    raise ValidationError(
                        "NON_PASS_CHECKER_CANNOT_QUALIFY",
                        f"Checker '{name}' is {outcome}; cannot award QUALIFIED status",
                    )

    def receipt_digest(self) -> str:
        body = {
            "receipt_id": self.receipt_id,
            "candidate_sha": self.candidate_sha,
            "app_version": self.app_version,
            "qualification_scope": self.qualification_scope,
            "status": self.status,
            "overall_outcome": self.overall_outcome,
            "total_required_checkers": self.total_required_checkers,
            "evaluated_checkers_count": self.evaluated_checkers_count,
            "checkers": self.checkers,
            "denominator": self.denominator,
            "unsupported_count": self.unsupported_count,
            "unknown_count": self.unknown_count,
            "unresolved_reasons": list(self.unresolved_reasons),
            "actual_receipt_digests": [r.receipt_digest() for r in self.actual_receipts],
            "metadata": self.metadata,
        }
        return hashlib.sha256(canonical_bytes(body)).hexdigest()
