"""Targeted tests for Work Package 1 (PR-F4-01): Collector Coverage & Production Domain Inventory."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id
from bdb_audit.inventory import (
    SurfaceKey,
    SurfaceRecord,
    InputDispositionRecord,
    ScopeStateRecord,
    InventoryRevision,
    CollectionRun,
    CollectorProfile,
    CollectorOutput,
    CollectorCoverageEngine,
    validate_terminal_accounting,
    compute_inventory_denominator,
    evaluate_m14_gate,
    SURFACE_CATEGORIES,
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


def test_surface_categories_production_coverage():
    """Verify all 18 normative surface categories are recognized."""
    expected_categories = {
        "HTTP_ROUTE", "STATE_MUTATION", "NETWORK_EGRESS", "PARSER",
        "FILE_IO", "PERSISTENCE", "CACHE", "SUBPROCESS", "CONCURRENCY",
        "TIMER_RETRY_WORKER", "AUTHORITY", "SECRET_CONFIG", "DOM_SINK",
        "EXTERNAL_CONTENT", "CI_SUPPLY_CHAIN", "TEST_ORACLE",
        "ARTIFACT_PRODUCER", "OTHER",
    }
    assert expected_categories == SURFACE_CATEGORIES


def test_collector_coverage_engine_multi_collector_execution():
    """Test multi-collector domain execution covering diverse surface categories."""
    engine = CollectorCoverageEngine()
    src_ref = make_ref("source_identity", "src_v1")
    history_cut = {"tag": "CUT_001", "commit_seq": 10}

    # Collector 1: HTTP API collector
    api_prof = CollectorProfile(
        collector_id="col_api",
        collector_name="HTTP API Collector",
        supported_categories=["HTTP_ROUTE", "AUTHORITY"],
    )

    def api_collector_fn(inputs, s_ref):
        surfaces = []
        dispositions = []
        scopes = []
        for inp in inputs:
            if "api/" in inp:
                s_key = SurfaceKey(
                    source_identity_ref=s_ref,
                    canonical_surface_category="HTTP_ROUTE",
                    normalized_anchor_descriptor={"path": inp, "offset": 10, "method": "POST"},
                )
                surfaces.append(SurfaceRecord(
                    surface_key=s_key.as_object().as_ref(),
                    source_identity_ref=s_ref,
                    surface_category="HTTP_ROUTE",
                    anchor_descriptor={"path": inp, "offset": 10},
                    identity_state="STABLE",
                    surface_record_id=new_id("surface_record"),
                ))
                dispositions.append((inp, "COLLECTED", ["ROUTE_EXTRACTED"]))
        return CollectorOutput(
            collector_id="col_api",
            assigned_inputs=inputs,
            emitted_surfaces=surfaces,
            input_dispositions=dispositions,
            scope_states=scopes,
            completion_status="COMPLETED",
        )

    # Collector 2: Database / Persistence collector
    db_prof = CollectorProfile(
        collector_id="col_db",
        collector_name="Database Models Collector",
        supported_categories=["PERSISTENCE", "STATE_MUTATION"],
    )

    def db_collector_fn(inputs, s_ref):
        surfaces = []
        dispositions = []
        scopes = []
        for inp in inputs:
            if "models/" in inp:
                s_key = SurfaceKey(
                    source_identity_ref=s_ref,
                    canonical_surface_category="PERSISTENCE",
                    normalized_anchor_descriptor={"path": inp, "model": "UserTable"},
                )
                surfaces.append(SurfaceRecord(
                    surface_key=s_key.as_object().as_ref(),
                    source_identity_ref=s_ref,
                    surface_category="PERSISTENCE",
                    anchor_descriptor={"path": inp, "table": "users"},
                    identity_state="STABLE",
                    surface_record_id=new_id("surface_record"),
                ))
                dispositions.append((inp, "COLLECTED", ["MODEL_EXTRACTED"]))
        return CollectorOutput(
            collector_id="col_db",
            assigned_inputs=inputs,
            emitted_surfaces=surfaces,
            input_dispositions=dispositions,
            scope_states=scopes,
            completion_status="COMPLETED",
        )

    engine.register_collector(api_prof, api_collector_fn)
    engine.register_collector(db_prof, db_collector_fn)

    assigned = ["api/v1/auth.py", "models/user.py", "legacy/raw_unsupported.bin"]
    inv_id = new_id("inventory_revision")
    inv, runs, disps, scopes = engine.execute_collection(
        inventory_id=inv_id,
        inventory_revision="1",
        source_generation_ref=src_ref,
        assigned_inputs=assigned,
        history_cut=history_cut,
    )

    assert inv.inventory_id == inv_id
    assert len(inv.surface_refs) == 2
    assert len(inv.assigned_input_refs) == 3
    assert len(runs) == 2

    # Verify that the unhandled input became UNSUPPORTED (and not dropped)
    disp_map = {d.assigned_input_ref["logical_id"]: d.disposition for d in disps}
    assert disp_map["api/v1/auth.py"] == "COLLECTED"
    assert disp_map["models/user.py"] == "COLLECTED"
    assert disp_map["legacy/raw_unsupported.bin"] == "UNSUPPORTED"

    # Verify terminal accounting passes
    acct = validate_terminal_accounting(assigned, disps)
    assert acct["result"] == "PASS"

    # Verify denominator includes UNSUPPORTED_SCOPE
    denom = compute_inventory_denominator(inv, scopes)
    assert denom["breakdown"]["UNSUPPORTED_SCOPE"] == 1
    assert denom["breakdown"]["KNOWN_SURFACE"] == 2
    assert denom["total_denominator"] == 3


def test_provisional_disposition_strictly_rejects_terminal_accounting():
    """PROVISIONAL disposition must reject terminal accounting gate."""
    cut = {"tag": "CUT_001"}
    inp_ref = make_ref("assigned_input_ref", "inp_provisional", logical_id="inp_provisional")
    disp = InputDispositionRecord(
        assigned_input_ref=inp_ref,
        disposition="PROVISIONAL",
        disposition_input_history_cut=cut,
        reason_codes=["SCAN_IN_PROGRESS"],
    )

    acct = validate_terminal_accounting(["inp_provisional"], [disp])
    assert acct["result"] == "REJECT_GATE"
    assert acct["all_assigned_inputs_terminally_accounted"] is False
    assert "inp_provisional" in acct["provisional_inputs"]


def test_failed_collector_remains_in_denominator_and_not_na():
    """Collector failure must NOT be marked as NOT_APPLICABLE; remains in denominator as COLLECTION_FAILED."""
    cut = {"tag": "CUT_001"}
    inp_ref = make_ref("assigned_input_ref", "failing_parser.py", logical_id="failing_parser.py")

    # Collector fails on parsing
    disp = InputDispositionRecord(
        assigned_input_ref=inp_ref,
        disposition="COLLECTION_FAILED",
        disposition_input_history_cut=cut,
        reason_codes=["AST_CRASH"],
    )
    scope = ScopeStateRecord(
        scope_key="scope_failing_parser",
        state="COLLECTION_FAILED",
        scope_state_input_history_cut=cut,
        reason_codes=["AST_CRASH"],
    )

    inv = InventoryRevision(
        inventory_id=new_id("inventory_revision"),
        inventory_revision="1",
        source_generation_ref=make_ref("source_identity", "src_1"),
        basis_history_cut=cut,
        assigned_input_refs=[inp_ref],
        input_disposition_refs=[disp.as_object().as_ref()],
        surface_refs=[],
        scope_state_record_refs=[scope.as_object().as_ref()],
    )

    denom = compute_inventory_denominator(inv, [scope])
    # Denominator must NOT be zero; the failed scope must remain visible
    assert denom["total_denominator"] == 1
    assert denom["breakdown"]["COLLECTION_FAILED"] == 1
    assert denom["unsupported_failed_unknown_visible"] == 1


def test_deterministic_replay_identical_inputs():
    """Replay of identical inputs on identical history cut produces identical canonical hashes."""
    engine = CollectorCoverageEngine()
    src_ref = make_ref("source_identity", "src_repro")
    cut = {"tag": "CUT_REPRO", "commit_seq": 42}
    assigned = ["api/route.py", "db/table.py"]

    prof = CollectorProfile(
        collector_id="col_static",
        collector_name="Static Collector",
        supported_categories=["PARSER", "HTTP_ROUTE"],
    )

    fixed_surf_id_1 = "surface_record_11111111-1111-4111-8111-111111111111"
    fixed_surf_id_2 = "surface_record_22222222-2222-4222-8222-222222222222"

    def collector_fn(inputs, s_ref):
        surfaces = []
        disps = []
        scopes = []
        for idx, inp in enumerate(inputs):
            s_key = SurfaceKey(
                source_identity_ref=s_ref,
                canonical_surface_category="PARSER",
                normalized_anchor_descriptor={"file": inp},
            )
            surfaces.append(SurfaceRecord(
                surface_key=s_key.as_object().as_ref(),
                source_identity_ref=s_ref,
                surface_category="PARSER",
                anchor_descriptor={"file": inp},
                identity_state="STABLE",
                surface_record_id=fixed_surf_id_1 if idx == 0 else fixed_surf_id_2,
            ))
            disps.append((inp, "COLLECTED", ["OK"]))
        return CollectorOutput(
            collector_id="col_static",
            assigned_inputs=inputs,
            emitted_surfaces=surfaces,
            input_dispositions=disps,
            scope_states=scopes,
            completion_status="COMPLETED",
        )

    engine.register_collector(prof, collector_fn)

    inv_id = "inventory_revision_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    inv1, runs1, disps1, scopes1 = engine.execute_collection(inv_id, "1", src_ref, assigned, cut)
    inv2, runs2, disps2, scopes2 = engine.execute_collection(inv_id, "1", src_ref, assigned, cut)

    # Identical object digests
    assert inv1.digest == inv2.digest
    assert len(runs1) == len(runs2)
    assert runs1[0].as_object().digest == runs2[0].as_object().digest


def test_retry_idempotency_and_no_double_effect():
    """Retrying after failure creates a new clean revision without duplicate dispositions."""
    cut1 = {"tag": "CUT_001", "commit_seq": 10}
    cut2 = {"tag": "CUT_002", "commit_seq": 11}
    inp_ref = make_ref("assigned_input_ref", "retry_file.py", logical_id="retry_file.py")

    # Initial failed disposition
    disp_failed = InputDispositionRecord(
        assigned_input_ref=inp_ref,
        disposition="COLLECTION_FAILED",
        disposition_input_history_cut=cut1,
        reason_codes=["TIMEOUT"],
    )

    # Retry disposition on next cut
    disp_success = InputDispositionRecord(
        assigned_input_ref=inp_ref,
        disposition="COLLECTED",
        disposition_input_history_cut=cut2,
        reason_codes=["RETRY_SUCCESS"],
    )

    # In Revision 1: failed
    inv1 = InventoryRevision(
        inventory_id=new_id("inventory_revision"),
        inventory_revision="1",
        source_generation_ref=make_ref("source_identity", "src_1"),
        basis_history_cut=cut1,
        assigned_input_refs=[inp_ref],
        input_disposition_refs=[disp_failed.as_object().as_ref()],
        surface_refs=[],
    )

    # In Revision 2: success (clean single disposition for the input in rev2)
    inv2 = InventoryRevision(
        inventory_id=new_id("inventory_revision"),
        inventory_revision="2",
        source_generation_ref=make_ref("source_identity", "src_1"),
        basis_history_cut=cut2,
        assigned_input_refs=[inp_ref],
        input_disposition_refs=[disp_success.as_object().as_ref()],
        surface_refs=[],
    )

    assert inv1.digest != inv2.digest
    # Check that in revision 2, terminal accounting has exactly one disposition per input
    acct2 = validate_terminal_accounting(["retry_file.py"], [disp_success])
    assert acct2["result"] == "PASS"
