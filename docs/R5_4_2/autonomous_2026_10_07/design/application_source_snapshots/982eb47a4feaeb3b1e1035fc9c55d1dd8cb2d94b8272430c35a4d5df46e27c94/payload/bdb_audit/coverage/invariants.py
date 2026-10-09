"""Production Invariant Categories and Invariant Registry Engine (F4 Domain Expansion / M15).

Implements the full 13 normative invariant categories, immutable revision binding,
and fail-closed negative case validation (stale revisions, wrong revisions,
invalidated dependencies, incompatible applicability, and missing support).
"""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id, validate_id, deterministic_id
from ..history.objects import CanonicalObject, ObjectRef
from .models import (
    InvariantRevision,
    INVARIANT_STATUSES,
    _ref_dict,
    _ref_kind,
)

INVARIANT_CATEGORIES = {
    "AUTHORITY",
    "DURABILITY",
    "ATOMICITY",
    "CONSISTENCY",
    "COMPLETENESS",
    "PARSING",
    "RECOVERY",
    "CONCURRENCY",
    "RESOURCE_OWNERSHIP",
    "SECURITY_BOUNDARY",
    "PRIVACY",
    "SUPPLY_CHAIN",
    "RELEASE_ASSURANCE",
    "STATE_CONSISTENCY",  # for backwards compatibility with F3 reference slice
}


class InvariantRegistryEngine:
    """Manages immutable Invariant revisions with exact accepted history cut binding."""

    def __init__(self):
        # keyed by logical_id -> list of InvariantRevision sorted by int(revision)
        self._revisions_by_id: dict[str, list[InvariantRevision]] = {}
        # keyed by digest -> InvariantRevision
        self._revisions_by_digest: dict[str, InvariantRevision] = {}

    def register_revision(self, revision: InvariantRevision) -> InvariantRevision:
        """Register an immutable invariant revision."""
        inv_id = revision.invariant_id or "default"
        digest = revision.digest

        if digest in self._revisions_by_digest:
            # Idempotent duplicate: return already registered
            return self._revisions_by_digest[digest]

        existing = self._revisions_by_id.get(inv_id, [])
        new_rev_num = int(revision.invariant_revision)

        for prev in existing:
            prev_num = int(prev.invariant_revision)
            if prev_num == new_rev_num:
                # Conflicting same-revision registration
                raise ValidationError("CONFLICTING_INVARIANT_REVISION", f"Revision {new_rev_num} already exists for {inv_id}")
            if prev_num > new_rev_num:
                # Out of order / non-monotonic revision
                raise ValidationError("NON_MONOTONIC_INVARIANT_REVISION", f"Cannot register revision {new_rev_num} after {prev_num}")

        self._revisions_by_id.setdefault(inv_id, []).append(revision)
        self._revisions_by_digest[digest] = revision
        return revision

    def get_revision(self, digest: str) -> InvariantRevision | None:
        return self._revisions_by_digest.get(digest)

    def get_revisions_for_id(self, invariant_id: str) -> list[InvariantRevision]:
        return list(self._revisions_by_id.get(invariant_id, []))

    def validate_currency(
        self,
        revision: InvariantRevision,
        as_of_cut: dict | None = None,
    ) -> None:
        """Verify invariant revision is current (not stale, retired, superseded, or invalidated)."""
        if revision.status in ("SUPERSEDED", "RETIRED", "INVALIDATED"):
            raise ValidationError(
                "STALE_INVARIANT_REVISION",
                f"Invariant {revision.invariant_id} rev {revision.invariant_revision} is {revision.status}",
            )

        inv_id = revision.invariant_id or "default"
        existing = self._revisions_by_id.get(inv_id, [])
        curr_num = int(revision.invariant_revision)
        for other in existing:
            if int(other.invariant_revision) > curr_num and other.status == "ACTIVE":
                raise ValidationError(
                    "STALE_INVARIANT_REVISION",
                    f"Invariant {inv_id} rev {curr_num} is superseded by rev {other.invariant_revision}",
                )

    def validate_dependencies(
        self,
        revision: InvariantRevision,
        invalidated_refs: Sequence[Any],
    ) -> None:
        """Ensure no target scope or policy dependency has been invalidated."""
        inv_set = {
            r if isinstance(r, str) else r.get("revision_digest") or r.get("logical_id")
            for r in invalidated_refs
        }
        for scope_ref in revision.target_scope_refs:
            key = scope_ref if isinstance(scope_ref, str) else scope_ref.get("revision_digest") or scope_ref.get("logical_id")
            if key in inv_set:
                raise ValidationError(
                    "INVALIDATED_DEPENDENCY",
                    f"Target scope {key} of invariant {revision.invariant_id} is invalidated",
                )

        if revision.activation_policy_ref:
            pol_key = (
                revision.activation_policy_ref
                if isinstance(revision.activation_policy_ref, str)
                else revision.activation_policy_ref.get("revision_digest")
                or revision.activation_policy_ref.get("logical_id")
            )
            if pol_key in inv_set:
                raise ValidationError(
                    "INVALIDATED_DEPENDENCY",
                    f"Activation policy {pol_key} of invariant {revision.invariant_id} is invalidated",
                )

    def validate_applicability(
        self,
        revision: InvariantRevision,
        target_scope: Any,
        applicability_decisions: Sequence[Mapping[str, Any]],
    ) -> None:
        """Ensure invariant is applicable to target scope according to accepted decisions."""
        target_key = target_scope if isinstance(target_scope, str) else target_scope.get("revision_digest") or target_scope.get("logical_id")
        for dec in applicability_decisions:
            dec_scope = dec.get("scope")
            dec_scope_key = dec_scope if isinstance(dec_scope, str) else (dec_scope.get("revision_digest") if isinstance(dec_scope, dict) else str(dec_scope))
            if dec_scope_key == target_key:
                result = dec.get("result")
                if result == "NOT_APPLICABLE":
                    raise ValidationError(
                        "INCOMPATIBLE_APPLICABILITY",
                        f"Invariant {revision.invariant_id} is deemed NOT_APPLICABLE for scope {target_key}",
                    )
                if result in ("UNKNOWN", "CONFLICTED"):
                    raise ValidationError(
                        "INCOMPATIBLE_APPLICABILITY",
                        f"Invariant {revision.invariant_id} applicability is {result} for scope {target_key}",
                    )

    def validate_support(
        self,
        revision: InvariantRevision,
        available_scopes: Sequence[Any],
    ) -> None:
        """Verify all declared target scopes are present in the available accepted scopes."""
        avail_set = {
            s if isinstance(s, str) else s.get("revision_digest") or s.get("logical_id")
            for s in available_scopes
        }
        for target in revision.target_scope_refs:
            t_key = target if isinstance(target, str) else target.get("revision_digest") or target.get("logical_id")
            if t_key not in avail_set:
                raise ValidationError(
                    "MISSING_INVARIANT_SUPPORT",
                    f"Target scope {t_key} for invariant {revision.invariant_id} not found in available scopes",
                )
