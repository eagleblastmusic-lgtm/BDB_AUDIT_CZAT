"""Native E3 Novelty Expansion, Blind Lanes, and Checkpoint/Reveal Orchestration (WP-F5 / M24-M27)."""
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
import hashlib

from ..core.canonical_json import canonical_bytes, parse
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


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(child) for child in value]
    return value


def _canonical_copy(value: Any) -> Any:
    """Copy JSON contract data through the canonical parser, rejecting aliases."""
    return parse(canonical_bytes(_json_value(value)))


def _same_canonical(left: Any, right: Any) -> bool:
    return canonical_bytes(_json_value(left)) == canonical_bytes(_json_value(right))


def _require_ref_kind(ref: Mapping, expected_kind: str) -> bool:
    return (
        isinstance(ref, Mapping)
        and ref.get("kind") == expected_kind
        and isinstance(ref.get("revision_digest"), str)
        and len(ref["revision_digest"]) == 64
        and ref.get("digest_profile") == "BDB-OBJECT-DIGEST-1"
    )


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
        transition_policy_ref="TRANSITION_PROFILE_V1",
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
        self._isolation_qualifications: dict[str, str] = {}
        self._is_checkpoint_sealed: bool = False
        self._checkpoint_digest: str | None = None
        self._checkpoint_cut_bytes: bytes | None = None
        self._sealed_checkpoint: dict[str, Any] | None = None

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
        if required not in {"DECLARED", "ENFORCED"}:
            raise ValidationError(
                "BLIND_ORIGIN_ISOLATION_NOT_QUALIFIED",
                (
                    f"Lane {lane_slot} lacks an explicit qualified "
                    f"isolation requirement: {required}"
                ),
            )
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
        if qualification.forbidden_channel_access:
            raise ValidationError(
                "BLIND_ORIGIN_ISOLATION_NOT_QUALIFIED",
                f"Lane {lane_slot} has known forbidden-channel access",
            )
        if qualification.contaminated:
            raise ValidationError(
                "LANE_CONTAMINATED",
                f"Lane {lane_slot} is contaminated and cannot participate in blind novelty",
            )
        self._isolation_qualifications[lane_slot] = qualification.as_object().digest

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

        self._sealed_findings[lane_slot].append(_canonical_copy(discovery))

    def get_lane_view(self, requesting_lane: str) -> list[dict]:
        """A lane can ONLY see its own findings prior to checkpoint release."""
        if requesting_lane not in E3_LANE_SLOTS:
            raise ValidationError("UNKNOWN_LANE_SLOT", requesting_lane)
        return _canonical_copy(self._sealed_findings[requesting_lane])

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
        return _canonical_copy(self._sealed_findings[target_lane])

    def query_finding_corpus(self, requesting_lane: str) -> None:
        """Adversarial check: requesting prior stage or cumulative finding corpus must fail closed."""
        if not self._is_checkpoint_sealed:
            raise ValidationError(
                "KNOWLEDGE_BOUNDARY_VIOLATION",
                f"Blind lane {requesting_lane} cannot access prior finding corpus before checkpoint seal",
            )

    def seal_checkpoint(self, accepted_history_cut: dict) -> dict[str, Any]:
        """Seal E3 blind discoveries into an immutable checkpoint."""
        cut = _canonical_copy(accepted_history_cut)
        cut_bytes = canonical_bytes(cut)
        if self._is_checkpoint_sealed:
            if cut_bytes != self._checkpoint_cut_bytes:
                raise ValidationError(
                    "CHECKPOINT_SEAL_BASIS_MISMATCH",
                    "Checkpoint was already sealed against a different exact history cut",
                )
            return _canonical_copy(self._sealed_checkpoint)

        # Verify all 3 lanes have completed isolation qualification
        for slot in E3_LANE_SLOTS:
            if slot not in self._isolation_qualifications:
                raise ValidationError(
                    "MANDATORY_LANE_MISSING",
                    f"Cannot seal checkpoint: lane {slot} has not qualified isolation",
                )

        body = {
            "checkpoint_type": "E3_BLIND_NOVELTY_CHECKPOINT",
            "accepted_history_cut": cut,
            "lane_discoveries_count": {slot: len(self._sealed_findings[slot]) for slot in E3_LANE_SLOTS},
            "sealed_discovery_digests": self.discovery_bindings(),
            "isolation_qualification_digests": {
                slot: self._isolation_qualifications[slot]
                for slot in E3_LANE_SLOTS
            },
            "lane_slots": list(E3_LANE_SLOTS),
        }
        self._checkpoint_digest = hashlib.sha256(canonical_bytes(body)).hexdigest()
        result = {
            "checkpoint_digest": self._checkpoint_digest,
            "authority_status": "PREVIEW_ONLY",
            "body": body,
            "sealed_findings": _canonical_copy(self._sealed_findings),
        }
        self._checkpoint_cut_bytes = cut_bytes
        self._sealed_checkpoint = _canonical_copy(result)
        self._is_checkpoint_sealed = True
        return _canonical_copy(self._sealed_checkpoint)


