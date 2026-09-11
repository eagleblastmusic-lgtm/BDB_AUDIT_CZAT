"""Targeted unit and gate verification for PR-020 / M14 minimal inventory accounting."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id, validate_id
from bdb_audit.core.registry import ContractRegistry, load_vectors
from bdb_audit.history.objects import CanonicalObject, ObjectRef
from bdb_audit.inventory import (
    SurfaceKey, SurfaceRecord, InputDispositionRecord, ScopeStateRecord,
    InventoryRevision, CollectionRun, validate_terminal_accounting,
    compute_inventory_denominator, evaluate_m14_gate,
)
from bdb_audit.schemas.foundation import F3_KINDS, foundation_schema_bindings
from bdb_audit.schemas.identity import LayeredValidator


def ref(kind, seed, ref_class="CONTENT_OR_PRIOR", logical_id=None):
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
        **({"logical_id": logical_id} if logical_id else {}),
    }


def test_surface_key_and_record():
    s_ident = ref("source_identity", "src_id_1")
    s_key = SurfaceKey(
        source_identity_ref=s_ident,
        canonical_surface_category="HTTP_ROUTE",
        normalized_anchor_descriptor={"repo_relative_posix_path": "api/v1/user.py", "byte_offset": 120, "entry_kind": "route", "discriminator": "GET"},
    )
    assert len(s_key.digest) == 64
    assert s_key.as_object().kind == "surface_key"

    s_rec = SurfaceRecord(
        surface_key=s_key.as_object().as_ref().as_dict(),
        source_identity_ref=s_ident,
        surface_category="HTTP_ROUTE",
        anchor_descriptor={"repo_relative_posix_path": "api/v1/user.py", "byte_offset": 120},
        provenance_refs=[],
        identity_state="STABLE",
        surface_record_id=new_id("surface_record"),
    )
    assert len(s_rec.digest) == 64
    assert s_rec.as_object().kind == "surface_record"


def test_input_disposition_record_and_enum_separation():
    cut = {"tag": "EMPTY_HISTORY"}
    input_ref = ref("assigned_input_ref", "input_1")

    # Valid terminal disposition
    disp = InputDispositionRecord(
        assigned_input_ref=input_ref,
        disposition="COLLECTED",
        disposition_input_history_cut=cut,
        reason_codes=["PARSE_OK"],
    )
    assert disp.disposition == "COLLECTED"
    assert disp.as_object().kind == "input_disposition_record"

    # R5N49: ScopeState value in InputDisposition must be rejected with ENUM_DOMAIN_MISMATCH
    with pytest.raises(ValidationError, match="ENUM_DOMAIN_MISMATCH"):
        InputDispositionRecord(
            assigned_input_ref=input_ref,
            disposition="PROVISIONAL_SCOPE",
            disposition_input_history_cut=cut,
        )

    # Invalid disposition
    with pytest.raises(ValidationError, match="INVALID_INPUT_DISPOSITION"):
        InputDispositionRecord(
            assigned_input_ref=input_ref,
            disposition="NOT_A_DISPOSITION",
            disposition_input_history_cut=cut,
        )


def test_scope_state_record_and_enum_separation():
    cut = {"tag": "EMPTY_HISTORY"}

    # Valid scope state
    rec = ScopeStateRecord(
        scope_key="module_auth",
        state="KNOWN_SURFACE",
        scope_state_input_history_cut=cut,
        basis_refs=[],
        reason_codes=["AUDITED"],
    )
    assert rec.state == "KNOWN_SURFACE"

    # Excluded scope requires decision
    with pytest.raises(ValidationError, match="EXCLUDED_SCOPE_REQUIRES_DECISION"):
        ScopeStateRecord(
            scope_key="legacy_module",
            state="EXCLUDED_SCOPE",
            scope_state_input_history_cut=cut,
            scope_decision_ref=None,
        )

    # R5N49: InputDisposition value in ScopeState must be rejected with ENUM_DOMAIN_MISMATCH
    with pytest.raises(ValidationError, match="ENUM_DOMAIN_MISMATCH"):
        ScopeStateRecord(
            scope_key="test_key",
            state="PROVISIONAL",
            scope_state_input_history_cut=cut,
        )


def test_inventory_revision_and_domain_separation():
    cut = {"tag": "EMPTY_HISTORY"}
    src_gen = ref("source_generation", "gen_1")
    inp_1 = ref("assigned_input_ref", "inp_1")
    disp_1 = ref("input_disposition_record", "disp_1")
    scope_1 = ref("scope_state_record", "scope_1")
    surf_1 = ref("surface_record", "surf_1")

    inv = InventoryRevision(
        inventory_id=new_id("inventory_revision"),
        inventory_revision="1",
        source_generation_ref=src_gen,
        basis_history_cut=cut,
        assigned_input_refs=[inp_1],
        input_disposition_refs=[disp_1],
        surface_refs=[surf_1],
        scope_state_record_refs=[scope_1],
    )
    assert len(inv.digest) == 64

    # R5N75: Cross-domain references must be rejected
    with pytest.raises(ValidationError, match="REFERENCE_TARGET_KIND_MISMATCH"):
        InventoryRevision(
            inventory_id=new_id("inventory_revision"),
            inventory_revision="1",
            source_generation_ref=src_gen,
            basis_history_cut=cut,
            assigned_input_refs=[disp_1],  # Wrong kind!
            input_disposition_refs=[disp_1],
        )

    with pytest.raises(ValidationError, match="REFERENCE_TARGET_KIND_MISMATCH"):
        InventoryRevision(
            inventory_id=new_id("inventory_revision"),
            inventory_revision="1",
            source_generation_ref=src_gen,
            basis_history_cut=cut,
            assigned_input_refs=[inp_1],
            input_disposition_refs=[scope_1],  # Wrong kind!
        )


def test_terminal_accounting_validation():
    # Complete terminal accounting
    inputs = ["inp_1", "inp_2"]
    dispositions = [
        {"id": "inp_1", "disposition": "COLLECTED"},
        {"id": "inp_2", "disposition": "UNSUPPORTED"},
    ]
    res = validate_terminal_accounting(inputs, dispositions)
    assert res["result"] == "PASS"
    assert res["all_assigned_inputs_terminally_accounted"] is True

    # Missing input -> INCOMPLETE_INPUT_ACCOUNTING (R5N75)
    with pytest.raises(ValidationError, match="INCOMPLETE_INPUT_ACCOUNTING"):
        validate_terminal_accounting(inputs, [{"id": "inp_1", "disposition": "COLLECTED"}])

    # Ambiguous duplicate -> AMBIGUOUS_DUPLICATE_DISPOSITION
    with pytest.raises(ValidationError, match="AMBIGUOUS_DUPLICATE_DISPOSITION"):
        validate_terminal_accounting(
            inputs,
            [
                {"id": "inp_1", "disposition": "COLLECTED"},
                {"id": "inp_1", "disposition": "UNSUPPORTED"},
                {"id": "inp_2", "disposition": "COLLECTED"},
            ]
        )

    # FR13: PROVISIONAL rejects terminal accounting gate
    prov_res = validate_terminal_accounting(
        ["I1"],
        [{"id": "I1", "input_disposition": "PROVISIONAL"}]
    )
    assert prov_res["result"] == "REJECT_GATE"
    assert prov_res["all_assigned_inputs_terminally_accounted"] is False


def test_m14_golden_vectors():
    vectors = load_vectors()["vectors"]
    by_id = {v["id"]: v for v in vectors}

    # FR13_PROVISIONAL_TERMINAL_REJECT
    v_fr13 = by_id["FR13_PROVISIONAL_TERMINAL_REJECT"]
    res = validate_terminal_accounting(
        [v_fr13["input"]["assigned_inputs"][0]["id"]],
        v_fr13["input"]["assigned_inputs"]
    )
    assert res["gate"] == v_fr13["expected"]["gate"]
    assert res["result"] == v_fr13["expected"]["result"]

    # R5N68_SURFACE_RECORD_REGISTERED_IDENTITY
    v_r5n68 = by_id["R5N68_SURFACE_RECORD_REGISTERED_IDENTITY"]
    reg = ContractRegistry()
    assert reg.contract("surface_record")["kind"] == v_r5n68["input"]["canonical_kind"]

    # R5N70_INVENTORY_INVARIANT_MATERIALITY_EXPLICIT
    v_r5n70 = by_id["R5N70_INVENTORY_INVARIANT_MATERIALITY_EXPLICIT"]
    for kind in v_r5n70["input"]["kinds"]:
        assert reg.contract(kind)["reference_contract_mode"] == v_r5n70["input"]["required_mode"]

    # R5N75_INVENTORY_ONE_DISPOSITION_PER_ASSIGNED_INPUT
    v_r5n75_1 = by_id["R5N75_INVENTORY_ONE_DISPOSITION_PER_ASSIGNED_INPUT"]
    with pytest.raises(ValidationError, match=v_r5n75_1["expected"]["error"]):
        validate_terminal_accounting(
            v_r5n75_1["input"]["assigned_input_refs"],
            [{"id": x, "disposition": "COLLECTED"} for x in v_r5n75_1["input"]["disposition_records_for"]],
        )

    # R5N75_INVENTORY_TYPED_ACCOUNTING_DOMAINS
    v_r5n75_2 = by_id["R5N75_INVENTORY_TYPED_ACCOUNTING_DOMAINS"]
    with pytest.raises(ValidationError, match=v_r5n75_2["expected"]["error"]):
        InventoryRevision(
            inventory_id=new_id("inventory_revision"),
            inventory_revision="1",
            source_generation_ref=ref("source_generation", "gen_1"),
            basis_history_cut={"tag": "EMPTY_HISTORY"},
            assigned_input_refs=v_r5n75_2["input"]["assigned_input_refs"],
            input_disposition_refs=v_r5n75_2["input"]["input_disposition_refs"],
            scope_state_record_refs=v_r5n75_2["input"]["scope_state_record_refs"],
        )


def test_m14_gate_full_evaluation():
    cut = {"tag": "EMPTY_HISTORY"}
    src_gen = ref("source_generation", "gen_1")
    inp_1 = ref("assigned_input_ref", "inp_1", logical_id="input_auth")
    inp_2 = ref("assigned_input_ref", "inp_2", logical_id="input_route")

    disp_1 = InputDispositionRecord(
        assigned_input_ref=inp_1,
        disposition="COLLECTED",
        disposition_input_history_cut=cut,
        input_disposition_record_id=new_id("input_disposition_record"),
    )
    disp_2 = InputDispositionRecord(
        assigned_input_ref=inp_2,
        disposition="UNSUPPORTED",
        disposition_input_history_cut=cut,
        input_disposition_record_id=new_id("input_disposition_record"),
    )

    s_key = SurfaceKey(
        source_identity_ref=ref("source_identity", "src_1"),
        canonical_surface_category="HTTP_ROUTE",
        normalized_anchor_descriptor={"path": "auth.py", "byte_offset": 0, "discriminator": "1"},
    )
    surf_1 = SurfaceRecord(
        surface_key=s_key.as_object().as_ref().as_dict(),
        source_identity_ref=ref("source_identity", "src_1"),
        surface_category="HTTP_ROUTE",
        anchor_descriptor={"path": "auth.py", "byte_offset": 0},
        surface_record_id=new_id("surface_record"),
    )

    scope_unsupported = ScopeStateRecord(
        scope_key="unsupported_subsystem",
        state="UNSUPPORTED_SCOPE",
        scope_state_input_history_cut=cut,
        scope_state_record_id=new_id("scope_state_record"),
    )

    inv_rev1 = InventoryRevision(
        inventory_id=new_id("inventory_revision"),
        inventory_revision="1",
        source_generation_ref=src_gen,
        basis_history_cut=cut,
        assigned_input_refs=[inp_1, inp_2],
        input_disposition_refs=[disp_1.as_object().as_ref().as_dict(), disp_2.as_object().as_ref().as_dict()],
        surface_refs=[surf_1.as_object().as_ref().as_dict()],
        scope_state_record_refs=[scope_unsupported.as_object().as_ref().as_dict()],
    )

    gate_result = evaluate_m14_gate(
        inv_rev1,
        [disp_1, disp_2],
        [scope_unsupported],
    )
    assert gate_result["result"] == "PASS"
    assert gate_result["ALL_ASSIGNED_INPUTS_TERMINALLY_ACCOUNTED"] == "YES"
    assert gate_result["UNSUPPORTED_FAILED_SCOPE_REMAINS_VISIBLE"] == "YES"

    # Denominator breakdown preserves non-surface scope
    denom = gate_result["denominator"]
    assert denom["breakdown"]["KNOWN_SURFACE"] == 1
    assert denom["breakdown"]["UNSUPPORTED_SCOPE"] == 1
    assert denom["total_denominator"] == 2

    # Late surface produces revision 2 and recomputes coverage
    surf_2 = SurfaceRecord(
        surface_key=SurfaceKey(
            source_identity_ref=ref("source_identity", "src_1"),
            canonical_surface_category="PARSER",
            normalized_anchor_descriptor={"path": "parser.py", "byte_offset": 0, "discriminator": "1"},
        ).as_object().as_ref().as_dict(),
        source_identity_ref=ref("source_identity", "src_1"),
        surface_category="PARSER",
        anchor_descriptor={"path": "parser.py", "byte_offset": 0},
        surface_record_id=new_id("surface_record"),
    )

    inv_rev2 = InventoryRevision(
        inventory_id=new_id("inventory_revision"),
        inventory_revision="2",
        source_generation_ref=src_gen,
        basis_history_cut=cut,
        assigned_input_refs=[inp_1, inp_2],
        input_disposition_refs=[disp_1.as_object().as_ref().as_dict(), disp_2.as_object().as_ref().as_dict()],
        surface_refs=[surf_1.as_object().as_ref().as_dict(), surf_2.as_object().as_ref().as_dict()],
        scope_state_record_refs=[scope_unsupported.as_object().as_ref().as_dict()],
    )

    gate_rev2 = evaluate_m14_gate(
        inv_rev2,
        [disp_1, disp_2],
        [scope_unsupported],
        prior_inventory=inv_rev1,
        prior_covered_units=1,
    )
    assert gate_rev2["result"] == "PASS"
    assert gate_rev2["LATE_SURFACE_CREATES_NEW_INVENTORY_REVISION"] == "PASS"
    assert gate_rev2["OLD_COVERAGE_RECOMPUTES_ON_NEW_DENOMINATOR"] == "PASS"
    assert gate_rev2["recomputed_coverage"] == 1 / 3


def test_m14_schemas_with_layered_validator():
    bindings = foundation_schema_bindings(kinds=F3_KINDS)
    validator = LayeredValidator(bindings=bindings)

    cut = {"tag": "EMPTY_HISTORY"}
    disp = InputDispositionRecord(
        assigned_input_ref=ref("assigned_input_ref", "inp_1"),
        disposition="COLLECTED",
        disposition_input_history_cut=cut,
    )
    validated = validator.validate("input_disposition_record", canonical_bytes(disp.body()))
    assert validated.revision_digest == disp.digest
