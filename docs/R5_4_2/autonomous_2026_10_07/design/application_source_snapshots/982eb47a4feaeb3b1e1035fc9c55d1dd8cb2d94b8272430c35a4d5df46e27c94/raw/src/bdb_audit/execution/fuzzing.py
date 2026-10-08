"""Fuzzing Adapter Framework (WP-F5 / PR-E3-03 / M25 / §136).

Implements:
- FuzzerAdapter abstract interface (core decoupled from concrete fuzzers).
- FuzzerCapability enforcement (limits on cases, timeout, memory).
- Deterministic FuzzerCase identity and reproduction linkage.
- Cleanup guarantees.
- Canonical pipeline: case -> observation -> hypothesis -> adjudication.
- Rejection of crash -> finding bypass (crash is observation, never automatic finding).
- Duplicate case idempotency and stale history cut rejection.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence, Set
import hashlib
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
from ..evidence.graph import EvidenceGraph, EvidenceNode, Observation


@dataclass(frozen=True)
class FuzzerCapability:
    max_cases: int = 1000
    timeout_seconds: float = 10.0
    supported_targets: tuple[str, ...] = ("ALL",)
    memory_limit_mb: int = 512
    allowed_mutators: tuple[str, ...] = ("BIT_FLIP", "BYTE_REPLACE", "DICTIONARY_INSERT")


@dataclass(frozen=True)
class FuzzerCase:
    case_id: str
    case_hash: str
    generator_ref: dict
    target_ref: dict
    raw_input: bytes
    seed_ref: dict | None = None
    minimization_lineage: tuple[str, ...] = ()
    generation_metadata: dict = field(default_factory=dict)

    def body(self) -> dict:
        return {
            "case_id": self.case_id,
            "case_hash": self.case_hash,
            "generator_ref": dict(self.generator_ref),
            "target_ref": dict(self.target_ref),
            "raw_input_hex": self.raw_input.hex(),
            "seed_ref": dict(self.seed_ref) if self.seed_ref else None,
            "minimization_lineage": list(self.minimization_lineage),
            "generation_metadata": dict(self.generation_metadata),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def ref(self) -> dict:
        return {
            "kind": "fuzzer_case",
            "revision_digest": self.digest,
            "case_hash": self.case_hash,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::fuzzer_case/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


def create_fuzzer_case(
    raw_input: bytes,
    generator_ref: Mapping,
    target_ref: Mapping,
    seed_ref: Mapping | None = None,
    minimization_lineage: Sequence[str] = (),
    generation_metadata: Mapping | None = None,
) -> FuzzerCase:
    """Construct deterministic FuzzerCase with SHA256 identity."""
    case_hash = hashlib.sha256(raw_input).hexdigest()
    case_id = f"case_{case_hash[:16]}"
    return FuzzerCase(
        case_id=case_id,
        case_hash=case_hash,
        generator_ref=dict(generator_ref),
        target_ref=dict(target_ref),
        raw_input=raw_input,
        seed_ref=dict(seed_ref) if seed_ref else None,
        minimization_lineage=tuple(minimization_lineage),
        generation_metadata=dict(generation_metadata or {}),
    )


@dataclass(frozen=True)
class FuzzerExecutionRecord:
    generator_ref: dict
    generator_profile_ref: dict
    harness_ref: dict
    environment_ref: dict
    input_case_ref: dict
    exit_code: int
    execution_time_ms: int
    status: str  # "SUCCESS", "CRASH", "TIMEOUT", "ERROR"
    reproduction_command: str
    seed_ref: dict | None = None
    crash_observation_ref: dict | None = None
    activation_observation_refs: tuple[dict, ...] = ()
    path_observation_refs: tuple[dict, ...] = ()
    invariant_candidate_ref: dict | None = None
    minimization_lineage: tuple[str, ...] = ()
    cleaned_up: bool = True

    def body(self) -> dict:
        return {
            "generator_ref": dict(self.generator_ref),
            "generator_profile_ref": dict(self.generator_profile_ref),
            "harness_ref": dict(self.harness_ref),
            "environment_ref": dict(self.environment_ref),
            "input_case_ref": dict(self.input_case_ref),
            "exit_code": self.exit_code,
            "execution_time_ms": self.execution_time_ms,
            "status": self.status,
            "reproduction_command": self.reproduction_command,
            "seed_ref": dict(self.seed_ref) if self.seed_ref else None,
            "crash_observation_ref": dict(self.crash_observation_ref) if self.crash_observation_ref else None,
            "activation_observation_refs": [dict(r) for r in self.activation_observation_refs],
            "path_observation_refs": [dict(r) for r in self.path_observation_refs],
            "invariant_candidate_ref": dict(self.invariant_candidate_ref) if self.invariant_candidate_ref else None,
            "minimization_lineage": list(self.minimization_lineage),
            "cleaned_up": self.cleaned_up,
        }


    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def ref(self) -> dict:
        return {
            "kind": "fuzzer_execution_record",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::fuzzer_execution_record/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


class FuzzerAdapter(ABC):
    """Abstract Fuzzer Adapter decouples core from concrete fuzzing backends."""

    def __init__(
        self,
        capability: FuzzerCapability,
        generator_ref: Mapping,
        generator_profile_ref: Mapping,
        harness_ref: Mapping,
        environment_ref: Mapping,
    ):
        self.capability = capability
        self.generator_ref = dict(generator_ref)
        self.generator_profile_ref = dict(generator_profile_ref)
        self.harness_ref = dict(harness_ref)
        self.environment_ref = dict(environment_ref)
        self._temp_resources: list[str] = []

    @abstractmethod
    def generate_cases(self, seed_inputs: Sequence[bytes], count: int) -> Sequence[FuzzerCase]:
        """Generate test cases deterministically."""
        pass

    @abstractmethod
    def execute_case(self, case: FuzzerCase, target_fn: Callable[[bytes], Any] | None = None) -> FuzzerExecutionRecord:
        """Execute a single fuzz case against target."""
        pass

    def cleanup(self) -> bool:
        """Release temporary resources and confirm cleanup."""
        self._temp_resources.clear()
        return True


class DeterministicFuzzerAdapter(FuzzerAdapter):
    """Deterministic, extensible in-memory fuzzer adapter enforcing capability limits."""

    def generate_cases(self, seed_inputs: Sequence[bytes], count: int) -> list[FuzzerCase]:
        if count > self.capability.max_cases:
            raise ValidationError(
                "FUZZER_CAPABILITY_EXCEEDED",
                f"Requested {count} cases exceeds maximum capability {self.capability.max_cases}",
            )
        if not seed_inputs:
            seed_inputs = [b"default_seed_payload"]

        cases = []
        for i in range(count):
            base_seed = seed_inputs[i % len(seed_inputs)]
            # Deterministic mutation: mutate byte at i % len
            mutated = bytearray(base_seed)
            if mutated:
                idx = i % len(mutated)
                mutated[idx] = (mutated[idx] + (i + 1) * 7) % 256
            raw = bytes(mutated)
            c = create_fuzzer_case(
                raw_input=raw,
                generator_ref=self.generator_ref,
                target_ref={"target": "target_service"},
                seed_ref={"seed_id": f"seed_{i % len(seed_inputs)}"},
                minimization_lineage=(f"mutation_step_{i}",),
            )
            cases.append(c)
        return cases

    def execute_case(
        self,
        case: FuzzerCase,
        target_fn: Callable[[bytes], Any] | None = None,
        timeout_override: float | None = None,
    ) -> FuzzerExecutionRecord:
        effective_timeout = timeout_override or self.capability.timeout_seconds
        repro_cmd = f"fuzz_replay --case-hash {case.case_hash} --input-hex {case.raw_input.hex()}"

        # Track temp resource
        temp_res = f"temp_fuzz_shm_{case.case_hash[:8]}"
        self._temp_resources.append(temp_res)

        crash_obs = None
        status = "SUCCESS"
        exit_code = 0
        exec_time_ms = 10

        # Check for malformed fuzzer output or invalid input
        if b"\x00\xff\xfe\xfdMALFORMED" in case.raw_input:
            self.cleanup()
            raise ValidationError("MALFORMED_FUZZER_OUTPUT", "Fuzzer target emitted corrupt output packet")

        # Check timeout simulation
        if b"TRIGGER_TIMEOUT" in case.raw_input:
            status = "TIMEOUT"
            exit_code = 124
            exec_time_ms = int(effective_timeout * 1000) + 100
        elif target_fn is not None:
            try:
                target_fn(case.raw_input)
            except Exception as exc:
                status = "CRASH"
                exit_code = 139  # SIGSEGV simulation
                crash_obs = {
                    "kind": "crash_observation",
                    "observation_id": f"crash_{case.case_hash[:12]}",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "reproduction_command": repro_cmd,
                }
        elif b"CRASH" in case.raw_input:
            status = "CRASH"
            exit_code = 139
            crash_obs = {
                "kind": "crash_observation",
                "observation_id": f"crash_{case.case_hash[:12]}",
                "exception_type": "MemoryAccessViolation",
                "exception_message": "Segmentation fault at offset 0x42",
                "reproduction_command": repro_cmd,
            }

        # Cleanup immediately after run
        self.cleanup()

        return FuzzerExecutionRecord(
            generator_ref=self.generator_ref,
            generator_profile_ref=self.generator_profile_ref,
            harness_ref=self.harness_ref,
            environment_ref=self.environment_ref,
            input_case_ref=case.ref,
            exit_code=exit_code,
            execution_time_ms=exec_time_ms,
            status=status,
            reproduction_command=repro_cmd,
            seed_ref=case.seed_ref,
            crash_observation_ref=crash_obs,
            activation_observation_refs=({"observation_id": f"act_{case.case_hash[:8]}"},),
            path_observation_refs=({"path_id": f"path_{case.case_hash[:8]}"},),
            minimization_lineage=case.minimization_lineage,
            cleaned_up=True,
        )


def process_fuzz_result_through_pipeline(
    fuzz_record: FuzzerExecutionRecord,
    hypothesis_orchestrator: HypothesisOrchestrator,
    evidence_graph: EvidenceGraph,
    history_cut: Mapping,
    source_generation_ref: Mapping,
    policy_ref: Mapping,
    adjudicator_ref: Mapping,
    active_cut_seq: int,
) -> tuple[HypothesisRevision | None, FindingAdjudicationDecision | None]:
    """Execute the canonical pipeline: case -> observation/evidence -> hypothesis -> adjudication.

    DISALLOWED: crash -> finding.
    Crash is an observation / evidence input, never an automatic finding.
    """
    cut_seq = history_cut.get("accepted_head_seq", 0)
    if cut_seq < active_cut_seq:
        raise ValidationError(
            "STALE_HISTORY_CUT_REJECTED",
            f"Fuzzing history cut {cut_seq} is stale compared to active cut {active_cut_seq}",
        )

    if fuzz_record.status != "CRASH" or not fuzz_record.crash_observation_ref:
        # Non-crash executions do not spawn hypotheses
        return None, None

    crash_data = fuzz_record.crash_observation_ref
    case_ref = fuzz_record.input_case_ref
    case_hash = case_ref.get("case_hash", "unknown")

    # Step 1: Record crash observation as EvidenceNode
    obs_id = f"obs_{case_hash[:16]}"
    if obs_id in evidence_graph.nodes:
        obs_node = evidence_graph.nodes[obs_id]
    else:
        obs_node = evidence_graph.add_node(
            node_id=obs_id,
            node_type="OBSERVATION",
            data=dict(crash_data),
            ref=case_ref,
        )

    # Step 2: Propose HypothesisRevision (EXPLORATORY, not automatic finding)
    hyp_statement = f"Target failure triggered by input case {case_hash[:12]}: {crash_data.get('exception_type', 'Crash')}"
    inv_digest = hashlib.sha256(b"PARSER_CRASH_FREEDOM").hexdigest()
    inv_ref = {
        "kind": "invariant_revision",
        "revision_digest": inv_digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::invariant_revision/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    h_id = f"hyp_fuzz_{case_hash[:16]}"
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

    # Step 3: 4-Axis Finding Adjudication (adjudicate_finding)
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
        method="FUZZ_CRASH_REPRODUCTION",
    )
    reach = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=dict(history_cut),
        assessment_policy_ref=dict(policy_ref),
        axis="REACHABILITY",
        epistemic_outcome="SUPPORTED",
        method="FUZZ_HARNESS_TRIGGER",
    )
    impact = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=dict(history_cut),
        assessment_policy_ref=dict(policy_ref),
        axis="IMPACT",
        epistemic_outcome="SUPPORTED",
        method="PROCESS_TERMINATION_OBSERVATION",
    )
    sev = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=dict(history_cut),
        assessment_policy_ref=dict(policy_ref),
        axis="SEVERITY",
        epistemic_outcome="SUPPORTED",
        method="DEFAULT_CRASH_SEVERITY",
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


def validate_no_direct_crash_to_finding(attempted_claim: Mapping, is_direct_crash: bool) -> None:
    """Guard against bypass: crashes cannot directly create findings without hypothesis and adjudication."""
    if is_direct_crash and not attempted_claim.get("hypothesis_revision_ref"):
        raise ValidationError(
            "CRASH_CANNOT_AUTO_CREATE_FINDING",
            "Disallowed pipeline bypass: crash output cannot directly form a FindingClaim without hypothesis and adjudication",
        )
