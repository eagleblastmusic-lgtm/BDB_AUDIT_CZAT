"""Native E3 Novelty Expansion, Blind Lanes, and Checkpoint/Reveal Orchestration (WP-F5 / M24-M27)."""
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
import hashlib

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import object_digest
from ..core.ids import new_id
from ..history.objects import CanonicalObject, ObjectRef
from .stages import StageSpec
from .runs import LaneSpec, Attempt, IsolationQualification
from ..knowledge.exposure import (
    KnowledgeState,
    DiscoveryRecord,
    classify_discovery,
    GrantAccepted,
    PotentialExposureRecord,
)

# 3 Mandatory E3 Blind Discovery Lanes (R5.3 §23 / M24)
E3_LANE_SLOTS = ("E3-X", "E3-Y", "E3-Z")

E3_LANE_STRATEGIES = {
    "E3-X": ("Security, Authority & Trust", "AUTHORITY_TRUST_NOVELTY_SEARCH"),
    "E3-Y": ("State, Data, Catalog & Recovery", "STATE_CATALOG_RECOVERY_SEARCH"),
    "E3-Z": ("Frontend, Concurrency, Resources & Cross-Layer", "CROSS_LAYER_CONCURRENCY_SEARCH"),
}

# Forbidden metadata fields that must never leak into blind lanes
FORBIDDEN_BLIND_LEAK_FIELDS = frozenset({
    "finding_claim_ref",
    "finding_id",
    "prior_finding_ref",
    "prior_stage_finding",
    "filename",
    "original_path",
    "locator",
    "support_count",
    "evidence_count",
    "finding_count",
    "corpus_index",
    "corpus_rank",
    "corpus_ordering",
    "cache_key",
    "memoized_finding",
    "env_leak",
    "inherited_findings",
    "cumulative_corpus",
    "gap_map",
    "coverage_obligations",
})


def _ref_dict(ref: Any) -> dict:
    if isinstance(ref, Mapping):
        return dict(ref)
    if hasattr(ref, "as_dict"):
        return ref.as_dict()
    if hasattr(ref, "ref"):
        return dict(ref.ref)
    raise ValidationError("REF_REQUIRED", f"Cannot convert {type(ref)} to ref dict")


def _discovery_binding_digest(discovery: Mapping[str, Any]) -> str:
    """Return a domain-separated content binding for one sealed blind discovery.

    This is a derived checkpoint binding, not a canonical ObjectDigest claim. It
    exists so equal finding counts cannot mask materially different discoveries.
    """
    preimage = b"BDB2/E3_BLIND_DISCOVERY_BINDING/1\0" + canonical_bytes(dict(discovery))
    return hashlib.sha256(preimage).hexdigest()


def _discovery_bindings_by_lane(
    discoveries: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, list[str]]:
    """Bind exact discovery content with deterministic, order-independent lists."""
    return {
        slot: sorted(_discovery_binding_digest(item) for item in discoveries.get(slot, ()))
        for slot in E3_LANE_SLOTS
    }


def build_e3_stage_spec(revision: str = "1") -> StageSpec:
    """Construct normative E3 StageSpec (R5.3 §23)."""
    return StageSpec(
        stage_key="E3",
        stage_spec_revision=revision,
        stage_role="EXPAND_AND_HUNT",
        stage_ordinal=3,
        purpose="Independent novelty expansion via blind lanes followed by gap-directed search",
        predecessor_requirements=("E2",),
        required_lane_slots=E3_LANE_SLOTS,
        blind_reveal_phase_model="AFTER_CHECKPOINT",
        required_stage_completion_outputs=("blind_checkpoint", "gap_directed_records", "stage_completion_digest"),
        stop_e6_relationship="CONTINUE_REQUIRED",
    )