@dataclass(frozen=True)
class E3BlindAttemptContext:
    lane_slot: str
    source_generation_ref: Mapping | None
    attempt: Attempt
    isolation_qualification: IsolationQualification
    knowledge_state: KnowledgeState
    result_slot_contract: dict
    binding_digest: str = ""

    def __post_init__(self):
        payload = _e3_context_binding_payload(
            self.lane_slot,
            self.source_generation_ref,
            self.attempt,
            self.isolation_qualification,
            self.knowledge_state,
            self.result_slot_contract,
        )
        digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        if self.binding_digest and self.binding_digest != digest:
            raise ValidationError("E3_ATTEMPT_CONTEXT_BINDING_MISMATCH")
        object.__setattr__(self, "binding_digest", digest)


def _e3_context_binding_payload(
    lane_slot: str,
    source_generation_ref: Mapping | None,
    attempt: Attempt,
    isolation_qualification: IsolationQualification,
    knowledge_state: KnowledgeState,
    result_slot_contract: Mapping,
) -> dict[str, Any]:
    return {
        "lane_slot": lane_slot,
        "source_generation_ref": _canonical_copy(dict(source_generation_ref))
        if source_generation_ref is not None
        else None,
        "attempt": _canonical_copy(attempt.body()),
        "isolation_qualification": _canonical_copy(
            isolation_qualification.body()
        ),
        "knowledge_state": _canonical_copy(knowledge_state.body()),
        "result_slot_contract": _canonical_copy(dict(result_slot_contract)),
    }


