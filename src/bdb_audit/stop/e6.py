"""Adaptive E6 Generator (WP-E5-11 / M45 / §104 / Data Contracts §78).

Generates adaptive E6 StageSpec exclusively from an accepted StopEvaluation with E6_REQUIRED.

Normative requirements:
- Strictly inherits governing source, policy, unresolved obligations, and materiality.
- CANNOT reduce or drop requirements that caused FAIL/BLOCKED (no denominator manipulation).
- CANNOT weaken or rewrite isolation after seeing failure results.
- CANNOT launder unresolved contradictions.
- CAN add new surfaces, invariants, and obligations (preserves or strengthens).
- After E6 execution, execution must return to global STOP on the new accepted head.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .models import StopInput, StopEvaluation


@dataclass(frozen=True)
class AdaptiveE6Spec:
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

    def body(self) -> dict[str, Any]:
        return {
            "e6_stage_spec_id": self.e6_stage_spec_id,
            "source_stop_evaluation_ref": dict(self.source_stop_evaluation_ref),
            "source_generation_ref": dict(self.source_generation_ref),
            "governing_policy_ref": dict(self.governing_policy_ref),
            "trust_profile_ref": dict(self.trust_profile_ref),
            "isolation_profile_ref": dict(self.isolation_profile_ref),
            "inherited_unresolved_obligations": [dict(r) for r in self.inherited_unresolved_obligations],
            "added_surfaces": [dict(r) for r in self.added_surfaces],
            "added_invariants": [dict(r) for r in self.added_invariants],
            "added_obligations": [dict(r) for r in self.added_obligations],
            "unresolved_contradictions": [dict(r) for r in self.unresolved_contradictions],
            "e6_input_history_cut": dict(self.e6_input_history_cut),
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()

    @property
    def ref(self) -> dict[str, Any]:
        return {
            "kind": "stage_spec",
            "revision_digest": self.digest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stage_spec/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


class AdaptiveE6Generator:
    """Generates Adaptive E6 StageSpec from a StopEvaluation."""

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
        # Invariant 1: E6 can ONLY be generated from explicit continuation_decision == "E6_REQUIRED"
        if stop_evaluation.continuation_decision != "E6_REQUIRED":
            raise ValidationError(
                "E6_ONLY_FROM_E6_REQUIRED",
                f"Cannot generate E6 from STOP decision '{stop_evaluation.continuation_decision}'; requires E6_REQUIRED",
            )

        # Invariant 2: Denominator manipulation forbidden: cannot drop unresolved obligations
        mandatory_digests = {
            r.get("revision_digest") for r in stop_input.mandatory_obligation_refs if r.get("revision_digest")
        }
        if attempted_dropped_obligation_digests and (attempted_dropped_obligation_digests & mandatory_digests):
            raise ValidationError(
                "DENOMINATOR_MANIPULATION_FORBIDDEN",
                "E6 cannot drop mandatory unresolved obligations to manipulate the denominator",
            )

        # Invariant 3: Isolation rewrite forbidden: cannot weaken isolation
        if proposed_isolation_profile_ref is not None:
            baseline_level = isolation_profile_ref.get("isolation_level", "STRICT")
            proposed_level = proposed_isolation_profile_ref.get("isolation_level", "STRICT")
            if baseline_level == "STRICT" and proposed_level != "STRICT":
                raise ValidationError(
                    "ISOLATION_REWRITE_FORBIDDEN",
                    "E6 cannot weaken baseline isolation profile after failure observation",
                )

        # Invariant 4: Contradiction laundering forbidden: unresolved contradictions must be carried forward
        unresolved_contradictions = tuple(stop_input.contradiction_refs)

        hcut = e6_input_history_cut or stop_input.input_history_cut

        return AdaptiveE6Spec(
            e6_stage_spec_id=spec_id,
            source_stop_evaluation_ref=dict(stop_evaluation.ref),
            source_generation_ref=dict(stop_input.source_generation_ref),
            governing_policy_ref=dict(stop_input.governing_policy_ref),
            trust_profile_ref=dict(trust_profile_ref),
            isolation_profile_ref=dict(isolation_profile_ref),
            inherited_unresolved_obligations=tuple(stop_input.mandatory_obligation_refs),
            added_surfaces=tuple(added_surfaces),
            added_invariants=tuple(added_invariants),
            added_obligations=tuple(added_obligations),
            unresolved_contradictions=unresolved_contradictions,
            e6_input_history_cut=dict(hcut),
        )

    @staticmethod
    def verify_post_e6_return_to_stop(new_head_cut: dict[str, Any], previous_cut: dict[str, Any]) -> None:
        """Verify that after E6 completion, control flow returns to global STOP on the new accepted head."""
        new_seq = new_head_cut.get("commit_seq", 0)
        prev_seq = previous_cut.get("commit_seq", 0)
        if new_seq <= prev_seq:
            raise ValidationError(
                "POST_E6_MUST_ADVANCE_HEAD",
                f"Post-E6 evaluation requires advanced head cut (new {new_seq} <= prev {prev_seq})",
            )
