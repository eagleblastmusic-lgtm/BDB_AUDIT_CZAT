"""Targeted tests for Work Package 4 (PR-F4-04): Production Gap Engine & Rebuild Equivalence."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id, deterministic_id
from bdb_audit.coverage import (
    CoverageObligation,
    CoverageObligationQualification,
    MaterialityAssessment,
    GapRecord,
    GapMap,
    GapEngine,
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


def make_test_obligation(ob_id_seed: str, target_surf_ref: dict) -> CoverageObligation:
    ob_id = deterministic_id("coverage_obligation", ob_id_seed)
    return CoverageObligation(
        obligation_id=ob_id,
        obligation_revision="1",
        obligation_input_history_cut={"tag": "CUT_001"},
        source_generation_ref=make_ref("source_identity", "src_1"),
        target_scope_or_surface_ref=target_surf_ref,
        invariant_revision_ref=make_ref("invariant_revision", "inv_1"),
        scenario_class="DYNAMIC_TEST",
        environment_profile_ref=make_ref("environment_profile", "env_1"),
        materiality_assessment_ref=make_ref("materiality_assessment", "mat_1"),
        required_oracle_independence_predicate_ref=make_ref("predicate", "p1"),
        acceptance_predicate_ref=make_ref("predicate", "p2"),
        applicability_predicate_ref=make_ref("predicate", "p3"),
        policy_obligation_key=f"pol_key_{ob_id_seed}",
        governing_policy_ref=make_ref("policy_revision", "pol_1"),
        origin_ref=target_surf_ref,
    )


def test_gap_engine_rebuild_equivalence():
    """Rebuilding the GapMap from identical canonical domain facts produces byte-for-byte identical digests."""
    engine = GapEngine()
    surf1 = make_ref("surface_record", "surf_1", logical_id="surf_1")
    surf2 = make_ref("surface_record", "surf_2", logical_id="surf_2")
    ob1 = make_test_obligation("ob_1", surf1)
    ob2 = make_test_obligation("ob_2", surf2)

    qual1 = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob1.as_object().as_ref(),
        input_history_cut={"tag": "CUT_001"},
        qualification_status="QUALIFIED",
        substantive_outcome="NO_VIOLATION_OBSERVED",
    )
    # ob2 is unassessed (gap)

    cut = {"tag": "CUT_001", "commit_seq": 10}
    map1 = engine.compute_gap_map(
        inventory_surfaces=[surf1, surf2],
        obligations=[ob1, ob2],
        qualifications=[qual1],
        history_cut=cut,
    )
    map2 = engine.compute_gap_map(
        inventory_surfaces=[surf1, surf2],
        obligations=[ob1, ob2],
        qualifications=[qual1],
        history_cut=cut,
    )

    assert map1.digest == map2.digest
    assert map1.canonical_bytes() == map2.canonical_bytes()
    assert len(map1.gaps) == 1
    assert map1.gaps[0].target_scope_ref["logical_id"] == "surf_2"


def test_dynamic_reaction_to_new_surface():
    """Introducing a new surface with unassessed obligations creates a new GapRecord."""
    engine = GapEngine()
    surf1 = make_ref("surface_record", "surf_1", logical_id="surf_1")
    ob1 = make_test_obligation("ob_1", surf1)
    qual1 = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob1.as_object().as_ref(),
        input_history_cut={"tag": "CUT_001"},
        qualification_status="QUALIFIED",
        substantive_outcome="NO_VIOLATION_OBSERVED",
    )

    # Initially: all satisfied, 0 gaps
    map_init = engine.compute_gap_map(
        inventory_surfaces=[surf1],
        obligations=[ob1],
        qualifications=[qual1],
    )
    assert len(map_init.gaps) == 0

    # New surface added to inventory with an unsatisfied obligation
    surf_new = make_ref("surface_record", "surf_new", logical_id="surf_new")
    ob_new = make_test_obligation("ob_new", surf_new)

    map_after = engine.compute_gap_map(
        inventory_surfaces=[surf1, surf_new],
        obligations=[ob1, ob_new],
        qualifications=[qual1],
    )
    assert len(map_after.gaps) == 1
    assert map_after.gaps[0].target_scope_ref["logical_id"] == "surf_new"
    assert len(map_after.gaps[0].missing_or_unsatisfied_obligation_refs) == 1


def test_dynamic_reaction_to_evidence_invalidation_and_replacement():
    """Invalidation re-opens a gap; replacement evidence closes it again."""
    engine = GapEngine()
    surf1 = make_ref("surface_record", "surf_1", logical_id="surf_1")
    ob1 = make_test_obligation("ob_1", surf1)
    ev_ref = make_ref("evidence_qualification_assessment", "ev_initial")

    qual1 = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob1.as_object().as_ref(),
        input_history_cut={"tag": "CUT_001"},
        qualification_status="QUALIFIED",
        substantive_outcome="NO_VIOLATION_OBSERVED",
        evidence_qualification_refs=[ev_ref],
    )

    # 1. Clean state: 0 gaps
    map_clean = engine.compute_gap_map(
        inventory_surfaces=[surf1],
        obligations=[ob1],
        qualifications=[qual1],
    )
    assert len(map_clean.gaps) == 0

    # 2. Evidence invalidated: re-opens gap
    ev_digest = ev_ref["revision_digest"]
    map_invalidated = engine.compute_gap_map(
        inventory_surfaces=[surf1],
        obligations=[ob1],
        qualifications=[qual1],
        invalidated_evidence_digests={ev_digest},
    )
    assert len(map_invalidated.gaps) == 1
    assert map_invalidated.gaps[0].target_scope_ref["logical_id"] == "surf_1"

    # 3. Replacement evidence provided: closes gap
    ev_replacement = make_ref("evidence_qualification_assessment", "ev_replacement")
    qual_replaced = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob1.as_object().as_ref(),
        input_history_cut={"tag": "CUT_002"},
        qualification_status="QUALIFIED",
        substantive_outcome="NO_VIOLATION_OBSERVED",
        evidence_qualification_refs=[ev_replacement],
    )
    map_resolved = engine.compute_gap_map(
        inventory_surfaces=[surf1],
        obligations=[ob1],
        qualifications=[qual_replaced],
        invalidated_evidence_digests={ev_digest},
    )
    assert len(map_resolved.gaps) == 0


def test_dynamic_reaction_to_failed_collector_and_unsupported_scope():
    """Failed collector or unsupported scope creates a high-penalty gap."""
    engine = GapEngine()
    scope_failed = {
        "scope_key": "failed_ast_parser",
        "state": "COLLECTION_FAILED",
        "kind": "scope_state_record",
        "revision_digest": hashlib.sha256(b"failed_scope").hexdigest(),
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::scope_state_record/1",
        "ref_class": "CONTENT_OR_PRIOR",
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "logical_id": "failed_ast_parser",
    }
    scope_unsupported = {
        "scope_key": "unsupported_cobol",
        "state": "UNSUPPORTED_SCOPE",
        "kind": "scope_state_record",
        "revision_digest": hashlib.sha256(b"unsupported_scope").hexdigest(),
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::scope_state_record/1",
        "ref_class": "CONTENT_OR_PRIOR",
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "logical_id": "unsupported_cobol",
    }

    g_map = engine.compute_gap_map(
        inventory_surfaces=[],
        obligations=[],
        qualifications=[],
        scope_states=[scope_failed, scope_unsupported],
    )

    assert len(g_map.gaps) == 2
    g_failed = next(g for g in g_map.gaps if g.target_scope_ref.get("logical_id") == "failed_ast_parser")
    assert g_failed.priority_basis["scope_state"] == "COLLECTION_FAILED"
    # COLLECTION_FAILED has higher penalty (15) than UNSUPPORTED (10)
    assert g_failed.priority_basis["unknown_scope_penalty"] == 15


def test_dynamic_reaction_to_contradiction():
    """Unresolved contradiction creates a gap and elevates priority score."""
    engine = GapEngine()
    surf1 = make_ref("surface_record", "surf_auth", logical_id="surf_auth")
    ob1 = make_test_obligation("ob_auth", surf1)
    qual1 = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob1.as_object().as_ref(),
        input_history_cut={"tag": "CUT_001"},
        qualification_status="QUALIFIED",
        substantive_outcome="NO_VIOLATION_OBSERVED",
    )

    contra = {
        "contradiction_id": new_id("contradiction_revision"),
        "scope": surf1,
        "status": "OPEN",
        "kind": "contradiction_revision",
        "revision_digest": hashlib.sha256(b"contra_1").hexdigest(),
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::contradiction_revision/1",
        "ref_class": "CONTENT_OR_PRIOR",
        "digest_profile": "BDB-OBJECT-DIGEST-1",
    }

    g_map = engine.compute_gap_map(
        inventory_surfaces=[surf1],
        obligations=[ob1],
        qualifications=[qual1],
        contradictions=[contra],
    )

    # Even though obligations are satisfied, the active contradiction generates a gap!
    assert len(g_map.gaps) == 1
    gap = g_map.gaps[0]
    assert gap.priority_basis["contradiction_count"] == 1
    # Priority includes contradiction penalty (+10.0)
    assert gap.priority_basis["derived_priority_score"] >= 20.0