def create_e3_blind_attempt(
    lane_slot: str,
    lane_run_ref: Mapping,
    assigned_history_cut: Mapping,
    executor_profile_ref: Mapping,
    delivery_profile_ref: Mapping,
    boundary_evidence_refs: Mapping[str, Sequence[Mapping]] | None = None,
    channel_inventory_ref: Mapping | None = None,
    nonce: str | None = None,
    isolation_assurance: str = "DECLARED",
    fresh_session_boundary: bool = False,
    forbidden_channel_access: bool = False,
    contaminated: bool = False,
    source_generation_ref: Mapping | None = None,
) -> E3BlindAttemptContext:
    """Construct a blind attempt with an honest, caller-supplied isolation class."""
    if lane_slot not in E3_LANE_SLOTS:
        raise ValidationError("UNKNOWN_LANE_SLOT", f"Invalid lane slot: {lane_slot}")
    if source_generation_ref is None:
        raise ValidationError(
            "E3_SOURCE_GENERATION_REQUIRED",
            "A blind attempt must be bound to its exact source generation",
        )

    lane_run_ref = _canonical_copy(dict(lane_run_ref))
    assigned_history_cut = _canonical_copy(dict(assigned_history_cut))
    executor_profile_ref = _canonical_copy(dict(executor_profile_ref))
    delivery_profile_ref = _canonical_copy(dict(delivery_profile_ref))
    source_generation_ref = _canonical_copy(dict(source_generation_ref))

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

    if channel_inventory_ref is None:
        raise ValidationError(
            "E3_CHANNEL_INVENTORY_REQUIRED",
            "E3 isolation qualification requires an explicit channel inventory",
        )

    ev = boundary_evidence_refs or {}
    allowed_isolation = {"ENFORCED", "DECLARED", "UNKNOWN"}
    if isolation_assurance not in allowed_isolation:
        raise ValidationError(
            "ISOLATION_CLASS_INVALID",
            f"Unsupported E3 isolation class: {isolation_assurance}",
        )

    if isolation_assurance == "ENFORCED":
        evidence_keys = (
            "enforcement_receipt_refs",
            "filesystem_boundary_evidence_refs",
            "network_boundary_evidence_refs",
            "tool_boundary_evidence_refs",
            "session_boundary_evidence_refs",
        )
        missing_evidence = [key for key in evidence_keys if not tuple(ev.get(key, ()))]
        if not fresh_session_boundary or forbidden_channel_access or contaminated or missing_evidence:
            raise ValidationError(
                "E3_ENFORCED_BOUNDARY_EVIDENCE_REQUIRED",
                "ENFORCED E3 needs uncontaminated boundary assertions and supplied witness refs",
            )
        raise ValidationError(
            "ISOLATION_ADMISSION_CONTEXT_REQUIRED",
            "The reference helper cannot resolve accepted Executor/Lane material-channel policy and evidence",
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
        channel_inventory_ref=(
            dict(channel_inventory_ref)
            if channel_inventory_ref is not None
            else None
        ),
        enforcement_receipt_refs=tuple(ev.get("enforcement_receipt_refs", ())),
        filesystem_boundary_evidence_refs=tuple(ev.get("filesystem_boundary_evidence_refs", ())),
        network_boundary_evidence_refs=tuple(ev.get("network_boundary_evidence_refs", ())),
        tool_boundary_evidence_refs=tuple(ev.get("tool_boundary_evidence_refs", ())),
        session_boundary_evidence_refs=tuple(ev.get("session_boundary_evidence_refs", ())),
        isolation_qualification_id=f"iso_{attempt_id}",
        required_isolation_assurance=isolation_assurance,
        scope=f"E3 blind lane {lane_slot}",
        limitations=(
            ("Manual/declared isolation; enforcement is not proven",)
            if isolation_assurance == "DECLARED"
            else ()
        ),
        reason_codes=(
            ("DECLARED_ISOLATION_ONLY",)
            if isolation_assurance == "DECLARED"
            else ()
        ),
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
        lane_slot=lane_slot,
        source_generation_ref=source_generation_ref,
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
            "authority_status": "PREVIEW_ONLY",
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
    source_ref = _canonical_copy(_ref_dict(source_generation_ref))
    assigned_cut = _canonical_copy(dict(assigned_history_cut))

    # Verify all 3 mandatory lanes are reported
    reported_lanes = set(lane_discoveries.keys())
    missing = set(spec.required_lane_slots) - reported_lanes
    if missing:
        raise ValidationError(
            "MANDATORY_LANE_MISSING",
            f"Missing required E3 blind novelty lanes: {sorted(missing)}",
        )
    if reported_lanes != set(spec.required_lane_slots) or set(lane_contexts) != set(spec.required_lane_slots):
        raise ValidationError("E3_LANE_SET_MISMATCH")
    if not _require_ref_kind(source_ref, "source_generation"):
        raise ValidationError("E3_SOURCE_GENERATION_REF_INVALID")
    if assigned_cut.get("variant") != "ACCEPTED_HISTORY_CUT":
        raise ValidationError("E3_ACCEPTED_HISTORY_CUT_REQUIRED")

    broker = E3QuarantineBroker()
    all_quarantined: list[dict] = []
    total_count = 0
    attempt_digests: set[str] = set()
    lane_run_digests: set[str] = set()

    for slot in sorted(spec.required_lane_slots):
        ctx = lane_contexts.get(slot)
        if ctx is None:
            raise ValidationError(
                "MANDATORY_LANE_MISSING",
                f"Missing attempt context for mandatory lane: {slot}",
            )
        current_binding = _e3_context_binding_payload(
            ctx.lane_slot,
            ctx.source_generation_ref,
            ctx.attempt,
            ctx.isolation_qualification,
            ctx.knowledge_state,
            ctx.result_slot_contract,
        )
        if (
            ctx.binding_digest
            != hashlib.sha256(canonical_bytes(current_binding)).hexdigest()
            or ctx.lane_slot != slot
            or ctx.source_generation_ref is None
            or not _same_canonical(ctx.source_generation_ref, source_ref)
            or not _same_canonical(ctx.attempt.assigned_history_cut, assigned_cut)
            or not _same_canonical(
                ctx.isolation_qualification.assessment_input_history_cut,
                assigned_cut,
            )
            or not _same_canonical(ctx.knowledge_state.basis_history_cut, assigned_cut)
            or not _same_canonical(
                ctx.isolation_qualification.attempt_ref,
                ctx.attempt.as_object().ref.as_dict(),
            )
            or not _same_canonical(
                ctx.knowledge_state.attempt_ref,
                ctx.attempt.as_object().ref.as_dict(),
            )
            or not _same_canonical(
                ctx.isolation_qualification.executor_profile_ref,
                ctx.attempt.executor_profile_ref,
            )
            or not _same_canonical(
                ctx.isolation_qualification.delivery_profile_ref,
                ctx.attempt.delivery_profile_ref,
            )
            or not _same_canonical(
                ctx.knowledge_state.isolation_qualification_ref,
                ctx.isolation_qualification.as_object().ref.as_dict(),
            )
            or not _require_ref_kind(ctx.attempt.lane_run_ref, "lane_run")
            or not _require_ref_kind(ctx.attempt.executor_profile_ref, "executor_profile")
            or not _require_ref_kind(ctx.attempt.delivery_profile_ref, "delivery_profile")
            or not _require_ref_kind(
                ctx.attempt.as_object().ref.as_dict(),
                "attempt",
            )
            or ctx.isolation_qualification.required_isolation_assurance
            != build_e3_lane_specs(spec.stage_spec_revision)[slot].required_isolation_assurance
            or not _same_canonical(
                ctx.attempt.result_slot_contracts,
                (ctx.result_slot_contract,),
            )
            or ctx.knowledge_state.previous_knowledge_state_ref is not None
            or ctx.knowledge_state.allowed_view_refs
            or ctx.knowledge_state.potential_exposure_refs
        ):
            raise ValidationError(
                "E3_ATTEMPT_CONTEXT_MISMATCH",
                f"Lane {slot} context does not match the exact blind-run source, cut, attempt and profiles",
            )
        attempt_digest = ctx.attempt.as_object().digest
        lane_run_digest = ctx.attempt.lane_run_ref.get("revision_digest")
        if (
            attempt_digest in attempt_digests
            or lane_run_digest in lane_run_digests
            or not lane_run_digest
        ):
            raise ValidationError(
                "E3_LANE_ATTEMPT_REUSED",
                f"Each blind lane requires a distinct attempt and lane run: {slot}",
            )
        attempt_digests.add(attempt_digest)
        lane_run_digests.add(lane_run_digest)
        broker.register_isolation_qualification(slot, ctx.isolation_qualification)

        disc_list = lane_discoveries.get(slot, [])
        for d in disc_list:
            discovery = _canonical_copy(dict(d))
            broker.record_lane_discovery(slot, discovery)
            claim_data = _canonical_copy(discovery)
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
        "source_generation_ref": source_ref,
        "assigned_history_cut": assigned_cut,
        "total_discoveries": total_count,
        "sealed_discovery_digests": broker.discovery_bindings(),
    }
    blind_comp_digest = hashlib.sha256(canonical_bytes(completion_body)).hexdigest()
    broker.seal_checkpoint(assigned_cut)

    return E3BlindNoveltyResult(
        stage_key="E3",
        stage_spec_digest=spec.revision_digest,
        assigned_history_cut=_canonical_copy(assigned_cut),
        completed_lanes=tuple(sorted(spec.required_lane_slots)),
        total_discoveries=total_count,
        discoveries_by_lane={
            slot: _canonical_copy(list(lane_discoveries.get(slot, [])))
            for slot in spec.required_lane_slots
        },
        blind_completion_digest=blind_comp_digest,
        quarantined_claims=tuple(all_quarantined),
        broker=broker,
    )
