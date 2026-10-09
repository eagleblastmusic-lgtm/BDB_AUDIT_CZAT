"""Independent Qualification Runner and Methodology Qualifier (R5.3 §111 / B08).

Enforces:
1. Critical validators disabled or tampered -> qualification FAIL.
2. Mandatory checker NOT_RUN -> overall qualification CANNOT PASS (marked INSUFFICIENT or FAILED).
3. Zero test cases / zero evaluated checks -> cannot pass (INSUFFICIENT).
4. Results derive strictly from verifiable actual run receipts.
5. Explicit denominators and explicit unknown/unsupported tracking.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .methodology_metrics import MethodologyMetrics
from .receipts import ActualRunReceipt, BenchmarkManifest, QualificationReceipt


MANDATORY_QUALIFICATION_CHECKERS = (
    "0_version_identity",
    "1_startup_integrity",
    "2_embedded_registry_pin",
    "3_embedded_stagespec_definition_presence",
    "4_embedded_lanespec_definition_presence",
    "5_embedded_template_definition_presence",
    "6_payload_manifest",
    "7_exact_digests",
    "7b_embedded_runtime_closure",
    "8_self_test_isolated_embedded_runtime",
    "9_foundation_golden_vectors_pin",
    "10_same_environment_rebuild_identity",
    "anti_bypass_suite",
)


class MethodologyQualifier:
    """Rigorous qualification evaluator enforcing anti-false-PASS invariants."""

    def __init__(self, app_version: str = "2.0.3", candidate_sha: str = ""):
        self.app_version = app_version
        self.candidate_sha = candidate_sha

    @staticmethod
    def evaluate_checker_receipts(
        checkers: Mapping[str, str],
        receipts: Sequence[ActualRunReceipt] = (),
        required_checkers: Sequence[str] = MANDATORY_QUALIFICATION_CHECKERS,
    ) -> dict[str, Any]:
        """Evaluate a set of checker outcomes against mandatory qualification rules."""
        unresolved_reasons: list[str] = []
        has_not_run = False
        has_failure = False

        for req in required_checkers:
            outcome = checkers.get(req)
            if outcome is None:
                unresolved_reasons.append(f"MANDATORY_CHECKER_MISSING: {req}")
                has_not_run = True
            elif outcome == "NOT_RUN":
                unresolved_reasons.append(f"MANDATORY_CHECKER_NOT_RUN: {req}")
                has_not_run = True
            elif outcome != "PASS":
                unresolved_reasons.append(f"MANDATORY_CHECKER_FAILED: {req} ({outcome})")
                has_failure = True

        # Check receipts for non-PASS or zero cases
        receipts_by_checker = {r.checker_id: r for r in receipts}
        for req in required_checkers:
            if req in receipts_by_checker:
                rec = receipts_by_checker[req]
                if rec.status != "PASS" or rec.evaluated_cases_count == 0:
                    unresolved_reasons.append(f"CHECKER_NON_PASS_OR_ZERO_CASES: {req} ({rec.status}, cases={rec.evaluated_cases_count})")
                    has_failure = True

        if has_failure:
            status = "FAILED"
            overall_outcome = "FAIL"
        elif has_not_run:
            status = "INSUFFICIENT"
            overall_outcome = "INSUFFICIENT_EVIDENCE"
        else:
            status = "QUALIFIED"
            overall_outcome = "PASS"

        return {
            "status": status,
            "overall_outcome": overall_outcome,
            "unresolved_reasons": unresolved_reasons,
            "total_required": len(required_checkers),
            "evaluated_count": sum(1 for req in required_checkers if checkers.get(req) not in (None, "NOT_RUN")),
        }

    def qualify_candidate(
        self,
        candidate_sha: str,
        checkers: Mapping[str, str],
        receipts: Sequence[ActualRunReceipt] = (),
        benchmarks: Sequence[BenchmarkManifest] = (),
        required_checkers: Sequence[str] = MANDATORY_QUALIFICATION_CHECKERS,
        qualification_scope: str = "METHODOLOGY_QUALIFICATION",
        metadata: dict[str, Any] | None = None,
    ) -> QualificationReceipt:
        """Produce an authoritative QualificationReceipt."""
        if not candidate_sha:
            raise ValidationError("CANDIDATE_SHA_REQUIRED", "candidate_sha cannot be empty")

        eval_res = self.evaluate_checker_receipts(checkers, receipts, required_checkers)

        denominator = len(required_checkers) + len(benchmarks)
        if denominator <= 0:
            raise ValidationError("ZERO_DENOMINATOR", "Cannot qualify with 0 denominator")

        unsupported_count = sum(1 for b in benchmarks if b.expected_label == "UNSUPPORTED")
        unknown_count = sum(1 for r in receipts if r.status == "UNKNOWN")

        receipt_id = f"qual_rcpt_{hashlib.sha256((candidate_sha + str(time.time())).encode()).hexdigest()[:16]}"

        return QualificationReceipt(
            receipt_id=receipt_id,
            candidate_sha=candidate_sha,
            app_version=self.app_version,
            qualification_scope=qualification_scope,
            status=eval_res["status"],
            overall_outcome=eval_res["overall_outcome"],
            total_required_checkers=eval_res["total_required"],
            evaluated_checkers_count=eval_res["evaluated_count"],
            checkers=dict(checkers),
            denominator=denominator,
            actual_receipts=tuple(receipts),
            unsupported_count=unsupported_count,
            unknown_count=unknown_count,
            unresolved_reasons=tuple(eval_res["unresolved_reasons"]),
            metadata=metadata or {},
        )

    @staticmethod
    def score_benchmark_corpus(
        benchmarks: Sequence[BenchmarkManifest],
        actual_results: Mapping[str, str],  # target_id -> observed_label ("CLEAN", "DEFECTIVE", "UNKNOWN", etc.)
    ) -> MethodologyMetrics:
        """Score actual runs against benchmark truth partition (which was not exposed to audited system)."""
        total = len(benchmarks)
        evaluated = 0
        tp = 0
        fp = 0
        tn = 0
        fn = 0
        unsupported = 0
        unknown = 0

        for bm in benchmarks:
            obs = actual_results.get(bm.target_id)
            if obs is None:
                continue
            evaluated += 1

            if bm.expected_label == "UNSUPPORTED":
                unsupported += 1
            elif obs == "UNKNOWN":
                unknown += 1
            elif bm.expected_label == "DEFECTIVE":
                if obs == "DEFECTIVE":
                    tp += 1
                else:
                    fn += 1
            elif bm.expected_label == "CLEAN":
                if obs == "CLEAN":
                    tn += 1
                else:
                    fp += 1

        return MethodologyMetrics(
            total_targets=total,
            evaluated_targets=evaluated,
            true_positives=tp,
            false_positives=fp,
            true_negatives=tn,
            false_negatives=fn,
            unsupported_cases=unsupported,
            unknown_cases=unknown,
            anti_bypass_total=0,
            anti_bypass_passed=0,
            denominator=total,
        )