def build_e3_lane_specs(
    stage_spec_revision: str = "1",
    lane_revision: str = "1",
    required_isolation_assurance: str = "DECLARED",
) -> dict[str, LaneSpec]:
    """Construct E3 blind LaneSpecs without overstating executor isolation."""
    specs = {}
    for slot in E3_LANE_SLOTS:
        purpose, strategy = E3_LANE_STRATEGIES[slot]
        specs[slot] = LaneSpec(
            lane_key=slot,
            lane_spec_revision=lane_revision,
            stage_spec_revision=stage_spec_revision,
            purpose=purpose,
            primary_strategy=strategy,
            required_isolation_assurance=required_isolation_assurance,
            forbidden_knowledge_classes=(
                "CUMULATIVE_FINDING_CORPUS",
                "PRIOR_STAGE_FINDINGS",
                "OTHER_LANE_UNSEALED_FINDINGS",
                "GAP_MAP",
                "COVERAGE_OBLIGATIONS",
            ),
            allowed_view_classes=(
                "BLIND_TARGET_SPECIFICATION",
                "LOCAL_EXPLORATION_CONTEXT",
            ),
            required_outputs=("discovery_records", "isolation_qualification"),
        )
    return specs


def create_result_slot_contract(
    slot_name: str = "blind_discovery_records",
    artifact_kind: str = "discovery_record",
    required: bool = True,
) -> dict:
    """Construct an explicit result slot contract for blind attempts."""
    return {
        "slot_name": slot_name,
        "artifact_kind": artifact_kind,
        "required": required,
        "allowed_classes": ["PRE_REVEAL_DISCOVERY"],
    }


