"""Non-authoritative compatibility adapters for pre-M45 E6 planner callers.

These adapters exist only so older pure-planner tests/callers can construct an
E6 proposal while migrating to the canonical StageSpec API.  They do not grant
accepted authority: the history-store E6 validator still requires an exact
current ACCEPTED_HISTORY_CUT and a prior accepted StopEvaluation/StopInput.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..orchestration.stages import StageSpec


_COMPAT_POLICY = "compat:legacy-e6-planner-policy"
_COMPAT_SPEC = "compat:legacy-e6-planner-spec"


def _is_legacy_cut(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and "variant" not in value
        and {"campaign_id", "commit_seq", "commit_hash"}.issubset(value)
    )


def _canonicalize_legacy_cut(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": value["campaign_id"],
        "accepted_head_seq": value["commit_seq"],
        "accepted_head_hash": value["commit_hash"],
        "governing_policy_ref": _COMPAT_POLICY,
        "governing_spec_refs": [_COMPAT_SPEC],
    }


def install_adaptive_e6_planner_compat(spec_cls, generator_cls) -> None:
    """Install a narrow runtime adapter without weakening store acceptance."""
    if getattr(spec_cls, "_bdb_legacy_planner_compat", False):
        return

    original_init = spec_cls.__init__

    def compat_init(self, *args, **kwargs):
        if "e6_stage_spec_id" not in kwargs:
            return original_init(self, *args, **kwargs)
        if args:
            raise TypeError("legacy AdaptiveE6Spec compatibility accepts keyword arguments only")

        spec_id = kwargs.pop("e6_stage_spec_id")
        source_stop_evaluation_ref = dict(kwargs.pop("source_stop_evaluation_ref"))
        source_generation_ref = dict(kwargs.pop("source_generation_ref"))
        governing_policy_ref = dict(kwargs.pop("governing_policy_ref"))
        trust_profile_ref = dict(kwargs.pop("trust_profile_ref"))
        isolation_profile_ref = dict(kwargs.pop("isolation_profile_ref"))
        inherited = tuple(dict(v) for v in kwargs.pop("inherited_unresolved_obligations", ()))
        e6_cut = dict(kwargs.pop("e6_input_history_cut", {}))
        if kwargs:
            unexpected = ", ".join(sorted(kwargs))
            raise TypeError(f"unexpected legacy AdaptiveE6Spec arguments: {unexpected}")

        # This is deliberately a planner-only compatibility object.  The exact
        # canonical StageSpec shape is preserved, while stop_e6_relationship is
        # NONE so direct history acceptance fails closed under M45 authority.
        stage_spec = StageSpec(
            stage_key="E6",
            stage_spec_revision=str(spec_id),
            stage_role="E6",
            stage_ordinal=6,
            purpose="Legacy non-authoritative Adaptive E6 planner compatibility",
            predecessor_requirements=("E5",),
            required_lane_slots=("E6_ADAPTIVE",),
            optional_lane_slots=(),
            blind_reveal_phase_model="CONTROLLED",
            allowed_corpus_roles=(),
            forbidden_corpus_roles=(),
            coverage_obligation_policy_ref="",
            required_stage_completion_outputs=("POST_E6_STOP_REEVALUATION",),
            transition_policy_ref="TRANSITION_PROFILE_V1",
            stop_e6_relationship="NONE",
        )
        return original_init(
            self,
            stage_spec=stage_spec,
            source_stop_evaluation_ref=source_stop_evaluation_ref,
            source_generation_ref=source_generation_ref,
            governing_policy_ref=governing_policy_ref,
            trust_profile_ref=trust_profile_ref,
            isolation_profile_ref=isolation_profile_ref,
            inherited_unresolved_obligations=inherited,
            e6_input_history_cut=e6_cut,
        )

    spec_cls.__init__ = compat_init
    spec_cls._bdb_legacy_planner_compat = True

    original_generate = generator_cls.generate_e6_spec

    def compat_generate(*args, **kwargs):
        if len(args) >= 3:
            stop_evaluation = args[1]
            stop_input = args[2]
        else:
            stop_evaluation = kwargs.get("stop_evaluation")
            stop_input = kwargs.get("stop_input")

        if stop_input is None or not _is_legacy_cut(getattr(stop_input, "input_history_cut", None)):
            return original_generate(*args, **kwargs)

        compat_cut = _canonicalize_legacy_cut(dict(stop_input.input_history_cut))
        compat_input = replace(stop_input, input_history_cut=compat_cut)

        remaining = tuple(getattr(stop_evaluation, "remaining_obligation_refs", ()))
        if not remaining:
            remaining = tuple(compat_input.mandatory_obligation_refs)
        compat_evaluation = replace(
            stop_evaluation,
            stop_input_ref=compat_input.ref,
            remaining_obligation_refs=remaining,
        )

        mutable_args = list(args)
        if len(mutable_args) >= 3:
            mutable_args[1] = compat_evaluation
            mutable_args[2] = compat_input
        else:
            kwargs["stop_evaluation"] = compat_evaluation
            kwargs["stop_input"] = compat_input

        supplied_cut = kwargs.get("e6_input_history_cut")
        if supplied_cut is None or _is_legacy_cut(supplied_cut):
            kwargs["e6_input_history_cut"] = compat_cut

        return original_generate(*mutable_args, **kwargs)

    generator_cls.generate_e6_spec = staticmethod(compat_generate)
