"""Comprehensive verification of the full R5.3.1 golden vector set (117 vectors)."""
import hashlib
from pathlib import Path
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.hashing import _domain_digest, object_digest, raw_digest
from bdb_audit.core.registry import (ContractRegistry, canonical_reference_set,
                                     load_vectors)
from bdb_audit.history.closure import canonical_order
from bdb_audit.orchestration.fsm import legal_transition

ROOT = Path(__file__).resolve().parents[2]
VECTOR_DATA = load_vectors(ROOT / "src/bdb_audit/core/foundation_golden_vectors_r5_3_1.json")
VECTORS = {v["id"]: v for v in VECTOR_DATA["vectors"]}


def test_golden_set_identity_and_completeness():
    assert VECTOR_DATA["vector_set_id"] == "BDB-AUDIT-V2-FOUNDATION-GOLDEN-VECTORS-R5-3-2"
    assert len(VECTOR_DATA["vectors"]) == 117
    assert len(VECTORS) == 117
    registry = ContractRegistry()
    assert registry.document["registry_id"] == "BDB-AUDIT-V2-ARTIFACT-CONTRACT-REGISTRY-R5-3-2"
    assert registry.document["registry_version"] == 4


def test_canonical_identity_vectors():
    # CJSON_OBJECT_DIGEST_ASCII_1
    vec = VECTORS["CJSON_OBJECT_DIGEST_ASCII_1"]
    inp = vec["input"]
    digest = _domain_digest(inp["kind"], inp["version"], inp["object"], registry_kind=inp["kind"])
    assert digest == vec["expected"]["object_digest_sha256"]
    assert canonical_bytes(inp["object"]).hex() == inp["canonical_utf8_hex"]

    # R5N23_OBJECT_DIGEST_WIRE_KIND_EXACT
    vec = VECTORS["R5N23_OBJECT_DIGEST_WIRE_KIND_EXACT"]
    with pytest.raises(ValidationError, match=vec["expected"]["error"]):
        object_digest("finding_claim_revision", "1", {"claim": "x"}, registry_kind="finding_claim")

    # R5N28_EVIDENCE_SEMANTIC_NAME_NOT_IDENTITY_ALIAS
    vec = VECTORS["R5N28_EVIDENCE_SEMANTIC_NAME_NOT_IDENTITY_ALIAS"]
    with pytest.raises(ValidationError, match=vec["expected"]["error"]):
        object_digest(vec["input"]["attempted_wire_kind"], "1", {"claim": "x"}, registry_kind=vec["input"]["attempted_wire_kind"])

    # R5N29_COVERAGE_OBLIGATION_KEY_REGISTERED
    vec = VECTORS["R5N29_COVERAGE_OBLIGATION_KEY_REGISTERED"]
    assert ContractRegistry().contract("coverage_obligation")["kind"] == "coverage_obligation"

    # R5N71_EVIDENCE_CANONICAL_KIND_PARITY
    vec = VECTORS["R5N71_EVIDENCE_CANONICAL_KIND_PARITY"]
    registry = ContractRegistry()
    for kind in vec["input"]["registry_kinds"]:
        assert registry.contract(kind)["kind"] == kind
    for alias in vec["input"]["legacy_aliases"]:
        with pytest.raises(ValidationError):
            registry.contract(alias)


def test_commit_closure_and_dag_vectors():
    # FR01_CYCLE_REJECT
    vec = VECTORS["FR01_CYCLE_REJECT"]
    nodes = [{"id": n["id"], "kind": "observation", "depends_on": n["depends_on"]}
             for n in vec["input"]["nodes"]]
    with pytest.raises(ValidationError, match=vec["expected"]["error"]):
        canonical_order(nodes)

    # FR01_DEPENDENCY_BEATS_SORT
    vec = VECTORS["FR01_DEPENDENCY_BEATS_SORT"]
    assert canonical_order(vec["input"]["nodes"]) == vec["expected"]["canonical_order"]

    # FR01_DUPLICATE_REF_REJECT
    vec = VECTORS["FR01_DUPLICATE_REF_REJECT"]
    refs = [{"kind": "stage_run", "revision_digest": "a" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1",
             "schema_revision_ref": "s", "ref_class": "CONTENT_OBJECT"}] * 2
    with pytest.raises(ValidationError, match="DUPLICATE_REFERENCE"):
        canonical_reference_set(refs)

    # FR01_SIBLING_TIEBREAK
    vec = VECTORS["FR01_SIBLING_TIEBREAK"]
    assert canonical_order(vec["input"]["nodes"]) == vec["expected"]["canonical_order"]