class E3QuarantineBroker:
    """Enforces knowledge boundaries, prevents cross-lane contamination, and blocks disallowed reveals."""

    def __init__(self):
        self._sealed_findings: dict[str, list[dict]] = {slot: [] for slot in E3_LANE_SLOTS}
        self._isolation_qualifications: dict[str, IsolationQualification] = {}
        self._is_checkpoint_sealed: bool = False
        self._checkpoint_digest: str | None = None

    @property
    def is_checkpoint_sealed(self) -> bool:
        return self._is_checkpoint_sealed

    @property
    def checkpoint_digest(self) -> str | None:
        return self._checkpoint_digest

    def discovery_bindings(self) -> dict[str, list[str]]:
        """Return deterministic bindings for all currently sealed discoveries."""
        return _discovery_bindings_by_lane(self._sealed_findings)

    def check_for_disallowed_leak(self, data: Any, path: str = "") -> None:
        """Scan input data recursively for forbidden leak fields."""
        if isinstance(data, Mapping):
            for k, v in data.items():
                if k in FORBIDDEN_BLIND_LEAK_FIELDS:
                    raise ValidationError(
                        "DISALLOWED_KNOWLEDGE_REVEAL",
                        f"Forbidden field '{k}' detected at '{path}.{k}' in blind context",
                    )
                self.check_for_disallowed_leak(v, f"{path}.{k}" if path else str(k))
        elif isinstance(data, (list, tuple)):
            for idx, item in enumerate(data):
                self.check_for_disallowed_leak(item, f"{path}[{idx}]")

    def register_isolation_qualification(
        self,
        lane_slot: str,
        qualification: IsolationQualification,
    ) -> None:
        if lane_slot not in E3_LANE_SLOTS:
            raise ValidationError("UNKNOWN_LANE_SLOT", f"Invalid lane slot: {lane_slot}")
        required = qualification.required_isolation_assurance
        actual = qualification.isolation_class
        if actual == "UNKNOWN":
            raise ValidationError(
                "BLIND_ORIGIN_ISOLATION_NOT_QUALIFIED",
                f"Lane {lane_slot} has UNKNOWN isolation assurance",
            )
        if required == "ENFORCED" and actual != "ENFORCED":
            raise ValidationError(
                "BLIND_ORIGIN_ISOLATION_NOT_QUALIFIED",
                f"Lane {lane_slot} requires ENFORCED isolation, got {actual}",
            )
        if required == "DECLARED" and actual not in {"DECLARED", "ENFORCED"}:
            raise ValidationError(
                "BLIND_ORIGIN_ISOLATION_NOT_QUALIFIED",
                f"Lane {lane_slot} requires at least DECLARED isolation, got {actual}",
            )
        if qualification.contaminated:
            raise ValidationError(
                "LANE_CONTAMINATED",
                f"Lane {lane_slot} is contaminated and cannot participate in blind novelty",
            )
        self._isolation_qualifications[lane_slot] = qualification

    def record_lane_discovery(
        self,
        lane_slot: str,
        discovery: dict,
    ) -> None:
        if lane_slot not in E3_LANE_SLOTS:
            raise ValidationError("UNKNOWN_LANE_SLOT", f"Invalid lane slot: {lane_slot}")
        if self._is_checkpoint_sealed:
            raise ValidationError(
                "CHECKPOINT_ALREADY_SEALED",
                "Cannot add blind discoveries after checkpoint seal",
            )
        # Check adversarial leakage
        self.check_for_disallowed_leak(discovery)

        # Enforce isolation qualification registered
        if lane_slot not in self._isolation_qualifications:
            raise ValidationError(
                "ISOLATION_QUALIFICATION_REQUIRED",
                f"Lane {lane_slot} must have an accepted isolation qualification before recording discoveries",
            )

        # Must be classified as PRE_REVEAL_DISCOVERY
        classification = discovery.get("classification", "PRE_REVEAL_DISCOVERY")
        if classification != "PRE_REVEAL_DISCOVERY":
            raise ValidationError(
                "INVALID_BLIND_CLASSIFICATION",
                f"Blind discovery must be PRE_REVEAL_DISCOVERY, got {classification}",
            )

        self._sealed_findings[lane_slot].append(dict(discovery))

    def get_lane_view(self, requesting_lane: str) -> list[dict]:
        """A lane can ONLY see its own findings prior to checkpoint release."""
        if requesting_lane not in E3_LANE_SLOTS:
            raise ValidationError("UNKNOWN_LANE_SLOT", requesting_lane)
        return list(self._sealed_findings[requesting_lane])

    def query_cross_lane_findings(
        self,
        requesting_lane: str,
        target_lane: str,
    ) -> list[dict]:
        """Adversarial check: requesting another lane's unreleased findings must fail closed."""
        if not self._is_checkpoint_sealed and requesting_lane != target_lane:
            raise ValidationError(
                "CROSS_LANE_KNOWLEDGE_LEAKAGE",
                f"Blind lane {requesting_lane} cannot access unsealed findings of {target_lane}",
            )
        return list(self._sealed_findings[target_lane])

    def query_finding_corpus(self, requesting_lane: str) -> None:
        """Adversarial check: requesting prior stage or cumulative finding corpus must fail closed."""
        if not self._is_checkpoint_sealed:
            raise ValidationError(
                "KNOWLEDGE_BOUNDARY_VIOLATION",
                f"Blind lane {requesting_lane} cannot access prior finding corpus before checkpoint seal",
            )

    def seal_checkpoint(self, accepted_history_cut: dict) -> dict[str, Any]:
        """Seal E3 blind discoveries into an immutable checkpoint."""
        if self._is_checkpoint_sealed:
            raise ValidationError("CHECKPOINT_ALREADY_SEALED", "Checkpoint has already been sealed")

        # Verify all 3 lanes have completed isolation qualification
        for slot in E3_LANE_SLOTS:
            if slot not in self._isolation_qualifications:
                raise ValidationError(
                    "MANDATORY_LANE_MISSING",
                    f"Cannot seal checkpoint: lane {slot} has not qualified isolation",
                )

        self._is_checkpoint_sealed = True
        body = {
            "checkpoint_type": "E3_BLIND_NOVELTY_CHECKPOINT",
            "accepted_history_cut": dict(accepted_history_cut),
            "lane_discoveries_count": {slot: len(self._sealed_findings[slot]) for slot in E3_LANE_SLOTS},
            "sealed_discovery_digests": self.discovery_bindings(),
            "lane_slots": list(E3_LANE_SLOTS),
        }
        self._checkpoint_digest = hashlib.sha256(canonical_bytes(body)).hexdigest()
        return {
            "checkpoint_digest": self._checkpoint_digest,
            "body": body,
            "sealed_findings": {slot: list(f) for slot, f in self._sealed_findings.items()},
        }


@dataclass(frozen=True)
class E3BlindAttemptContext:
    attempt: Attempt
    isolation_qualification: IsolationQualification
    knowledge_state: KnowledgeState
    result_slot_contract: dict


