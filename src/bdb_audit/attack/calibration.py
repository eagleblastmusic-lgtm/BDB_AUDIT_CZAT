"""Auditor Calibration Framework (WP-E5-04 / M39 / §98).

Implements calibrated ground truth benchmarking:
- Disjoint corpus partitions: DEVELOPMENT, CALIBRATION, HOLDOUT.
- Distinct case types: SEEDED_DEFECT, CLEAN_CONTROL, UNSEEDED_REAL_OBSERVATION.
- Unseeded real findings are strictly NEVER classified as false positives.
- Preserves exact denominator semantics for sensitivity, specificity, and precision.
- Fail-closed leakage guard between development and holdout corpora.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


CORPUS_PARTITIONS = {"DEVELOPMENT", "CALIBRATION", "HOLDOUT"}
CASE_TYPES = {"SEEDED_DEFECT", "CLEAN_CONTROL", "UNSEEDED_REAL_OBSERVATION"}


@dataclass(frozen=True)
class CalibrationCase:
    case_id: str
    partition: str
    case_type: str
    target_ref: dict[str, Any]
    defect_family: str = ""
    ground_truth_defective: bool | None = None  # None for unseeded real observations

    def __post_init__(self):
        if self.partition not in CORPUS_PARTITIONS:
            raise ValidationError(
                "INVALID_PARTITION",
                f"partition {self.partition} must be one of {sorted(CORPUS_PARTITIONS)}",
            )
        if self.case_type not in CASE_TYPES:
            raise ValidationError(
                "INVALID_CASE_TYPE",
                f"case_type {self.case_type} must be one of {sorted(CASE_TYPES)}",
            )
        if self.case_type == "SEEDED_DEFECT" and self.ground_truth_defective is not True:
            raise ValidationError("SEEDED_DEFECT_MUST_BE_TRUE", "SEEDED_DEFECT must have ground_truth_defective=True")
        if self.case_type == "CLEAN_CONTROL" and self.ground_truth_defective is not False:
            raise ValidationError("CLEAN_CONTROL_MUST_BE_FALSE", "CLEAN_CONTROL must have ground_truth_defective=False")
        if self.case_type == "UNSEEDED_REAL_OBSERVATION" and self.ground_truth_defective is not None:
            raise ValidationError("UNSEEDED_NO_GROUND_TRUTH", "UNSEEDED_REAL_OBSERVATION must have ground_truth_defective=None")

    def body(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "partition": self.partition,
            "case_type": self.case_type,
            "target_ref": dict(self.target_ref),
            "defect_family": self.defect_family,
            "ground_truth_defective": self.ground_truth_defective,
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


@dataclass(frozen=True)
class CalibrationEvaluation:
    evaluation_id: str
    partition: str
    true_positives: int
    false_negatives: int
    true_negatives: int
    false_positives: int
    unseeded_observations_flagged: int
    unseeded_observations_clean: int
    sensitivity_recall: float | None
    specificity: float | None
    precision_on_ground_truth: float | None

    def body(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "partition": self.partition,
            "true_positives": self.true_positives,
            "false_negatives": self.false_negatives,
            "true_negatives": self.true_negatives,
            "false_positives": self.false_positives,
            "unseeded_observations_flagged": self.unseeded_observations_flagged,
            "unseeded_observations_clean": self.unseeded_observations_clean,
            "sensitivity_recall": self.sensitivity_recall,
            "specificity": self.specificity,
            "precision_on_ground_truth": self.precision_on_ground_truth,
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


class CalibrationHarness:
    """Manages auditor calibration, enforces partition separation, and calculates calibration metrics."""

    def __init__(self):
        self._cases: dict[str, CalibrationCase] = {}

    def register_case(self, case: CalibrationCase) -> None:
        self._cases[case.case_id] = case

    def verify_no_partition_leakage(self) -> None:
        """Fail-closed guard verifying no intersection between DEVELOPMENT, CALIBRATION, and HOLDOUT cases."""
        dev_cases = {cid for cid, c in self._cases.items() if c.partition == "DEVELOPMENT"}
        cal_cases = {cid for cid, c in self._cases.items() if c.partition == "CALIBRATION"}
        holdout_cases = {cid for cid, c in self._cases.items() if c.partition == "HOLDOUT"}

        dev_cal = dev_cases & cal_cases
        dev_hold = dev_cases & holdout_cases
        cal_hold = cal_cases & holdout_cases

        if dev_cal or dev_hold or cal_hold:
            raise ValidationError(
                "CALIBRATION_CORPUS_LEAKAGE",
                f"Partition overlap detected: dev&cal={dev_cal}, dev&hold={dev_hold}, cal&hold={cal_hold}",
            )

    def evaluate(
        self,
        evaluation_id: str,
        partition: str,
        auditor_detections: Mapping[str, bool],
    ) -> CalibrationEvaluation:
        """Evaluate auditor performance on a specific partition preserving denominator semantics."""
        if partition not in CORPUS_PARTITIONS:
            raise ValidationError("INVALID_PARTITION", f"Unknown partition {partition}")

        self.verify_no_partition_leakage()

        tp = 0
        fn = 0
        tn = 0
        fp = 0
        unseeded_flagged = 0
        unseeded_clean = 0

        partition_cases = [c for c in self._cases.values() if c.partition == partition]

        for c in partition_cases:
            detected = auditor_detections.get(c.case_id, False)

            if c.case_type == "SEEDED_DEFECT":
                if detected:
                    tp += 1
                else:
                    fn += 1
            elif c.case_type == "CLEAN_CONTROL":
                if detected:
                    fp += 1  # False alarm on clean control
                else:
                    tn += 1
            elif c.case_type == "UNSEEDED_REAL_OBSERVATION":
                # Strictly isolated from ground truth denominators:
                # An unseeded observation is NEVER a false positive!
                if detected:
                    unseeded_flagged += 1
                else:
                    unseeded_clean += 1

        # Calculate metrics with denominator preservation
        sensitivity = round(tp / (tp + fn), 4) if (tp + fn) > 0 else None
        specificity = round(tn / (tn + fp), 4) if (tn + fp) > 0 else None
        precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else None

        return CalibrationEvaluation(
            evaluation_id=evaluation_id,
            partition=partition,
            true_positives=tp,
            false_negatives=fn,
            true_negatives=tn,
            false_positives=fp,
            unseeded_observations_flagged=unseeded_flagged,
            unseeded_observations_clean=unseeded_clean,
            sensitivity_recall=sensitivity,
            specificity=specificity,
            precision_on_ground_truth=precision,
        )
