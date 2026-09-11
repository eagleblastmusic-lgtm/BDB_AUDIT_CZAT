"""Production Hypothesis Orchestration Engine (F4 Domain Expansion / M18 / §§39–40).

Enforces immutable hypothesis revision flow:
- Rejected hypotheses are preserved in accepted history.
- Zero silent deletes or retroactive rewrites.
- Exact gap, discovery, and evidence provenance binding.
- Exact predecessor/successor binding across revisions.
- Gate authority strictly binds exact accepted revision digests, forbidding
  latest-by-logical-id shortcuts.
"""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id, validate_id, deterministic_id
from ..history.objects import CanonicalObject, ObjectRef
from .models import (
    HypothesisRevision,
    HYPOTHESIS_STATUSES,
    PLANNING_MODES,
    _ref_dict,
)
from .engine import LEGAL_TRANSITIONS, transition_hypothesis


class HypothesisOrchestrator:
    """Manages immutable Hypothesis revision chains across accepted history cuts."""

    def __init__(self):
        # keyed by digest -> HypothesisRevision
        self._revisions_by_digest: dict[str, HypothesisRevision] = {}
        # keyed by logical_id -> list of HypothesisRevision in ascending revision order
        self._chains_by_id: dict[str, list[HypothesisRevision]] = {}

    def propose_hypothesis(
        self,
        statement: str,
        scope_refs: Sequence[Any],
        invariant_refs: Sequence[Any],
        obligation_refs: Sequence[Any],
        source_generation_ref: Any,
        history_cut: dict,
        hypothesis_id: str | None = None,
        origin_discovery_ref: Any = None,
        planning_mode: str = "PREREGISTERED",
    ) -> HypothesisRevision:
        """Propose a new hypothesis (revision 1)."""
        h_id = hypothesis_id or new_id("hypothesis_revision")
        hyp = HypothesisRevision(
            hypothesis_id=h_id,
            hypothesis_revision="1",
            source_generation_ref=source_generation_ref,
            statement=statement,
            scope_refs=list(scope_refs),
            invariant_refs=list(invariant_refs),
            obligation_refs=list(obligation_refs),
            origin_discovery_ref=origin_discovery_ref,
            planning_mode=planning_mode,
            status="PROPOSED",
            input_history_cut=history_cut,
        )
        self.record_revision(hyp)
        return hyp

    def record_revision(self, revision: HypothesisRevision) -> None:
        """Record an accepted hypothesis revision into history."""
        d = revision.digest
        if d in self._revisions_by_digest:
            # Idempotent re-recording
            return

        h_id = revision.hypothesis_id or "default"
        chain = self._chains_by_id.get(h_id, [])

        new_rev_int = int(revision.hypothesis_revision)
        for existing in chain:
            existing_rev_int = int(existing.invariant_revision if hasattr(existing, "invariant_revision") else existing.hypothesis_revision)
            if existing_rev_int == new_rev_int:
                raise ValidationError("RETROACTIVE_REWRITE_FORBIDDEN", f"Revision {new_rev_int} of {h_id} already exists with different content")
            if existing_rev_int > new_rev_int:
                raise ValidationError("NON_MONOTONIC_HYPOTHESIS_REVISION", f"Cannot accept revision {new_rev_int} after {existing_rev_int}")

        self._revisions_by_digest[d] = revision
        self._chains_by_id.setdefault(h_id, []).append(revision)

    def transition(
        self,
        hypothesis: HypothesisRevision,
        new_status: str,
        new_statement: str | None = None,
        origin_discovery_ref: Any = None,
        history_cut: dict | None = None,
    ) -> HypothesisRevision:
        """Transition an existing hypothesis to a successor revision."""
        # Ensure the predecessor is already in history
        if hypothesis.digest not in self._revisions_by_digest:
            self.record_revision(hypothesis)

        next_hyp = transition_hypothesis(
            hypothesis=hypothesis,
            new_status=new_status,
            new_statement=new_statement,
            origin_discovery_ref=origin_discovery_ref,
        )

        if history_cut is not None:
            # Bind to new history cut
            next_hyp = HypothesisRevision(
                hypothesis_id=next_hyp.hypothesis_id,
                hypothesis_revision=next_hyp.hypothesis_revision,
                source_generation_ref=next_hyp.source_generation_ref,
                statement=next_hyp.statement,
                scope_refs=next_hyp.scope_refs,
                invariant_refs=next_hyp.invariant_refs,
                obligation_refs=next_hyp.obligation_refs,
                origin_discovery_ref=next_hyp.origin_discovery_ref,
                planning_mode=next_hyp.planning_mode,
                status=next_hyp.status,
                input_history_cut=history_cut,
            )

        self.record_revision(next_hyp)
        return next_hyp

    def delete_hypothesis(self, hypothesis_id: str) -> None:
        """Silent or explicit deletion is strictly forbidden in accepted history."""
        raise ValidationError("DELETION_FORBIDDEN", "Hypotheses cannot be deleted from canonical history")

    def get_history_chain(self, hypothesis_id: str) -> list[HypothesisRevision]:
        """Return the immutable revision chain for an ID, including any rejected revisions."""
        return list(self._chains_by_id.get(hypothesis_id, []))

    def evaluate_gate_authority(
        self,
        exact_revision_ref: Any,
        expected_status: str = "CONFIRMED",
    ) -> dict:
        """Evaluate gate authority strictly binding exact revision digest (no latest-by-id shortcut)."""
        ref_d = (
            exact_revision_ref.get("revision_digest")
            if isinstance(exact_revision_ref, dict)
            else (exact_revision_ref.revision_digest if hasattr(exact_revision_ref, "revision_digest") else str(exact_revision_ref))
        )

        rev = self._revisions_by_digest.get(ref_d)
        if rev is None:
            raise ValidationError("UNKNOWN_HYPOTHESIS_REVISION_REF", f"Revision {ref_d} not found in accepted history")

        is_satisfied = (rev.status == expected_status)
        return {
            "gate": "HYPOTHESIS_RESOLUTION_GATE",
            "bound_revision_digest": ref_d,
            "hypothesis_id": rev.hypothesis_id,
            "hypothesis_revision": rev.hypothesis_revision,
            "status": rev.status,
            "is_satisfied": is_satisfied,
        }