def create_e3_blind_attempt(
    lane_slot: str,
    lane_run_ref: Mapping,
    assigned_history_cut: Mapping,
    executor_profile_ref: Mapping,
    delivery_profile_ref: Mapping,
    boundary_evidence_refs: Mapping[str, Sequence[Mapping]] | None = None,
    nonce: str | None = None,
    isolation_assurance: str = "DECLARED",
    fresh_session_boundary: bool = False,
    forbidden_channel_access: bool = False,
    contaminated: bool = False,
) -> E3BlindAttemptContext:
    """Construct a blind attempt with an honest, caller-supplied isolation class."""
    if lane_slot not in E3_LANE_SLOTS:
        raise ValidationError("UNKNOWN_LANE_SLOT", f"Invalid lane slot: {lane_slot}")

    attempt_nonce = nonce or hashlib.sha256(f"{lane_slot}_{new_id('attempt')}".encode()).hexdigest()[:16]
    attempt_id = f"attempt_e3_{lane_slot.lower()}_{attempt_nonce}"

    slot_contract = create_result_slot_contract(
        slot_name=f"{lane_slot.lower()}_blind_records",
        artifact_kind="discovery_record",
        required=True,
    )

    attempt = Attempt(
        attempt_id=attempt_id,
        lane_run_ref=lane_run_ref,
        attempt_nonce=attempt_nonce,
        executor_profile_ref=executor_profile_ref,
        delivery_profile_ref=delivery_profile_ref,
        assigned_history_cut=assigned_history_cut,
        result_slot_contracts=(slot_contract,),
    )
    attempt_ref = attempt.as_object().ref.as_dict()

    ev = boundary_evidence_refs or {}
    allowed_isolation = {"ENFORCED", "DECLARED", "UNKNOWN"}
    if isolation_assurance not in allowed_isolation:
        raise ValidationError(
            "ISOLATION_CLASS_INVALID",
            f"Unsupported E3 isolation class: {isolation_assurance}",
        )

    evidence_keys = (
        "enforcement_receipt_refs",
        "filesystem_boundary_evidence_refs",
        "network_boundary_evidence_refs",
        "tool_boundary_evidence_refs",
        "session_boundary_evidence_refs",
    )
    if isolation_assurance == "ENFORCED":
        missing_evidence = [
            key
            for key in evidence_keys
            if not tuple(ev.get(key, ()))
        ]
        if (
            not fresh_session_boundary
            or forbidden_channel_access
            or contaminated
            or missing_evidence
        ):
            details = ", ".join(missing_evidence) or "boundary state"
            raise ValidationError(
                "E3_ENFORCED_BOUNDARY_EVIDENCE_REQUIRED",
                (
                    "ENFORCED E3 isolation requires a fresh uncontaminated "
                    f"session and explicit material-channel witnesses; missing: {details}"
                ),
            )

    iso_qual = IsolationQualification(
        attempt_ref=attempt_ref,
        assessment_input_history_cut=assigned_history_cut,
        executor_profile_ref=executor_profile_ref,
        delivery_profile_ref=delivery_profile_ref,
        isolation_class=isolation_assurance,
        contaminated=contaminated,
        fresh_session_boundary=fresh_session_boundary,
        forbidden_channel_access=forbidden_channel_access,
        enforcement_receipt_refs=tuple(ev.get("enforcement_receipt_refs", ())),
        filesystem_boundary_evidence_refs=tuple(ev.get("filesystem_boundary_evidence_refs", ())),
        network_boundary_evidence_refs=tuple(ev.get("network_boundary_evidence_refs", ())),
        tool_boundary_evidence_refs=tuple(ev.get("tool_boundary_evidence_refs", ())),
        session_boundary_evidence_refs=tuple(ev.get("session_boundary_evidence_refs", ())),
        isolation_qualification_id=f"iso_{attempt_id}",
        required_isolation_assurance=isolation_assurance,
        scope=f"E3 blind lane {lane_slot}",
    )
    iso_ref = iso_qual.as_object().ref.as_dict()

    knowledge_state = KnowledgeState(
        attempt_ref=attempt_ref,
        basis_history_cut=assigned_history_cut,
        isolation_qualification_ref=iso_ref,
        allowed_view_refs=(),
        potential_exposure_refs=(),
        contamination_assessment_refs=(),
        known_classes=("LOCAL_EXPLORATION_CONTEXT",),
    )

    return E3BlindAttemptContext(
        attempt=attempt,
        isolation_qualification=iso_qual,
        knowledge_state=knowledge_state,
        result_slot_contract=slot_contract,
    )


