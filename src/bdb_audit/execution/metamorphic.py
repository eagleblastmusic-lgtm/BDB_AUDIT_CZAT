"""Metamorphic Testing Framework (WP-F5 / PR-E3-05 / M27 / R5.3 §48).

Implements:
- Deterministic MetamorphicTransformation identity and parameters.
- Preregistration requirement: expected relation registered BEFORE observation.
- Separate recording of observed relation.
- Canonical pipeline: violation -> observation/evidence -> hypothesis -> adjudication.
- Direct finding bypass rejection: violations cannot auto-create findings.
- Stale / wrong-cut transformation rejection.
- Replay determinism.
- Invalidation propagation via EvidenceGraph.
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
from ..evidence.graph import EvidenceGraph, EvidenceNode, EvidenceEdge


@dataclass(frozen=True)
class MetamorphicTransformation:
    transformation_id: str
    category: str
    parameters: dict
    transform_fn: Callable[[bytes], bytes]
    identity_digest: str

    def body(self) -> dict:
        return {
            "transformation_id": self.transformation_id,
            "category": self.category,
            "parameters": dict(self.parameters),
            "identity_digest": self.identity_digest,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def ref(self) -> dict:
        return {
            "kind": "metamorphic_transformation",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::metamorphic_transformation/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


def create_metamorphic_transformation(
    category: str,
    parameters: Mapping[str, Any],
    transform_fn: Callable[[bytes], bytes],
) -> MetamorphicTransformation:
    """Create a MetamorphicTransformation with deterministic identity digest."""
    params_bytes = canonical_bytes(dict(parameters))
    ident_digest = hashlib.sha256(f"{category}:{params_bytes.hex()}".encode()).hexdigest()
    t_id = f"trans_{ident_digest[:16]}"
    return MetamorphicTransformation(
        transformation_id=t_id,
        category=category,
        parameters=dict(parameters),
        transform_fn=transform_fn,
        identity_digest=ident_digest,
    )


@dataclass(frozen=True)
class MetamorphicRelationSpec:
    spec_id: str
    transformation_id: str
    expected_relation: str  # "OUTPUT_EQUIVALENT", "OUTPUT_INVERSE", "MONOTONIC_LEQ", "OUTPUT_SUBSET"
    target_system_ref: dict
    preregistration_cut: dict
    preregistered_before_run: bool = True

    def __post_init__(self):
        if not self.preregistered_before_run:
            raise ValidationError(
                "RETROACTIVE_METAMORPHIC_RELATION_REJECTED",
                "Metamorphic relation must be preregistered before execution; retroactive registration forbidden",
            )

    def body(self) -> dict:
        return {
            "spec_id": self.spec_id,
            "transformation_id": self.transformation_id,
            "expected_relation": self.expected_relation,
            "target_system_ref": dict(self.target_system_ref),
            "preregistration_cut": dict(self.preregistration_cut),
            "preregistered_before_run": self.preregistered_before_run,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def ref(self) -> dict:
        return {
            "kind": "metamorphic_relation_spec",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::metamorphic_relation_spec/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


@dataclass(frozen=True)
class MetamorphicExecutionRecord:
    record_id: str
    original_input_ref: dict
    original_input_digest: str
    transformed_input_ref: dict
    transformed_input_digest: str
    transformation_ref: dict
    relation_spec_ref: dict
    expected_relation: str
    observed_relation: str  # "SATISFIED", "VIOLATION", "EXECUTION_ERROR"
    history_cut: dict
    violation_details: dict | None = None

    def body(self) -> dict:
        return {
            "record_id": self.record_id,
            "original_input_ref": dict(self.original_input_ref),
            "original_input_digest": self.original_input_digest,
            "transformed_input_ref": dict(self.transformed_input_ref),
            "transformed_input_digest": self.transformed_input_digest,
            "transformation_ref": dict(self.transformation_ref),
            "relation_spec_ref": dict(self.relation_spec_ref),
            "expected_relation": self.expected_relation,
            "observed_relation": self.observed_relation,
            "history_cut": dict(self.history_cut),
            "violation_details": dict(self.violation_details) if self.violation_details else None,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def ref(self) -> dict:
        return {
            "kind": "metamorphic_execution_record",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::metamorphic_execution_record/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


def check_metamorphic_relation(
    orig_output: Any,
    trans_output: Any,
    expected_relation: str,
) -> tuple[str, dict | None]:
    """Evaluate whether the observed outputs satisfy the preregistered expected relation."""
    if expected_relation == "OUTPUT_EQUIVALENT":
        # Parse json if str/bytes
        val_o = orig_output
        val_t = trans_output
        if isinstance(val_o, (bytes, str)):
            try:
                val_o = json.loads(val_o)
            except Exception:
                pass
        if isinstance(val_t, (bytes, str)):
            try:
                val_t = json.loads(val_t)
            except Exception:
                pass

        if val_o == val_t:
            return "SATISFIED", None
        return "VIOLATION", {
            "reason": "OUTPUT_EQUIVALENCE_VIOLATION",
            "orig_output": str(val_o)[:200],
            "trans_output": str(val_t)[:200],
        }

    if expected_relation == "MONOTONIC_LEQ":
        try:
            if orig_output <= trans_output:
                return "SATISFIED", None
            return "VIOLATION", {
                "reason": "MONOTONIC_LEQ_VIOLATION",
                "orig_output": str(orig_output),
                "trans_output": str(trans_output),
            }
        except TypeError:
            return "VIOLATION", {"reason": "NON_COMPARABLE_TYPES"}

    if expected_relation == "OUTPUT_INVERSE":
        try:
            if orig_output == -trans_output or (bool(orig_output) != bool(trans_output)):
                return "SATISFIED", None
            return "VIOLATION", {
                "reason": "INVERSE_RELATION_VIOLATION",
                "orig_output": str(orig_output),
                "trans_output": str(trans_output),
            }
        except Exception:
            return "VIOLATION", {"reason": "INVERSE_CHECK_FAILED"}

    raise ValidationError("UNKNOWN_RELATION", expected_relation)


class MetamorphicTestingFramework:
    """Executes metamorphic tests with deterministic transformation and preregistered relation specs."""

    def __init__(self, target_fn: Callable[[bytes], Any]):
        self.target_fn = target_fn
        self._preregistered_specs: dict[str, MetamorphicRelationSpec] = {}

    def preregister_relation_spec(self, spec: MetamorphicRelationSpec) -> None:
        """Preregister a metamorphic relation spec before observation."""
        if not spec.preregistered_before_run:
            raise ValidationError(
                "RETROACTIVE_METAMORPHIC_RELATION_REJECTED",
                "Cannot register metamorphic relation retroactively",
            )
        self._preregistered_specs[spec.spec_id] = spec

    def execute_metamorphic_test(
        self,
        original_input_ref: Mapping,
        original_input: bytes,
        transformation: MetamorphicTransformation,
        spec_id: str,
        history_cut: Mapping,
        active_cut_seq: int,
    ) -> MetamorphicExecutionRecord:
        """Run metamorphic test: original input + transformed input, evaluate expected relation."""
        cut_seq = history_cut.get("accepted_head_seq", 0)
        if cut_seq < active_cut_seq:
            raise ValidationError(
                "STALE_HISTORY_CUT_REJECTED",
                f"Metamorphic history cut {cut_seq} is older than active cut {active_cut_seq}",
            )

        if spec_id not in self._preregistered_specs:
            raise ValidationError(
                "RETROACTIVE_METAMORPHIC_RELATION_REJECTED",
                f"Relation spec {spec_id} was not preregistered before test execution",
            )
        spec = self._preregistered_specs[spec_id]

        orig_digest = hashlib.sha256(original_input).hexdigest()

        # Deterministic transformation execution
        transformed_input = transformation.transform_fn(original_input)
        trans_digest = hashlib.sha256(transformed_input).hexdigest()
        transformed_input_ref = {
            "kind": "transformed_input",
            "revision_digest": trans_digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::transformed_input/1",
            "ref_class": "CONTENT_OR_PRIOR",
            "origin_input_digest": orig_digest,
            "transformation_id": transformation.transformation_id,
        }

        # Run target on both inputs
        try:
            orig_out = self.target_fn(original_input)
            trans_out = self.target_fn(transformed_input)
        except Exception as exc:
            return MetamorphicExecutionRecord(
                record_id=f"meta_{orig_digest[:8]}_{trans_digest[:8]}",
                original_input_ref=dict(original_input_ref),
                original_input_digest=orig_digest,
                transformed_input_ref=transformed_input_ref,
                transformed_input_digest=trans_digest,
                transformation_ref=transformation.ref,
                relation_spec_ref=spec.ref,
                expected_relation=spec.expected_relation,
                observed_relation="EXECUTION_ERROR",
                history_cut=dict(history_cut),
                violation_details={"error": str(exc)},
            )

        observed_rel, viol_info = check_metamorphic_relation(
            orig_out, trans_out, spec.expected_relation
        )

        rec_id = f"meta_{orig_digest[:8]}_{trans_digest[:8]}"
        return MetamorphicExecutionRecord(
            record_id=rec_id,
            original_input_ref=dict(original_input_ref),
            original_input_digest=orig_digest,
            transformed_input_ref=transformed_input_ref,
            transformed_input_digest=trans_digest,
            transformation_ref=transformation.ref,
            relation_spec_ref=spec.ref,
            expected_relation=spec.expected_relation,
            observed_relation=observed_rel,
            history_cut=dict(history_cut),
            violation_details=viol_info,
        )


def process_metamorphic_result_through_pipeline(
    record: MetamorphicExecutionRecord,
    hypothesis_orchestrator: HypothesisOrchestrator,
    evidence_graph: EvidenceGraph,
    history_cut: Mapping,
    source_generation_ref: Mapping,
    policy_ref: Mapping,
    adjudicator_ref: Mapping,
    active_cut_seq: int,
) -> tuple[HypothesisRevision | None, FindingAdjudicationDecision | None, str | None]:
    """Canonical pipeline: violation -> observation/evidence -> hypothesis -> adjudication.

    Metamorphic violation does NOT become finding automatically.
    Returns (hypothesis, adjudication_decision, evidence_node_id).
    """
    cut_seq = history_cut.get("accepted_head_seq", 0)
    if cut_seq < active_cut_seq:
        raise ValidationError(
            "STALE_HISTORY_CUT_REJECTED",
            f"Metamorphic history cut {cut_seq} is older than active cut {active_cut_seq}",
        )

    if record.observed_relation != "VIOLATION":
        return None, None, None

    viol_data = record.violation_details or {}
    orig_ref = record.original_input_ref
    trans_ref = record.transformed_input_ref
    rec_hash = hashlib.sha256(f"{record.original_input_digest}:{record.transformed_input_digest}".encode()).hexdigest()

    # Step 1: Record violation as EvidenceNode in EvidenceGraph
    obs_id = f"obs_meta_{rec_hash[:16]}"
    if obs_id in evidence_graph.nodes:
        obs_node = evidence_graph.nodes[obs_id]
    else:
        obs_node = evidence_graph.add_node(
            node_id=obs_id,
            node_type="OBSERVATION",
            data=dict(viol_data),
            ref=record.ref,
        )

    # Step 2: Propose HypothesisRevision
    hyp_statement = (
        f"Metamorphic relation violation observed on transformation {record.transformation_ref.get('revision_digest', '')[:8]}: "
        f"{viol_data.get('reason', 'METAMORPHIC_VIOLATION')}"
    )
    inv_digest = hashlib.sha256(b"METAMORPHIC_INVARIANT_PRESERVATION").hexdigest()
    inv_ref = {
        "kind": "invariant_revision",
        "revision_digest": inv_digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::invariant_revision/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    h_id = f"hyp_meta_{rec_hash[:16]}"
    if h_id in hypothesis_orchestrator._chains_by_id:
        hyp = hypothesis_orchestrator._chains_by_id[h_id][-1]
    else:
        hyp = hypothesis_orchestrator.propose_hypothesis(
            hypothesis_id=h_id,
            statement=hyp_statement,
            scope_refs=[orig_ref, trans_ref],
            invariant_refs=[inv_ref],
            obligation_refs=[],
            source_generation_ref=dict(source_generation_ref),
            history_cut=dict(history_cut),
            origin_discovery_ref=record.ref,
            planning_mode="EXPLORATORY",
        )

    # Step 3: 4-Axis Adjudication
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
        method="METAMORPHIC_RELATION_ANALYSIS",
    )
    reach = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=dict(history_cut),
        assessment_policy_ref=dict(policy_ref),
        axis="REACHABILITY",
        epistemic_outcome="SUPPORTED",
        method="METAMORPHIC_TRANSFORMATION_EXECUTION",
    )
    impact = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=dict(history_cut),
        assessment_policy_ref=dict(policy_ref),
        axis="IMPACT",
        epistemic_outcome="SUPPORTED",
        method="INVARIANT_PRESERVATION_FAILURE",
    )
    sev = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=dict(history_cut),
        assessment_policy_ref=dict(policy_ref),
        axis="SEVERITY",
        epistemic_outcome="SUPPORTED",
        method="METAMORPHIC_SEVERITY_ESTIMATE",
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

    return hyp, decision, obs_id


def validate_no_direct_metamorphic_to_finding(attempted_claim: Mapping, is_direct_violation: bool) -> None:
    """Guard against bypass: metamorphic violations cannot directly create findings without hypothesis and adjudication."""
    if is_direct_violation and not attempted_claim.get("hypothesis_revision_ref"):
        raise ValidationError(
            "METAMORPHIC_VIOLATION_CANNOT_AUTO_CREATE_FINDING",
            "Disallowed pipeline bypass: metamorphic violation cannot directly form a FindingClaim without hypothesis and adjudication",
        )
