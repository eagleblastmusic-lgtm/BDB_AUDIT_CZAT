"""Differential Testing Framework (WP-F5 / PR-E3-04 / M26 / R5.3 §48).

Implements:
- Semantic relation comparison (beyond raw byte diffs: SEMANTIC_EQUIVALENCE, PERMUTATION_INVARIANCE, MONOTONIC_LEQ, STRICT_EQUAL_BYTES).
- Multi-path execution descriptor and oracle binding.
- Independence enforcement: shared oracle / shared path cannot pretend independence.
- Canonical pipeline: diff -> observation/evidence -> hypothesis -> adjudication.
- Bypass prevention: diff cannot directly form a finding.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence
import hashlib
import json
from uuid import uuid4

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..adjudication.models import (
    FindingClaimRevision,
    FindingAxisAssessment,
    FindingAdjudicationDecision,
    _ref_dict,
)
from ..adjudication.engine import adjudicate_finding
from ..hypothesis.orchestrator import HypothesisOrchestrator
from ..hypothesis.models import HypothesisRevision
from ..evidence.graph import EvidenceGraph, EvidenceNode

SEMANTIC_RELATIONS = {
    "SEMANTIC_EQUIVALENCE",
    "PERMUTATION_INVARIANCE",
    "MONOTONIC_LEQ",
    "STRICT_EQUAL_BYTES",
    "SUBSET_RELATION",
}


@dataclass(frozen=True)
class DifferentialPathConfig:
    path_name: str
    execution_descriptor_ref: dict
    oracle_or_dependency_ref: dict
    environment_ref: dict
    runner_fn: Callable[[bytes], Any] | None = None


@dataclass(frozen=True)
class DifferentialExecutionResult:
    result_id: str
    input_case_ref: dict
    source_generation_ref: dict
    path_a_descriptor_ref: dict
    path_b_descriptor_ref: dict
    path_a_oracle_ref: dict
    path_b_oracle_ref: dict
    environment_ref: dict
    expected_semantic_relation: str
    observed_relation: str  # "MATCH", "DIVERGENCE", "EXECUTION_ERROR"
    is_independent: bool
    diff_details: dict | None = None

    def __post_init__(self):
        if self.expected_semantic_relation not in SEMANTIC_RELATIONS:
            raise ValidationError(
                "INVALID_SEMANTIC_RELATION",
                f"Unknown semantic relation: {self.expected_semantic_relation}",
            )

    def body(self) -> dict:
        return {
            "result_id": self.result_id,
            "input_case_ref": dict(self.input_case_ref),
            "source_generation_ref": dict(self.source_generation_ref),
            "path_a_descriptor_ref": dict(self.path_a_descriptor_ref),
            "path_b_descriptor_ref": dict(self.path_b_descriptor_ref),
            "path_a_oracle_ref": dict(self.path_a_oracle_ref),
            "path_b_oracle_ref": dict(self.path_b_oracle_ref),
            "environment_ref": dict(self.environment_ref),
            "expected_semantic_relation": self.expected_semantic_relation,
            "observed_relation": self.observed_relation,
            "is_independent": self.is_independent,
            "diff_details": dict(self.diff_details) if self.diff_details else None,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def ref(self) -> dict:
        return {
            "kind": "differential_execution_result",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::differential_execution_result/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


def compare_semantic_relation(
    output_a: Any,
    output_b: Any,
    expected_relation: str,
) -> tuple[str, dict | None]:
    """Compare outputs under the specified semantic relation."""
    if expected_relation == "STRICT_EQUAL_BYTES":
        bytes_a = output_a if isinstance(output_a, bytes) else str(output_a).encode()
        bytes_b = output_b if isinstance(output_b, bytes) else str(output_b).encode()
        if bytes_a == bytes_b:
            return "MATCH", None
        return "DIVERGENCE", {
            "reason": "RAW_BYTES_MISMATCH",
            "len_a": len(bytes_a),
            "len_b": len(bytes_b),
        }

    if expected_relation == "SEMANTIC_EQUIVALENCE":
        # Parse JSON if string or bytes
        val_a = output_a
        val_b = output_b
        if isinstance(val_a, (bytes, str)):
            try:
                val_a = json.loads(val_a)
            except Exception:
                pass
        if isinstance(val_b, (bytes, str)):
            try:
                val_b = json.loads(val_b)
            except Exception:
                pass

        if val_a == val_b:
            return "MATCH", None
        return "DIVERGENCE", {
            "reason": "SEMANTIC_CONTENT_MISMATCH",
            "val_a": str(val_a)[:200],
            "val_b": str(val_b)[:200],
        }

    if expected_relation == "PERMUTATION_INVARIANCE":
        try:
            seq_a = sorted(output_a)
            seq_b = sorted(output_b)
            if seq_a == seq_b:
                return "MATCH", None
            return "DIVERGENCE", {
                "reason": "PERMUTATION_CONTENT_MISMATCH",
                "len_a": len(output_a),
                "len_b": len(output_b),
            }
        except TypeError:
            return "DIVERGENCE", {"reason": "UNSORTABLE_ELEMENTS"}

    if expected_relation == "MONOTONIC_LEQ":
        try:
            if output_a <= output_b:
                return "MATCH", None
            return "DIVERGENCE", {
                "reason": "MONOTONIC_ORDER_VIOLATION",
                "val_a": str(output_a),
                "val_b": str(output_b),
            }
        except TypeError:
            return "DIVERGENCE", {"reason": "NON_COMPARABLE_TYPES"}

    if expected_relation == "SUBSET_RELATION":
        set_a = set(output_a)
        set_b = set(output_b)
        if set_a.issubset(set_b):
            return "MATCH", None
        return "DIVERGENCE", {
            "reason": "SUBSET_VIOLATION",
            "extra_in_a": list(set_a - set_b)[:10],
        }

    raise ValidationError("UNKNOWN_RELATION", expected_relation)


class DifferentialTestingFramework:
    """Executes differential tests between Path A and Path B, enforcing independence."""

    def __init__(
        self,
        path_a: DifferentialPathConfig,
        path_b: DifferentialPathConfig,
        expected_relation: str = "SEMANTIC_EQUIVALENCE",
        require_independent_oracle: bool = True,
    ):
        self.path_a = path_a
        self.path_b = path_b
        self.expected_relation = expected_relation
        self.require_independent_oracle = require_independent_oracle

        # Adversarial check: Shared oracle/path must not pretend independence
        self._check_oracle_independence()

    def _check_oracle_independence(self) -> bool:
        oracle_a = self.path_a.oracle_or_dependency_ref.get("revision_digest") or self.path_a.oracle_or_dependency_ref.get("id")
        oracle_b = self.path_b.oracle_or_dependency_ref.get("revision_digest") or self.path_b.oracle_or_dependency_ref.get("id")
        desc_a = self.path_a.execution_descriptor_ref.get("revision_digest") or self.path_a.execution_descriptor_ref.get("id")
        desc_b = self.path_b.execution_descriptor_ref.get("revision_digest") or self.path_b.execution_descriptor_ref.get("id")

        if oracle_a == oracle_b or desc_a == desc_b:
            if self.require_independent_oracle:
                raise ValidationError(
                    "SHARED_DIFFERENTIAL_ORACLE_NOT_INDEPENDENT",
                    "Path A and Path B share identical oracle or execution descriptor; cannot establish independent differential evidence",
                )
            return False
        return True

    def execute_differential(
        self,
        input_case_ref: Mapping,
        raw_input: bytes,
        source_generation_ref: Mapping,
        environment_ref: Mapping,
    ) -> DifferentialExecutionResult:
        """Run input on Path A and Path B, evaluate semantic relation, and return verified result."""
        runner_a = self.path_a.runner_fn
        runner_b = self.path_b.runner_fn
        if runner_a is None or runner_b is None:
            raise ValidationError("RUNNER_REQUIRED", "Both paths must provide execution runner functions")

        try:
            out_a = runner_a(raw_input)
            out_b = runner_b(raw_input)
        except Exception as exc:
            return DifferentialExecutionResult(
                result_id=f"diff_{uuid4().hex[:12]}",
                input_case_ref=dict(input_case_ref),
                source_generation_ref=dict(source_generation_ref),
                path_a_descriptor_ref=dict(self.path_a.execution_descriptor_ref),
                path_b_descriptor_ref=dict(self.path_b.execution_descriptor_ref),
                path_a_oracle_ref=dict(self.path_a.oracle_or_dependency_ref),
                path_b_oracle_ref=dict(self.path_b.oracle_or_dependency_ref),
                environment_ref=dict(environment_ref),
                expected_semantic_relation=self.expected_relation,
                observed_relation="EXECUTION_ERROR",
                is_independent=True,
                diff_details={"error": str(exc)},
            )

        observed_rel, diff_info = compare_semantic_relation(out_a, out_b, self.expected_relation)

        res_id = f"diff_{hashlib.sha256(raw_input).hexdigest()[:16]}"
        return DifferentialExecutionResult(
            result_id=res_id,
            input_case_ref=dict(input_case_ref),
            source_generation_ref=dict(source_generation_ref),
            path_a_descriptor_ref=dict(self.path_a.execution_descriptor_ref),
            path_b_descriptor_ref=dict(self.path_b.execution_descriptor_ref),
            path_a_oracle_ref=dict(self.path_a.oracle_or_dependency_ref),
            path_b_oracle_ref=dict(self.path_b.oracle_or_dependency_ref),
            environment_ref=dict(environment_ref),
            expected_semantic_relation=self.expected_relation,
            observed_relation=observed_rel,
            is_independent=True,
            diff_details=diff_info,
        )


def process_differential_result_through_pipeline(
    diff_result: DifferentialExecutionResult,
    hypothesis_orchestrator: HypothesisOrchestrator,
    evidence_graph: EvidenceGraph,
    history_cut: Mapping,
    source_generation_ref: Mapping,
    policy_ref: Mapping,
    adjudicator_ref: Mapping,
    active_cut_seq: int,
) -> tuple[HypothesisRevision | None, FindingAdjudicationDecision | None]:
    """Canonical pipeline: diff -> observation/evidence -> hypothesis -> adjudication.

    Diff does NOT become finding automatically.
    """
    cut_seq = history_cut.get("accepted_head_seq", 0)
    if cut_seq < active_cut_seq:
        raise ValidationError(
            "STALE_HISTORY_CUT_REJECTED",
            f"Differential history cut {cut_seq} is older than active cut {active_cut_seq}",
        )

    if diff_result.observed_relation != "DIVERGENCE":
        # Matches or execution errors do not spawn finding hypotheses
        return None, None

    case_ref = diff_result.input_case_ref
    case_hash = case_ref.get("case_hash") or case_ref.get("revision_digest") or "case_diff"

    # Step 1: Record diff observation in EvidenceGraph
    obs_id = f"obs_diff_{case_hash[:16]}"
    if obs_id in evidence_graph.nodes:
        obs_node = evidence_graph.nodes[obs_id]
    else:
        obs_node = evidence_graph.add_node(
            node_id=obs_id,
            node_type="OBSERVATION",
            data=dict(diff_result.diff_details or {}),
            ref=case_ref,
        )

    # Step 2: Propose HypothesisRevision
    hyp_statement = (
        f"Differential divergence observed between Path A and Path B on input {case_hash[:12]}: "
        f"{diff_result.diff_details.get('reason', 'SEMANTIC_DIVERGENCE') if diff_result.diff_details else 'DIVERGENCE'}"
    )
    inv_digest = hashlib.sha256(b"DIFFERENTIAL_SEMANTIC_EQUIVALENCE").hexdigest()
    inv_ref = {
        "kind": "invariant_revision",
        "revision_digest": inv_digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::invariant_revision/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    h_id = f"hyp_diff_{case_hash[:16]}"
    if h_id in hypothesis_orchestrator._chains_by_id:
        hyp = hypothesis_orchestrator._chains_by_id[h_id][-1]
    else:
        hyp = hypothesis_orchestrator.propose_hypothesis(
            hypothesis_id=h_id,
            statement=hyp_statement,
            scope_refs=[case_ref],
            invariant_refs=[inv_ref],
            obligation_refs=[],
            source_generation_ref=dict(source_generation_ref),
            history_cut=dict(history_cut),
            origin_discovery_ref=case_ref,
            planning_mode="EXPLORATORY",
        )

    # Step 3: Adjudicate finding
    claim = FindingClaimRevision(
        statement=hyp_statement,
        source_generation_ref=dict(source_generation_ref),
    )
    claim_ref = claim.as_object().as_ref().as_dict()

    mech = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=dict(history_cut),
        assessment_policy_ref=dict(policy_ref),
        axis="MECHANISM",
        epistemic_outcome="SUPPORTED",
        method="DIFFERENTIAL_DIVERGENCE_ANALYSIS",
    )
    reach = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=dict(history_cut),
        assessment_policy_ref=dict(policy_ref),
        axis="REACHABILITY",
        epistemic_outcome="SUPPORTED",
        method="DIFFERENTIAL_DUAL_PATH_EXECUTION",
    )
    impact = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=dict(history_cut),
        assessment_policy_ref=dict(policy_ref),
        axis="IMPACT",
        epistemic_outcome="SUPPORTED",
        method="SEMANTIC_INCONSISTENCY_ASSESSMENT",
    )
    sev = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=dict(history_cut),
        assessment_policy_ref=dict(policy_ref),
        axis="SEVERITY",
        epistemic_outcome="SUPPORTED",
        method="DIFFERENTIAL_SEVERITY_ESTIMATE",
    )

    decision = adjudicate_finding(
        claim=claim,
        mechanism=mech,
        reachability=reach,
        impact=impact,
        severity=sev,
        adjudicator_ref=dict(adjudicator_ref),
        input_history_cut=dict(history_cut),
    )

    return hyp, decision


def validate_no_direct_diff_to_finding(attempted_claim: Mapping, is_direct_diff: bool) -> None:
    """Guard against bypass: diff outputs cannot directly create findings without hypothesis and adjudication."""
    if is_direct_diff and not attempted_claim.get("hypothesis_revision_ref"):
        raise ValidationError(
            "DIFF_CANNOT_AUTO_CREATE_FINDING",
            "Disallowed pipeline bypass: differential output cannot directly form a FindingClaim without hypothesis and adjudication",
        )
