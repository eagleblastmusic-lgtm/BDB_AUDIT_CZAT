"""Adaptive E6 Generator (WP-E5-11 / M45 / §104 / Data Contracts §78).

The canonical authority for adaptive E6 is an immutable ``StageSpec`` revision.
Planner metadata remains available on ``AdaptiveE6Spec`` for orchestration, but
``body()`` / ``as_object()`` expose only the exact StageSpec wire contract.

Authoritative acceptance proves that ``stop_e6_relationship`` points to the
latest prior accepted ``StopEvaluation=E6_REQUIRED`` and its exact accepted
``StopInput``.  Repeated POST_E6 rounds inherit the latest accepted E6 StageSpec,
so earlier strengthening cannot disappear in a later adaptive round.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.registry import canonical_reference_set
from ..history.objects import AcceptedHead, CanonicalObject, HistoryCut
from ..orchestration.stages import StageSpec
from .models import StopInput, StopEvaluation


_RELATIONSHIP_TYPE = "ADAPTIVE_E6_FROM_ACCEPTED_STOP_V1"
_POST_E6_OUTPUT = "POST_E6_STOP_REEVALUATION"
_RELATIONSHIP_KEYS = {
    "relationship_type",
    "source_stop_evaluation_ref",
    "source_stop_input_ref",
    "baseline_stage_spec_ref",
    "e6_input_history_cut",
    "source_generation_ref",
    "governing_policy_ref",
    "governing_policy_pin",
    "governing_spec_pins",
    "trust_profile_ref",
    "isolation_profile_ref",
    "inherited_unresolved_obligations",
    "unknown_blocked_summary",
    "unresolved_contradictions",
    "added_surfaces",
    "added_invariants",
    "added_obligations",
    "source_stop_reason_codes",
}


def _canonical_refs(values: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    return tuple(canonical_reference_set([dict(value) for value in values]))


def _merge_canonical_refs(*groups: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    unique: dict[bytes, dict[str, Any]] = {}
    for group in groups:
        for value in group:
            ref = dict(value)
            unique[canonical_bytes(ref)] = ref
    return tuple(canonical_reference_set(list(unique.values())))


def _digest_set(values: Sequence[Mapping[str, Any]]) -> set[str]:
    return {
        str(value.get("revision_digest"))
        for value in values
        if isinstance(value, Mapping) and isinstance(value.get("revision_digest"), str)
    }


def _same_digest(left: Any, right: Any) -> bool:
    return (
        isinstance(left, Mapping)
        and isinstance(right, Mapping)
        and left.get("revision_digest") == right.get("revision_digest")
    )


def _canonical_relationship(payload: dict[str, Any]) -> str:
    return canonical_bytes(payload).decode("utf-8")


def _parse_relationship(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        raise ValidationError("E6_STOP_RELATIONSHIP_REQUIRED")
    try:
        payload = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("E6_STOP_RELATIONSHIP_INVALID") from exc
    if not isinstance(payload, dict) or set(payload) != _RELATIONSHIP_KEYS:
        raise ValidationError("E6_STOP_RELATIONSHIP_INVALID")
    if _canonical_relationship(payload) != value:
        raise ValidationError("E6_STOP_RELATIONSHIP_NONCANONICAL")
    if payload.get("relationship_type") != _RELATIONSHIP_TYPE:
        raise ValidationError("E6_STOP_RELATIONSHIP_INVALID")
    return payload


@dataclass(frozen=True)
class AdaptiveE6Spec:
    """Planner view whose canonical authority is ``stage_spec`` only."""

    stage_spec: StageSpec
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

    @property
    def e6_stage_spec_id(self) -> str:
        return self.stage_spec.stage_spec_revision

    def body(self) -> dict[str, Any]:
        """Return the exact canonical ``StageSpec`` body, never planner metadata."""
        return self.stage_spec.body()

    def as_object(self) -> CanonicalObject:
        return self.stage_spec.as_object()

    def digest(self) -> str:
        return self.as_object().digest

    @property
    def ref(self) -> dict[str, Any]:
        return dict(self.stage_spec.ref)

    @property
    def relationship_payload(self) -> dict[str, Any]:
        return _parse_relationship(self.stage_spec.stop_e6_relationship)


class AdaptiveE6Generator:
    """Build adaptive E6 plans and authoritative-ready StageSpec revisions."""

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
        baseline_stage_spec: StageSpec | None = None,
        source_stop_evaluation_ref: Mapping[str, Any] | None = None,
        source_stop_input_ref: Mapping[str, Any] | None = None,
    ) -> AdaptiveE6Spec:
        """Build one immutable E6 plan.

        This pure builder validates semantic preservation but cannot by itself
        prove accepted-history membership.  Use ``generate_e6_spec_from_store``
        for an authoritative-ready plan; the history store repeats the proof at
        acceptance time.
        """
        if stop_evaluation.continuation_decision != "E6_REQUIRED":
            raise ValidationError(
                "E6_ONLY_FROM_E6_REQUIRED",
                f"Cannot generate E6 from STOP decision '{stop_evaluation.continuation_decision}'; requires E6_REQUIRED",
            )
        if stop_evaluation.assurance_level != "BOUNDED":
            raise ValidationError("E6_REQUIRES_BOUNDED_ASSURANCE")
        if stop_evaluation.release_readiness in {"READY", "READY_WITH_RESIDUAL_RISK"}:
            raise ValidationError("E6_READY_AXIS_CONFLICT")
        if stop_evaluation.stop_input_ref.get("revision_digest") != stop_input.ref.get("revision_digest"):
            raise ValidationError("E6_STOP_INPUT_BINDING_MISMATCH")

        exact_stop_eval_ref = dict(source_stop_evaluation_ref or stop_evaluation.ref)
        exact_stop_input_ref = dict(source_stop_input_ref or stop_input.ref)
        if exact_stop_eval_ref.get("revision_digest") != stop_evaluation.ref.get("revision_digest"):
            raise ValidationError("E6_STOP_EVALUATION_BINDING_MISMATCH")
        if exact_stop_input_ref.get("revision_digest") != stop_input.ref.get("revision_digest"):
            raise ValidationError("E6_STOP_INPUT_BINDING_MISMATCH")

        mandatory_digests = _digest_set(stop_input.mandatory_obligation_refs)
        inherited_unresolved = _canonical_refs(stop_evaluation.remaining_obligation_refs)
        inherited_digests = _digest_set(inherited_unresolved)
        if not inherited_digests.issubset(mandatory_digests):
            raise ValidationError("E6_REMAINING_OBLIGATION_BINDING_MISMATCH")
        if attempted_dropped_obligation_digests and (
            attempted_dropped_obligation_digests & inherited_digests
        ):
            raise ValidationError(
                "DENOMINATOR_MANIPULATION_FORBIDDEN",
                "E6 cannot drop unresolved mandatory obligations to manipulate the denominator",
            )

        if proposed_isolation_profile_ref is not None:
            baseline_level = isolation_profile_ref.get("isolation_level", "STRICT")
            proposed_level = proposed_isolation_profile_ref.get("isolation_level", "STRICT")
            if baseline_level == "STRICT" and proposed_level != "STRICT":
                raise ValidationError(
                    "ISOLATION_REWRITE_FORBIDDEN",
                    "E6 cannot weaken baseline isolation profile after failure observation",
                )

        stop_cut = AdaptiveE6Generator._accepted_cut(dict(stop_input.input_history_cut), "stop_input_cut")
        hcut = dict(e6_input_history_cut or stop_input.input_history_cut)
        e6_cut = AdaptiveE6Generator._accepted_cut(hcut, "e6_input_history_cut")
        if e6_cut.campaign_id != stop_cut.campaign_id:
            raise ValidationError("E6_INPUT_CUT_CAMPAIGN_MISMATCH")
        if e6_cut.accepted_head_seq < stop_cut.accepted_head_seq:
            raise ValidationError("E6_INPUT_CUT_PRECEDES_STOP_INPUT")
        if (
            e6_cut.accepted_head_seq == stop_cut.accepted_head_seq
            and e6_cut.accepted_head_hash != stop_cut.accepted_head_hash
        ):
            raise ValidationError("E6_INPUT_CUT_CONFLICT")

        prior_added_surfaces: Sequence[Mapping[str, Any]] = ()
        prior_added_invariants: Sequence[Mapping[str, Any]] = ()
        prior_added_obligations: Sequence[Mapping[str, Any]] = ()
        if baseline_stage_spec is not None and baseline_stage_spec.stage_key == "E6":
            prior_relation = _parse_relationship(baseline_stage_spec.stop_e6_relationship)
            if not _same_digest(prior_relation.get("source_generation_ref"), stop_input.source_generation_ref):
                raise ValidationError("E6_SOURCE_GENERATION_MISMATCH")
            if prior_relation.get("governing_policy_pin") != hcut.get("governing_policy_ref"):
                raise ValidationError("E6_GOVERNING_POLICY_MISMATCH")
            if prior_relation.get("governing_spec_pins") != list(hcut.get("governing_spec_refs", ())):
                raise ValidationError("E6_GOVERNING_SPEC_MISMATCH")
            if prior_relation.get("trust_profile_ref") != trust_profile_ref:
                raise ValidationError("E6_TRUST_PROFILE_WEAKENING_FORBIDDEN")
            if prior_relation.get("isolation_profile_ref") != isolation_profile_ref:
                raise ValidationError("E6_ISOLATION_REWRITE_FORBIDDEN")
            prior_added_surfaces = prior_relation.get("added_surfaces", ())
            prior_added_invariants = prior_relation.get("added_invariants", ())
            prior_added_obligations = prior_relation.get("added_obligations", ())

        added_surfaces_c = _merge_canonical_refs(prior_added_surfaces, added_surfaces)
        added_invariants_c = _merge_canonical_refs(prior_added_invariants, added_invariants)
        added_obligations_c = _merge_canonical_refs(prior_added_obligations, added_obligations)
        unresolved_contradictions = _canonical_refs(stop_input.contradiction_refs)

        baseline_ref = dict(baseline_stage_spec.ref) if baseline_stage_spec is not None else None
        payload = {
            "relationship_type": _RELATIONSHIP_TYPE,
            "source_stop_evaluation_ref": exact_stop_eval_ref,
            "source_stop_input_ref": exact_stop_input_ref,
            "baseline_stage_spec_ref": baseline_ref,
            "e6_input_history_cut": hcut,
            "source_generation_ref": dict(stop_input.source_generation_ref),
            "governing_policy_ref": dict(stop_input.governing_policy_ref),
            "governing_policy_pin": hcut.get("governing_policy_ref"),
            "governing_spec_pins": list(hcut.get("governing_spec_refs", ())),
            "trust_profile_ref": dict(trust_profile_ref),
            "isolation_profile_ref": dict(isolation_profile_ref),
            "inherited_unresolved_obligations": list(inherited_unresolved),
            "unknown_blocked_summary": dict(stop_input.unknown_blocked_summary),
            "unresolved_contradictions": list(unresolved_contradictions),
            "added_surfaces": list(added_surfaces_c),
            "added_invariants": list(added_invariants_c),
            "added_obligations": list(added_obligations_c),
            "source_stop_reason_codes": list(stop_evaluation.reason_codes),
        }

        if baseline_stage_spec is not None:
            blind_reveal_phase_model = baseline_stage_spec.blind_reveal_phase_model
            allowed_corpus_roles = baseline_stage_spec.allowed_corpus_roles
            forbidden_corpus_roles = baseline_stage_spec.forbidden_corpus_roles
            coverage_policy_ref = baseline_stage_spec.coverage_obligation_policy_ref
            transition_policy_ref = baseline_stage_spec.transition_policy_ref
            required_outputs = tuple(
                dict.fromkeys((*baseline_stage_spec.required_stage_completion_outputs, _POST_E6_OUTPUT))
            )
        else:
            blind_reveal_phase_model = "CONTROLLED"
            allowed_corpus_roles = ()
            forbidden_corpus_roles = ()
            coverage_policy_ref = str(hcut.get("governing_policy_ref") or "")
            governing_specs = tuple(str(value) for value in hcut.get("governing_spec_refs", ()))
            if not governing_specs:
                raise ValidationError("E6_GOVERNING_SPEC_REQUIRED")
            transition_policy_ref = governing_specs[0]
            required_outputs = (_POST_E6_OUTPUT,)

        stage_spec = StageSpec(
            stage_key="E6",
            stage_spec_revision=spec_id,
            stage_role="E6",
            stage_ordinal=6,
            purpose="Adaptive bounded assurance work after accepted STOP E6_REQUIRED",
            predecessor_requirements=("E5",),
            required_lane_slots=("E6_ADAPTIVE",),
            optional_lane_slots=(),
            blind_reveal_phase_model=blind_reveal_phase_model,
            allowed_corpus_roles=tuple(allowed_corpus_roles),
            forbidden_corpus_roles=tuple(forbidden_corpus_roles),
            coverage_obligation_policy_ref=coverage_policy_ref,
            required_stage_completion_outputs=required_outputs,
            transition_policy_ref=transition_policy_ref,
            stop_e6_relationship=_canonical_relationship(payload),
        )

        return AdaptiveE6Spec(
            stage_spec=stage_spec,
            source_stop_evaluation_ref=exact_stop_eval_ref,
            source_generation_ref=dict(stop_input.source_generation_ref),
            governing_policy_ref=dict(stop_input.governing_policy_ref),
            trust_profile_ref=dict(trust_profile_ref),
            isolation_profile_ref=dict(isolation_profile_ref),
            inherited_unresolved_obligations=inherited_unresolved,
            added_surfaces=added_surfaces_c,
            added_invariants=added_invariants_c,
            added_obligations=added_obligations_c,
            unresolved_contradictions=unresolved_contradictions,
            e6_input_history_cut=hcut,
        )

    @staticmethod
    def generate_e6_spec_from_store(
        store,
        *,
        spec_id: str,
        stop_evaluation_ref: Mapping[str, Any],
        trust_profile_ref: dict[str, Any],
        isolation_profile_ref: dict[str, Any],
        proposed_isolation_profile_ref: dict[str, Any] | None = None,
        added_surfaces: Sequence[dict[str, Any]] = (),
        added_invariants: Sequence[dict[str, Any]] = (),
        added_obligations: Sequence[dict[str, Any]] = (),
        attempted_dropped_obligation_digests: Set[str] | None = None,
    ) -> AdaptiveE6Spec:
        """Build E6 from the latest exact accepted STOP result at current head."""
        from ..workflow.read_models import current_accepted_cut

        cut = current_accepted_cut(store)
        stop_rows = store.accepted_records("stop_evaluation", cut)
        if not stop_rows:
            raise ValidationError("E6_ACCEPTED_STOP_REQUIRED")
        latest_stop = max(stop_rows, key=lambda row: int(row.get("accepted_seq", 0)))
        requested_digest = stop_evaluation_ref.get("revision_digest")
        if requested_digest != latest_stop["ref"].get("revision_digest"):
            raise ValidationError("E6_STOP_EVALUATION_STALE")

        stop_evaluation = StopEvaluation(**latest_stop["body"])
        declared_stop_input_ref = latest_stop["body"].get("stop_input_ref")
        if not isinstance(declared_stop_input_ref, dict):
            raise ValidationError("E6_STOP_INPUT_BINDING_MISMATCH")
        stop_input_rows = [
            row
            for row in store.accepted_records("stop_input", cut)
            if row["ref"].get("revision_digest") == declared_stop_input_ref.get("revision_digest")
        ]
        if len(stop_input_rows) != 1:
            raise ValidationError("E6_STOP_INPUT_BINDING_MISMATCH")
        stop_input_row = stop_input_rows[0]
        stop_input = StopInput(**stop_input_row["body"])

        all_stage_rows = store.accepted_records("stage_spec", cut)
        e6_rows = [row for row in all_stage_rows if row["body"].get("stage_key") == "E6"]
        e5_rows = [row for row in all_stage_rows if row["body"].get("stage_key") == "E5"]
        if e6_rows:
            baseline_row = max(e6_rows, key=lambda row: int(row.get("accepted_seq", 0)))
        elif e5_rows:
            baseline_row = max(e5_rows, key=lambda row: int(row.get("accepted_seq", 0)))
        else:
            raise ValidationError("E6_BASELINE_STAGE_SPEC_REQUIRED")
        if stop_input.evaluation_context == "POST_E6" and baseline_row["body"].get("stage_key") != "E6":
            raise ValidationError("E6_PRIOR_ROUND_BASELINE_REQUIRED")
        baseline_stage_spec = StageSpec(**baseline_row["body"])

        if trust_profile_ref.get("kind") != "trust_profile":
            raise ValidationError("E6_TRUST_PROFILE_REQUIRED")
        store.resolve_accepted(dict(trust_profile_ref), cut)

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
            baseline_stage_spec=baseline_stage_spec,
            source_stop_evaluation_ref=latest_stop["ref"],
            source_stop_input_ref=stop_input_row["ref"],
        )

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


def validate_adaptive_e6_stage_spec_authority(
    stage_obj: CanonicalObject,
    *,
    current: AcceptedHead | None,
    con,
) -> None:
    """Prove an E6 StageSpec is derived from current prior accepted STOP authority."""
    if stage_obj.kind != "stage_spec" or stage_obj.body.get("stage_key") != "E6":
        return
    if current is None:
        raise ValidationError("E6_ACCEPTED_STOP_REQUIRED")

    from .authority import _accepted_index, _latest, _records, _resolve

    body = stage_obj.body
    payload = _parse_relationship(body.get("stop_e6_relationship"))

    commit_row = con.execute(
        "SELECT body FROM commits WHERE commit_hash=?", (current.commit_hash,)
    ).fetchone()
    if commit_row is None:
        raise ValidationError("ACCEPTED_HEAD_COMMIT_MISSING")
    prior_commit = json.loads(commit_row[0])
    expected_cut = HistoryCut.accepted(
        current,
        prior_commit["governing_policy_ref"],
        prior_commit["governing_spec_refs"],
    ).as_dict()
    if payload.get("e6_input_history_cut") != expected_cut:
        raise ValidationError("E6_INPUT_CUT_MISMATCH")

    index = _accepted_index(current, con)
    stop_eval_ref = payload.get("source_stop_evaluation_ref")
    if not isinstance(stop_eval_ref, dict):
        raise ValidationError("E6_ACCEPTED_STOP_REQUIRED")
    stop_eval_row = _resolve(stop_eval_ref, index, con)
    latest_stop = _latest(_records("stop_evaluation", index, con))
    if latest_stop is None or latest_stop["ref"].get("revision_digest") != stop_eval_ref.get("revision_digest"):
        raise ValidationError("E6_STOP_EVALUATION_STALE")

    stop_eval_body = stop_eval_row["body"]
    if stop_eval_body.get("continuation_decision") != "E6_REQUIRED":
        raise ValidationError("E6_ONLY_FROM_E6_REQUIRED")
    if stop_eval_body.get("assurance_level") != "BOUNDED":
        raise ValidationError("E6_REQUIRES_BOUNDED_ASSURANCE")
    if stop_eval_body.get("release_readiness") in {"READY", "READY_WITH_RESIDUAL_RISK"}:
        raise ValidationError("E6_READY_AXIS_CONFLICT")

    stop_input_ref = payload.get("source_stop_input_ref")
    if not isinstance(stop_input_ref, dict):
        raise ValidationError("E6_STOP_INPUT_BINDING_MISMATCH")
    accepted_stop_input_ref = stop_eval_body.get("stop_input_ref")
    if not _same_digest(stop_input_ref, accepted_stop_input_ref):
        raise ValidationError("E6_STOP_INPUT_BINDING_MISMATCH")
    stop_input_row = _resolve(stop_input_ref, index, con)
    stop_input_body = stop_input_row["body"]
    if stop_input_body.get("evaluation_context") not in {"FINAL_POST_E5", "POST_E6"}:
        raise ValidationError("E6_FINAL_STOP_CONTEXT_REQUIRED")

    stage_rows = _records("stage_spec", index, con)
    prior_e6_rows = [row for row in stage_rows if row["body"].get("stage_key") == "E6"]
    e5_rows = [row for row in stage_rows if row["body"].get("stage_key") == "E5"]
    if prior_e6_rows:
        baseline_row = max(prior_e6_rows, key=lambda row: int(row["accepted_seq"]))
    elif e5_rows:
        baseline_row = max(e5_rows, key=lambda row: int(row["accepted_seq"]))
    else:
        raise ValidationError("E6_BASELINE_STAGE_SPEC_REQUIRED")
    if stop_input_body.get("evaluation_context") == "POST_E6" and baseline_row["body"].get("stage_key") != "E6":
        raise ValidationError("E6_PRIOR_ROUND_BASELINE_REQUIRED")

    baseline_ref = payload.get("baseline_stage_spec_ref")
    if not isinstance(baseline_ref, dict) or not _same_digest(baseline_ref, baseline_row["ref"]):
        raise ValidationError("E6_BASELINE_STAGE_SPEC_MISMATCH")
    _resolve(baseline_ref, index, con)
    baseline_body = baseline_row["body"]

    if payload.get("source_generation_ref") != stop_input_body.get("source_generation_ref"):
        raise ValidationError("E6_SOURCE_GENERATION_MISMATCH")
    if payload.get("governing_policy_ref") != stop_input_body.get("governing_policy_ref"):
        raise ValidationError("E6_GOVERNING_POLICY_MISMATCH")
    if payload.get("governing_policy_pin") != expected_cut.get("governing_policy_ref"):
        raise ValidationError("E6_GOVERNING_POLICY_MISMATCH")
    if payload.get("governing_spec_pins") != expected_cut.get("governing_spec_refs"):
        raise ValidationError("E6_GOVERNING_SPEC_MISMATCH")

    inherited = payload.get("inherited_unresolved_obligations")
    if not isinstance(inherited, list):
        raise ValidationError("E6_REMAINING_OBLIGATION_BINDING_MISMATCH")
    expected_remaining = stop_eval_body.get("remaining_obligation_refs", [])
    if canonical_bytes(canonical_reference_set(inherited)) != canonical_bytes(
        canonical_reference_set(expected_remaining)
    ):
        raise ValidationError("E6_REMAINING_OBLIGATION_BINDING_MISMATCH")
    mandatory_digests = _digest_set(stop_input_body.get("mandatory_obligation_refs", ()))
    if not _digest_set(inherited).issubset(mandatory_digests):
        raise ValidationError("E6_REMAINING_OBLIGATION_BINDING_MISMATCH")

    contradictions = payload.get("unresolved_contradictions")
    if not isinstance(contradictions, list) or canonical_bytes(canonical_reference_set(contradictions)) != canonical_bytes(
        canonical_reference_set(stop_input_body.get("contradiction_refs", ()))
    ):
        raise ValidationError("E6_CONTRADICTION_LAUNDERING_FORBIDDEN")
    if payload.get("unknown_blocked_summary") != stop_input_body.get("unknown_blocked_summary"):
        raise ValidationError("E6_UNKNOWN_BLOCKED_STATE_MISMATCH")
    if payload.get("source_stop_reason_codes") != stop_eval_body.get("reason_codes"):
        raise ValidationError("E6_STOP_REASON_SET_MISMATCH")

    trust_ref = payload.get("trust_profile_ref")
    if not isinstance(trust_ref, dict) or trust_ref.get("kind") != "trust_profile":
        raise ValidationError("E6_TRUST_PROFILE_REQUIRED")
    _resolve(trust_ref, index, con)
    if not isinstance(payload.get("isolation_profile_ref"), dict):
        raise ValidationError("E6_ISOLATION_PROFILE_REQUIRED")

    for field_name in ("added_surfaces", "added_invariants", "added_obligations"):
        values = payload.get(field_name)
        if not isinstance(values, list):
            raise ValidationError("E6_ADDED_SCOPE_INVALID", field_name)
        if canonical_bytes(values) != canonical_bytes(canonical_reference_set(values)):
            raise ValidationError("E6_ADDED_SCOPE_NONCANONICAL", field_name)

    if baseline_body.get("stage_key") == "E6":
        prior_relation = _parse_relationship(baseline_body.get("stop_e6_relationship"))
        if prior_relation.get("trust_profile_ref") != trust_ref:
            raise ValidationError("E6_TRUST_PROFILE_WEAKENING_FORBIDDEN")
        if prior_relation.get("isolation_profile_ref") != payload.get("isolation_profile_ref"):
            raise ValidationError("E6_ISOLATION_REWRITE_FORBIDDEN")
        if not _same_digest(prior_relation.get("source_generation_ref"), payload.get("source_generation_ref")):
            raise ValidationError("E6_SOURCE_GENERATION_MISMATCH")
        for field_name in ("added_surfaces", "added_invariants", "added_obligations"):
            prior_digests = _digest_set(prior_relation.get(field_name, ()))
            current_digests = _digest_set(payload.get(field_name, ()))
            if not prior_digests.issubset(current_digests):
                raise ValidationError("E6_PRIOR_STRENGTHENING_DROPPED", field_name)

    expected_outputs = tuple(
        dict.fromkeys((*baseline_body.get("required_stage_completion_outputs", ()), _POST_E6_OUTPUT))
    )
    if body.get("stage_role") != "E6" or body.get("stage_ordinal") != 6:
        raise ValidationError("E6_STAGE_SPEC_IDENTITY_INVALID")
    if body.get("predecessor_requirements") != ["E5"]:
        raise ValidationError("E6_PREDECESSOR_REQUIREMENT_INVALID")
    if body.get("required_lane_slots") != ["E6_ADAPTIVE"] or body.get("optional_lane_slots") != []:
        raise ValidationError("E6_LANE_PLAN_INVALID")
    if body.get("blind_reveal_phase_model") != baseline_body.get("blind_reveal_phase_model"):
        raise ValidationError("E6_BLIND_REVEAL_WEAKENING_FORBIDDEN")
    if body.get("allowed_corpus_roles") != baseline_body.get("allowed_corpus_roles"):
        raise ValidationError("E6_CORPUS_POLICY_MISMATCH")
    if body.get("forbidden_corpus_roles") != baseline_body.get("forbidden_corpus_roles"):
        raise ValidationError("E6_CORPUS_POLICY_MISMATCH")
    if body.get("coverage_obligation_policy_ref") != baseline_body.get("coverage_obligation_policy_ref"):
        raise ValidationError("E6_COVERAGE_POLICY_MISMATCH")
    if body.get("transition_policy_ref") != baseline_body.get("transition_policy_ref"):
        raise ValidationError("E6_TRANSITION_POLICY_MISMATCH")
    if tuple(body.get("required_stage_completion_outputs", ())) != expected_outputs:
        raise ValidationError("E6_RETURN_TO_STOP_OBLIGATION_MISSING")


__all__ = [
    "AdaptiveE6Generator",
    "AdaptiveE6Spec",
    "validate_adaptive_e6_stage_spec_authority",
]
