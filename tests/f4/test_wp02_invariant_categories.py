"""Targeted tests for Work Package 2 (PR-F4-02): Invariant Categories & Negative Binding Checks."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id, deterministic_id
from bdb_audit.coverage import (
    InvariantRevision,
    InvariantRegistryEngine,
    INVARIANT_CATEGORIES,
    INVARIANT_STATUSES,
)


def make_ref(kind: str, seed: str, logical_id: str | None = None) -> dict:
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": "CONTENT_OR_PRIOR",
        **({"logical_id": logical_id} if logical_id else {}),
    }


def test_invariant_production_categories():
    """Verify all 13 normative invariant categories are accepted and invalid ones rejected."""
    expected = {
        "AUTHORITY", "DURABILITY", "ATOMICITY", "CONSISTENCY", "COMPLETENESS",
        "PARSING", "RECOVERY", "CONCURRENCY", "RESOURCE_OWNERSHIP", "SECURITY_BOUNDARY",
        "PRIVACY", "SUPPLY_CHAIN", "RELEASE_ASSURANCE",
    }
    for cat in expected:
        assert cat in INVARIANT_CATEGORIES
        inv = InvariantRevision(
            invariant_id=new_id("invariant_revision"),
            invariant_revision="1",
            source_generation_ref=make_ref("source_identity", "src_1"),
            statement=f"Must satisfy {cat}",
            category=cat,
            activation_policy_ref=make_ref("policy_revision", "pol_1"),
        )
        assert inv.category == cat

    # Invalid category rejected
    with pytest.raises(ValidationError, match="INVALID_INVARIANT_CATEGORY"):
        InvariantRevision(
            invariant_id=new_id("invariant_revision"),
            invariant_revision="1",
            source_generation_ref=make_ref("source_identity", "src_1"),
            statement="Invalid category statement",
            category="NOT_A_REAL_CATEGORY",
            activation_policy_ref=make_ref("policy_revision", "pol_1"),
        )


def test_invariant_revision_monotonicity_and_duplicate_handling():
    """Verify strict monotonic revisions and idempotent duplicate handling."""
    engine = InvariantRegistryEngine()
    inv_id = new_id("invariant_revision")
    src_ref = make_ref("source_identity", "src_1")
    pol_ref = make_ref("policy_revision", "pol_1")

    rev1 = InvariantRevision(
        invariant_id=inv_id,
        invariant_revision="1",
        source_generation_ref=src_ref,
        statement="First revision statement",
        category="DURABILITY",
        activation_policy_ref=pol_ref,
    )
    rev2 = InvariantRevision(
        invariant_id=inv_id,
        invariant_revision="2",
        source_generation_ref=src_ref,
        statement="Second revision statement",
        category="DURABILITY",
        activation_policy_ref=pol_ref,
    )

    # Register rev 1 then rev 2
    engine.register_revision(rev1)
    engine.register_revision(rev2)
    assert len(engine.get_revisions_for_id(inv_id)) == 2

    # Idempotent duplicate: registering exact rev2 again is a NOOP
    engine.register_revision(rev2)
    assert len(engine.get_revisions_for_id(inv_id)) == 2

    # Conflicting same revision with different statement: rejected
    rev2_conflict = InvariantRevision(
        invariant_id=inv_id,
        invariant_revision="2",
        source_generation_ref=src_ref,
        statement="Conflicting statement",
        category="DURABILITY",
        activation_policy_ref=pol_ref,
    )
    with pytest.raises(ValidationError, match="CONFLICTING_INVARIANT_REVISION"):
        engine.register_revision(rev2_conflict)

    # Non-monotonic out-of-order registration: rev 1 after rev 2 on new engine
    engine2 = InvariantRegistryEngine()
    engine2.register_revision(rev2)
    with pytest.raises(ValidationError, match="NON_MONOTONIC_INVARIANT_REVISION"):
        engine2.register_revision(rev1)


def test_negative_stale_invariant_revision():
    """Negative check: Stale invariant revision fails currency check."""
    engine = InvariantRegistryEngine()
    inv_id = new_id("invariant_revision")
    src_ref = make_ref("source_identity", "src_1")
    pol_ref = make_ref("policy_revision", "pol_1")

    rev1 = InvariantRevision(
        invariant_id=inv_id,
        invariant_revision="1",
        source_generation_ref=src_ref,
        statement="Initial statement",
        category="ATOMICITY",
        activation_policy_ref=pol_ref,
        status="ACTIVE",
    )
    rev2 = InvariantRevision(
        invariant_id=inv_id,
        invariant_revision="2",
        source_generation_ref=src_ref,
        statement="Updated statement",
        category="ATOMICITY",
        activation_policy_ref=pol_ref,
        status="ACTIVE",
    )

    engine.register_revision(rev1)
    # rev1 is current when it's the only one
    engine.validate_currency(rev1)

    # After rev2 is registered, rev1 is superseded and fails currency check
    engine.register_revision(rev2)
    with pytest.raises(ValidationError, match="STALE_INVARIANT_REVISION"):
        engine.validate_currency(rev1)

    # If an invariant status is RETIRED or INVALIDATED, it also fails currency
    rev3_retired = InvariantRevision(
        invariant_id=new_id("invariant_revision"),
        invariant_revision="1",
        source_generation_ref=src_ref,
        statement="Retired invariant",
        category="ATOMICITY",
        activation_policy_ref=pol_ref,
        status="RETIRED",
    )
    with pytest.raises(ValidationError, match="STALE_INVARIANT_REVISION"):
        engine.validate_currency(rev3_retired)


def test_negative_invalidated_dependency():
    """Negative check: Invariant depending on an invalidated scope or policy fails dependency validation."""
    engine = InvariantRegistryEngine()
    src_ref = make_ref("source_identity", "src_1")
    scope_good = make_ref("surface_record", "surf_good", logical_id="scope_good")
    scope_bad = make_ref("surface_record", "surf_bad", logical_id="scope_bad")
    pol_ref = make_ref("policy_revision", "pol_1", logical_id="pol_1")

    inv = InvariantRevision(
        invariant_id=new_id("invariant_revision"),
        invariant_revision="1",
        source_generation_ref=src_ref,
        statement="Scope dependency test",
        category="SECURITY_BOUNDARY",
        activation_policy_ref=pol_ref,
        target_scope_refs=[scope_good, scope_bad],
    )

    # If scope_bad is in the invalidation set, validate_dependencies fails closed
    with pytest.raises(ValidationError, match="INVALIDATED_DEPENDENCY"):
        engine.validate_dependencies(inv, [scope_bad])

    # If policy is invalidated, it also fails
    with pytest.raises(ValidationError, match="INVALIDATED_DEPENDENCY"):
        engine.validate_dependencies(inv, [pol_ref])

    # With only unrelated invalidations, it passes
    engine.validate_dependencies(inv, [make_ref("surface_record", "other")])


def test_negative_incompatible_applicability():
    """Negative check: Invariant with incompatible applicability decision is rejected."""
    engine = InvariantRegistryEngine()
    src_ref = make_ref("source_identity", "src_1")
    target_scope = make_ref("surface_record", "scope_app", logical_id="scope_app")
    pol_ref = make_ref("policy_revision", "pol_1")

    inv = InvariantRevision(
        invariant_id=new_id("invariant_revision"),
        invariant_revision="1",
        source_generation_ref=src_ref,
        statement="Applicability test",
        category="CONCURRENCY",
        activation_policy_ref=pol_ref,
        target_scope_refs=[target_scope],
    )

    # Decision says NOT_APPLICABLE
    dec_na = {
        "scope": target_scope,
        "result": "NOT_APPLICABLE",
    }
    with pytest.raises(ValidationError, match="INCOMPATIBLE_APPLICABILITY"):
        engine.validate_applicability(inv, target_scope, [dec_na])

    # Decision says CONFLICTED
    dec_conflicted = {
        "scope": target_scope,
        "result": "CONFLICTED",
    }
    with pytest.raises(ValidationError, match="INCOMPATIBLE_APPLICABILITY"):
        engine.validate_applicability(inv, target_scope, [dec_conflicted])

    # Decision says APPLICABLE -> passes
    dec_ok = {
        "scope": target_scope,
        "result": "APPLICABLE",
    }
    engine.validate_applicability(inv, target_scope, [dec_ok])


def test_negative_missing_support():
    """Negative check: Invariant declaring target scopes missing from accepted inventory fails validation."""
    engine = InvariantRegistryEngine()
    src_ref = make_ref("source_identity", "src_1")
    scope_declared = make_ref("surface_record", "surf_declared", logical_id="surf_declared")
    pol_ref = make_ref("policy_revision", "pol_1")

    inv = InvariantRevision(
        invariant_id=new_id("invariant_revision"),
        invariant_revision="1",
        source_generation_ref=src_ref,
        statement="Support check",
        category="RELEASE_ASSURANCE",
        activation_policy_ref=pol_ref,
        target_scope_refs=[scope_declared],
    )

    # Empty available scopes -> fails
    with pytest.raises(ValidationError, match="MISSING_INVARIANT_SUPPORT"):
        engine.validate_support(inv, [])

    # Available scopes containing the declared scope -> passes
    engine.validate_support(inv, [scope_declared])