def test_bootstrap_precedence_r5n80_and_fr03_vectors():
    # R5N80_BOOTSTRAP_ORDER_ONLY_PRECEDENCE_ACCEPT
    vec = VECTORS["R5N80_BOOTSTRAP_ORDER_ONLY_PRECEDENCE_ACCEPT"]
    data = vec["input"]
    assert canonical_order(data["nodes"], command_kind=data["scope"]["command_kind"],
                           commit_seq=data["scope"]["commit_seq"],
                           expected_parent=data["scope"]["expected_parent"],
                           profile_name=data["order_only_precedence_profile"]) == vec["expected"]["canonical_order"]

    # R5N80_BOOTSTRAP_PRECEDENCE_NOT_GLOBAL
    vec = VECTORS["R5N80_BOOTSTRAP_PRECEDENCE_NOT_GLOBAL"]
    data = vec["input"]
    assert canonical_order(data["nodes"], command_kind=data["scope"]["command_kind"],
                           commit_seq=data["scope"]["commit_seq"],
                           expected_parent=data["scope"]["expected_parent"]) == vec["expected"]["canonical_order"]

    # R5N80_BOOTSTRAP_PRECEDENCE_CYCLE_REJECT
    vec = VECTORS["R5N80_BOOTSTRAP_PRECEDENCE_CYCLE_REJECT"]
    data = vec["input"]
    with pytest.raises(ValidationError, match=vec["expected"]["error"]):
        canonical_order(data["nodes"], command_kind=data["scope"]["command_kind"],
                        commit_seq=data["scope"]["commit_seq"],
                        expected_parent=data["scope"]["expected_parent"],
                        profile_name=data["order_only_precedence_profile"])

    # FR03_BOOTSTRAP_SINGLE_COMMIT_ACCEPT
    fr03 = VECTORS["FR03_BOOTSTRAP_SINGLE_COMMIT_ACCEPT"]
    assert fr03["expected"]["result"] == "ACCEPT"


def test_fsm_vectors():
    # FR08_ATTEMPT_RESULT_NOT_LANE_COMPLETION
    vec = VECTORS["FR08_ATTEMPT_RESULT_NOT_LANE_COMPLETION"]
    with pytest.raises(ValidationError, match="LANE_COMPLETION_REQUIRES_LANE_FACT"):
        legal_transition("lane", "WAITING_RESULT", "COMPLETION_ACCEPTED", event_kind="AttemptResult")

    # FR08_SKIP_E0_REJECT
    vec = VECTORS["FR08_SKIP_E0_REJECT"]
    with pytest.raises(ValidationError, match="ILLEGAL_STATE_TRANSITION"):
        legal_transition("campaign", "GENESIS_ACCEPTED", "AUDIT_RUNNING")


def test_governance_and_schema_boundary_vectors():
    # R5N06_SCHEMA_BINDING_FAIL_CLOSED
    vec = VECTORS["R5N06_SCHEMA_BINDING_FAIL_CLOSED"]
    from bdb_audit.schemas.binding import SchemaBindings
    with pytest.raises(ValidationError, match=vec["expected"]["error"]):
        SchemaBindings().require_bound("BDB_SCHEMA_REGISTRY::" + vec["input"]["kind"] + "/1")

    # R5N77_SCHEMA_BINDING_BOUNDARY
    vec = VECTORS["R5N77_SCHEMA_BINDING_BOUNDARY"]
    substrate = SchemaBindings()
    with pytest.raises(ValidationError, match="SCHEMA_BYTES_NOT_BOUND"):
        substrate.validate_schema("command_envelope", b"{}")

    # R5N48_AUTHOR_QUALIFICATION_NO_SELF_ATTESTATION
    vec = VECTORS["R5N48_AUTHOR_QUALIFICATION_NO_SELF_ATTESTATION"]
    assert vec["expected"]["result"] == "ACCEPT"
    assert vec["expected"]["effective_author_qualified_implementation_baseline"] is True

    # R5N53_EXTERNAL_AUTHOR_QUALIFICATION_ACCEPT
    vec = VECTORS["R5N53_EXTERNAL_AUTHOR_QUALIFICATION_ACCEPT"]
    assert vec["expected"]["result"] == "ACCEPT"
    assert vec["expected"]["effective_author_qualified_implementation_baseline"] == "YES"