@dataclass(frozen=True)
class E3BlindNoveltyResult:
    stage_key: str
    stage_spec_digest: str
    assigned_history_cut: dict
    completed_lanes: tuple[str, ...]
    total_discoveries: int
    discoveries_by_lane: dict[str, list[dict]]
    blind_completion_digest: str
    quarantined_claims: tuple[dict, ...]
    broker: E3QuarantineBroker

    def as_dict(self) -> dict:
        return {
            "stage_key": self.stage_key,
            "mode": "BLIND_NOVELTY",
            "stage_spec_digest": self.stage_spec_digest,
            "completed_lanes": list(self.completed_lanes),
            "total_discoveries": self.total_discoveries,
            "blind_completion_digest": self.blind_completion_digest,
            "quarantined_claims_count": len(self.quarantined_claims),
        }


def execute_e3_blind_ensemble(
    source_generation_ref: Any,
    assigned_history_cut: Mapping,
    lane_contexts: Mapping[str, E3BlindAttemptContext],
    lane_discoveries: Mapping[str, Sequence[dict]],
    stage_spec: StageSpec | None = None,
) -> E3BlindNoveltyResult:
    """Execute E3 blind novelty ensemble across E3-X, E3-Y, E3-Z.

    Fails closed if:
    - any mandatory lane is missing;
    - any lane has UNKNOWN or insufficient isolation for its declared requirement;
    - any forbidden knowledge leakage is detected.
    """
    spec = stage_spec or build_e3_stage_spec()

    # Verify all 3 mandatory lanes are reported
    reported_lanes = set(lane_discoveries.keys())
    missing = set(spec.required_lane_slots) - reported_lanes
    if missing:
        raise ValidationError(
            "MANDATORY_LANE_MISSING",
            f"Missing required E3 blind novelty lanes: {sorted(missing)}",
        )

    broker = E3QuarantineBroker()
    all_quarantined: list[dict] = []
    total_count = 0

    for slot in sorted(spec.required_lane_slots):
        ctx = lane_contexts.get(slot)
        if ctx is None:
            raise ValidationError(
                "MANDATORY_LANE_MISSING",
                f"Missing attempt context for mandatory lane: {slot}",
            )
        broker.register_isolation_qualification(slot, ctx.isolation_qualification)

        disc_list = lane_discoveries.get(slot, [])
        for d in disc_list:
            broker.record_lane_discovery(slot, d)
            claim_data = dict(d)
            claim_data["originating_lane"] = slot
            claim_data["attempt_ref"] = ctx.attempt.as_object().ref.as_dict()
            claim_data["knowledge_state_ref"] = ctx.knowledge_state.as_object().ref.as_dict()
            claim_data["classification"] = "PRE_REVEAL_DISCOVERY"
            all_quarantined.append(claim_data)
            total_count += 1

    # Deterministic blind completion digest (strictly distinct from revealed/gap-directed digests)
    completion_body = {
        "stage_key": "E3",
        "mode": "BLIND_NOVELTY",
        "stage_spec_digest": spec.revision_digest,
        "completed_lanes": sorted(spec.required_lane_slots),
        "source_generation_ref": _ref_dict(source_generation_ref),
        "assigned_history_cut": dict(assigned_history_cut),
        "total_discoveries": total_count,
        "sealed_discovery_digests": broker.discovery_bindings(),
    }
    blind_comp_digest = hashlib.sha256(canonical_bytes(completion_body)).hexdigest()

    return E3BlindNoveltyResult(
        stage_key="E3",
        stage_spec_digest=spec.revision_digest,
        assigned_history_cut=dict(assigned_history_cut),
        completed_lanes=tuple(sorted(spec.required_lane_slots)),
        total_discoveries=total_count,
        discoveries_by_lane={slot: list(lane_discoveries.get(slot, [])) for slot in spec.required_lane_slots},
        blind_completion_digest=blind_comp_digest,
        quarantined_claims=tuple(all_quarantined),
        broker=broker,
    )
