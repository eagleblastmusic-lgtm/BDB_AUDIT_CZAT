"""Adaptive E6 Generator (WP-E5-11 / M45 / §104 / Data Contracts §78).

E6 is represented by the ordinary canonical ``stage_spec`` contract.  The
adaptive plan is not a second artifact family: its exact accepted STOP source,
source generation, trust/isolation baseline and unresolved work are encoded in
the immutable StageSpec revision and independently re-checked by the history
authority before acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.objects import CanonicalObject, HistoryCut
from ..orchestration.stages import StageSpec
from .models import StopInput, StopEvaluation


E6_RELATIONSHIP_PROFILE = "BDB-E6-REL-1"
E6_RELATIONSHIP_PREFIX = f"{E6_RELATIONSHIP_PROFILE}|"
POST_E6_STOP_OUTPUT = "POST_E6_GLOBAL_STOP_REEVALUATION"


def _identity_digest(value: Any) -> str:
    """Return one deterministic 64-hex identity for a ref or scalar pin."""
    if isinstance(value, Mapping):
        digest = value.get("revision_digest")
        if isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest.lower()):
            return digest.lower()
        return hashlib.sha256(canonical_bytes(dict(value))).hexdigest()
    text = str(value)
    if len(text) == 64 and all(c in "0123456789abcdef" for c in text.lower()):
        return text.lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ref_token(value: Any) -> str:
    kind = value.get("kind", "scalar") if isinstance(value, Mapping) else "scalar"
    return f"BDB-REF-1:{kind}:{_identity_digest(value)}"


def _relationship_token(
    stop_evaluation_ref: Mapping[str, Any],
    source_generation_ref: Mapping[str, Any],
    trust_profile_ref: Mapping[str, Any],
    isolation_profile_ref: Mapping[str, Any],
) -> str:
    level = str(isolation_profile_ref.get("isolation_level", "UNKNOWN"))
    return (
        f"{E6_RELATIONSHIP_PROFILE}"
        f"|stop={_identity_digest(stop_evaluation_ref)}"
        f"|source={_identity_digest(source_generation_ref)}"
        f"|trust={_identity_digest(trust_profile_ref)}"
        f"|isolation={_identity_digest(isolation_profile_ref)}"
        f"|level={level}"
    )


def parse_e6_relationship(value: str) -> dict[str, str]:
    if not isinstance(value, str) or not value.startswith(E6_RELATIONSHIP_PREFIX):
        raise ValidationError("E6_STOP_RELATIONSHIP_INVALID")
    parts = value.split("|")
    if parts[0] != E6_RELATIONSHIP_PROFILE:
        raise ValidationError("E6_STOP_RELATIONSHIP_INVALID")
    parsed: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            raise ValidationError("E6_STOP_RELATIONSHIP_INVALID")
        key, item = part.split("=", 1)
        if not key or not item or key in parsed:
            raise ValidationError("E6_STOP_RELATIONSHIP_INVALID")
        parsed[key] = item
    required = {"stop", "source", "trust", "isolation", "level"}
    if set(parsed) != required:
        raise ValidationError("E6_STOP_RELATIONSHIP_INVALID")
    for key in ("stop", "source", "trust", "isolation"):
        item = parsed[key]
        if len(item) != 64 or any(c not in "0123456789abcdef" for c in item.lower()):
            raise ValidationError("E6_STOP_RELATIONSHIP_INVALID")
        parsed[key] = item.lower()
    return parsed


def _obligation_output(ref: Mapping[str, Any]) -> str:
    return f"E6_OBLIGATION:{_identity_digest(ref)}"


def _contradiction_output(ref: Mapping[str, Any]) -> str:
    return f"E6_CONTRADICTION:{_identity_digest(ref)}"


def _reason_output(reason: str) -> str:
    return f"E6_STOP_REASON:{reason}"


def _added_output(kind: str, ref: Mapping[str, Any]) -> str:
    return f"E6_ADDED_{kind}:{_identity_digest(ref)}"


def _transition_pin(stop_input: StopInput) -> str:
    cut = dict(stop_input.input_history_cut)
    refs = tuple(cut.get("governing_spec_refs", ()))
    if refs:
        return str(refs[0])
    if stop_input.policy_spec_refs:
        return _ref_token(stop_input.policy_spec_refs[0])
    raise ValidationError("E6_TRANSITION_POLICY_REQUIRED")


@dataclass(frozen=True)
class AdaptiveE6Spec:
    """Adaptive planning envelope whose canonical artifact is exactly StageSpec."""

    e6_stage_spec_id: str
    source_stop_evaluation_ref: dict[str, Any]
    source_generation_ref: dict[str, Any]
    governing_policy_ref: dict[str, Any]
    trust_profile_ref: dict[str, Any]
    isolation_profile_ref: dict[str, Any]
    inherited_unresolved_obligations: tuple[dict[str, Any], ...]
    added_surfaces: tuple[dict[str, Any], ...] = ()
    added_invariants: tuple[dict[str, Any], ...] = ()
    added_obligations: tuple[dict[str, Any], ...] = ()
    unresolved_contradictions: tuple[dict[str, Any], ...] = ()
    e6_input_history_cut: dict[str, Any] = field(default_factory=dict)
    canonical_stage_spec: StageSpec | None = None

    def __post_init__(self) -> None:
        if self.canonical_stage_spec is None:
            raise ValidationError("E6_CANONICAL_STAGE_SPEC_REQUIRED")
        if self.canonical_stage_spec.stage_key != "E6":
            raise ValidationError("E6_CANONICAL_STAGE_SPEC_REQUIRED")

    def body(self) -> dict[str, Any]:
        assert self.canonical_stage_spec is not None
        return self.canonical_stage_spec.body()

    def as_object(self) -> CanonicalObject:
        assert self.canonical_stage_spec is not None
        return self.canonical_stage_spec.as_object()

    def digest(self) -> str:
        return self.as_object().digest

    @property
    def ref(self) -> dict[str, Any]:
        return self.as_object().as_ref(ref_class="HISTORY_CONTEXT_BINDING").as_dict()


class AdaptiveE6Generator:
    """Generate one canonical adaptive E6 StageSpec from a STOP E6_REQUIRED result."""

    @staticmethod
    def generate_e6_spec(
        spec_id: str,
        stop_evaluation: StopEvaluation,
        stop_input: StopInput,
        trust_profile_ref: dict[str, Any],
        isolation_profile_ref: dict[str, Any],
        proposed_isolation_profile_ref: dict[str, Any] | None = None,
        added_surfaces: Sequence[dict[str, Any]] = (),
        added_invariants: Sequence[dict[str, Any]] = (),
        added_obligations: Sequence[dict[str, Any]] = (),
        attempted_dropped_obligation_digests: Set[str] | None = None,
        e6_input_history_cut: dict[str, Any] | None = None,
    ) -> AdaptiveE6Spec:
        if stop_evaluation.continuation_decision != "E6_REQUIRED":
            raise ValidationError(
                "E6_ONLY_FROM_E6_REQUIRED",
                f"Cannot generate E6 from STOP decision '{stop_evaluation.continuation_decision}'; requires E6_REQUIRED",
            )

        stop_input_digest = stop_input.as_object().digest
        if stop_evaluation.stop_input_ref.get("revision_digest") != stop_input_digest:
            raise ValidationError("E6_STOP_INPUT_BINDING_MISMATCH")

        remaining = tuple(dict(r) for r in stop_evaluation.remaining_obligation_refs)
        mandatory_digests = {
            r.get("revision_digest")
            for r in stop_input.mandatory_obligation_refs
            if isinstance(r, Mapping) and r.get("revision_digest")
        }
        remaining_digests = {
            r.get("revision_digest")
            for r in remaining
            if isinstance(r, Mapping) and r.get("revision_digest")
        }
        if not remaining_digests.issubset(mandatory_digests):
            raise ValidationError("E6_STOP_REMAINING_OBLIGATION_MISMATCH")
        if attempted_dropped_obligation_digests and (
            attempted_dropped_obligation_digests & remaining_digests
        ):
            raise ValidationError(
                "DENOMINATOR_MANIPULATION_FORBIDDEN",
                "E6 cannot drop mandatory unresolved obligations to manipulate the denominator",
            )

        if proposed_isolation_profile_ref is not None:
            baseline_level = isolation_profile_ref.get("isolation_level", "STRICT")
            proposed_level = proposed_isolation_profile_ref.get("isolation_level", "STRICT")
            if baseline_level == "STRICT" and proposed_level != "STRICT":
                raise ValidationError(
                    "ISOLATION_REWRITE_FORBIDDEN",
                    "E6 cannot weaken baseline isolation profile after failure observation",
                )

        unresolved_contradictions = tuple(dict(r) for r in stop_input.contradiction_refs)
        hcut = dict(e6_input_history_cut or stop_input.input_history_cut)
        accepted_cut = AdaptiveE6Generator._accepted_cut(hcut, "e6_input_history_cut")
        if accepted_cut.campaign_id != stop_input.campaign_id:
            raise ValidationError("E6_CAMPAIGN_MISMATCH")

        relation = _relationship_token(
            stop_evaluation.ref,
            stop_input.source_generation_ref,
            trust_profile_ref,
            isolation_profile_ref,
        )
        outputs = {
            POST_E6_STOP_OUTPUT,
            *(_obligation_output(r) for r in remaining),
            *(_contradiction_output(r) for r in unresolved_contradictions),
            *(_reason_output(str(reason)) for reason in stop_evaluation.reason_codes),
            *(_added_output("SURFACE", r) for r in added_surfaces),
            *(_added_output("INVARIANT", r) for r in added_invariants),
            *(_added_output("OBLIGATION", r) for r in added_obligations),
        }

        canonical = StageSpec(
            stage_key="E6",
            stage_spec_revision=f"e6-{stop_evaluation.as_object().digest[:16]}",
            stage_role="E6",
            stage_ordinal=6,
            purpose=f"Adaptive E6 continuation from accepted STOP {stop_evaluation.as_object().digest}",
            predecessor_requirements=("E5",),
            required_lane_slots=("E6_ADAPTIVE",),
            optional_lane_slots=(),
            blind_reveal_phase_model="CONTROLLED",
            allowed_corpus_roles=(),
            forbidden_corpus_roles=(),
            coverage_obligation_policy_ref=_ref_token(stop_input.governing_policy_ref),
            required_stage_completion_outputs=tuple(sorted(outputs)),
            transition_policy_ref=_transition_pin(stop_input),
            stop_e6_relationship=relation,
        )

        return AdaptiveE6Spec(
            e6_stage_spec_id=spec_id,
            source_stop_evaluation_ref=dict(stop_evaluation.ref),
            source_generation_ref=dict(stop_input.source_generation_ref),
            governing_policy_ref=dict(stop_input.governing_policy_ref),
            trust_profile_ref=dict(trust_profile_ref),
            isolation_profile_ref=dict(isolation_profile_ref),
            inherited_unresolved_obligations=remaining,
            added_surfaces=tuple(dict(r) for r in added_surfaces),
            added_invariants=tuple(dict(r) for r in added_invariants),
            added_obligations=tuple(dict(r) for r in added_obligations),
            unresolved_contradictions=unresolved_contradictions,
            e6_input_history_cut=hcut,
            canonical_stage_spec=canonical,
        )

    @staticmethod
    def generate_e6_spec_from_store(
        store,
        *,
        spec_id: str,
        stop_evaluation_ref: Mapping[str, Any],
        isolation_profile_ref: dict[str, Any],
        proposed_isolation_profile_ref: dict[str, Any] | None = None,
        added_surfaces: Sequence[dict[str, Any]] = (),
        added_invariants: Sequence[dict[str, Any]] = (),
        added_obligations: Sequence[dict[str, Any]] = (),
        attempted_dropped_obligation_digests: Set[str] | None = None,
    ) -> AdaptiveE6Spec:
        """Resolve all M45 authority inputs from one exact current accepted cut."""
        from ..workflow.read_models import current_accepted_cut

        cut = current_accepted_cut(store)
        stop_record = store.resolve_accepted(dict(stop_evaluation_ref), cut)
        if stop_record["ref"].get("kind") != "stop_evaluation":
            raise ValidationError("E6_STOP_EVALUATION_REQUIRED")
        stop_evaluation = StopEvaluation(**stop_record["body"])

        stop_input_ref = stop_evaluation.stop_input_ref
        stop_input_record = store.resolve_accepted(stop_input_ref, cut)
        if stop_input_record["ref"].get("kind") != "stop_input":
            raise ValidationError("E6_STOP_INPUT_REQUIRED")
        stop_input = StopInput(**stop_input_record["body"])

        genesis_records = store.accepted_records("campaign_genesis", cut)
        if len(genesis_records) != 1:
            raise ValidationError("E6_CAMPAIGN_GENESIS_REQUIRED")
        trust_profile_ref = genesis_records[0]["body"].get("trust_profile_ref")
        if not isinstance(trust_profile_ref, dict):
            raise ValidationError("E6_TRUST_PROFILE_REQUIRED")

        return AdaptiveE6Generator.generate_e6_spec(
            spec_id=spec_id,
            stop_evaluation=stop_evaluation,
            stop_input=stop_input,
            trust_profile_ref=trust_profile_ref,
            isolation_profile_ref=isolation_profile_ref,
            proposed_isolation_profile_ref=proposed_isolation_profile_ref,
            added_surfaces=added_surfaces,
            added_invariants=added_invariants,
            added_obligations=added_obligations,
            attempted_dropped_obligation_digests=attempted_dropped_obligation_digests,
            e6_input_history_cut=cut,
        )

    @staticmethod
    def _accepted_cut(value: dict[str, Any], label: str) -> HistoryCut:
        if not isinstance(value, dict) or value.get("variant") != "ACCEPTED_HISTORY_CUT":
            raise ValidationError(
                "ACCEPTED_HISTORY_CUT_REQUIRED",
                f"{label} must be a canonical ACCEPTED_HISTORY_CUT",
            )
        cut = HistoryCut(
            variant=value.get("variant"),
            history_namespace_ref=value.get("history_namespace_ref"),
            campaign_id=value.get("campaign_id"),
            accepted_head_seq=value.get("accepted_head_seq"),
            accepted_head_hash=value.get("accepted_head_hash"),
            governing_policy_ref=value.get("governing_policy_ref"),
            governing_spec_refs=tuple(value.get("governing_spec_refs", ())),
        )
        cut.require_accepted()
        return cut

    @staticmethod
    def verify_post_e6_return_to_stop(new_head_cut: dict[str, Any], previous_cut: dict[str, Any]) -> None:
        previous = AdaptiveE6Generator._accepted_cut(previous_cut, "previous_cut")
        new = AdaptiveE6Generator._accepted_cut(new_head_cut, "new_head_cut")

        if new.campaign_id != previous.campaign_id:
            raise ValidationError(
                "POST_E6_CAMPAIGN_MISMATCH",
                "Post-E6 STOP must remain in the same campaign",
            )

        if (
            new.accepted_head_seq <= previous.accepted_head_seq
            or new.accepted_head_hash == previous.accepted_head_hash
        ):
            raise ValidationError(
                "POST_E6_MUST_ADVANCE_HEAD",
                "Post-E6 evaluation requires a strictly newer accepted head",
            )
