"""R5.3 R5N-15 regressions for global PRIOR_ACCEPTED_ONLY semantics."""
from __future__ import annotations

from pathlib import Path

import pytest

from bdb_audit.coordinator import run_foundation_reference_slice
from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.closure import canonical_order
from bdb_audit.history.objects import CanonicalObject
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.read_models import current_accepted_cut


def test_generic_prior_accepted_same_commit_uses_r5n15_error() -> None:
    checkpoint = CanonicalObject("knowledge_state", {"marker": "checkpoint"})
    discovery = CanonicalObject(
        "discovery_record",
        {
            "knowledge_state_ref": checkpoint.as_ref(
                ref_class="PRIOR_ACCEPTED_ONLY"
            ).as_dict()
        },
    )

    with pytest.raises(ValidationError) as exc:
        canonical_order([checkpoint, discovery])

    assert exc.value.code == "BACKWARD_REF_NOT_PRIOR_ACCEPTED"


def test_content_or_prior_same_commit_remains_content_dag_legal() -> None:
    environment = CanonicalObject("environment_record", {"marker": "environment"})
    assessment = CanonicalObject(
        "evidence_applicability_assessment",
        {
            "environment_ref": environment.as_ref(
                ref_class="CONTENT_OR_PRIOR"
            ).as_dict()
        },
    )

    ordered = canonical_order([assessment, environment])
    assert ordered.index(environment.digest) < ordered.index(assessment.digest)


def test_reference_slice_accepts_knowledge_before_discovery(tmp_path: Path) -> None:
    store_path = tmp_path / "r5n15_reference_slice.sqlite"
    result = run_foundation_reference_slice(store_path)

    assert result["commit_count"] == 10
    assert result["head_commit"].commit_seq == 10

    store = TransactionalHistoryStore(store_path)
    cut = current_accepted_cut(store)
    knowledge = store.accepted_records("knowledge_state", cut)
    discoveries = store.accepted_records("discovery_record", cut)

    assert len(knowledge) == 1
    assert len(discoveries) == 1
    knowledge_seq = int(knowledge[0]["accepted_seq"])
    discovery_seq = int(discoveries[0]["accepted_seq"])

    assert knowledge_seq == 5
    assert discovery_seq == 6
    assert knowledge_seq < discovery_seq
    assert discoveries[0]["body"]["discovery_input_history_cut"]["accepted_head_seq"] == knowledge_seq
    assert discoveries[0]["body"]["knowledge_state_ref"]["revision_digest"] == knowledge[0]["ref"]["revision_digest"]
    assert discoveries[0]["body"]["knowledge_state_ref"]["ref_class"] == "PRIOR_ACCEPTED_ONLY"


def _r5n15_context(tmp_path: Path, name: str):
    store_path = tmp_path / name
    ctx = run_foundation_reference_slice(store_path, stop_at_seq=9)
    store = ctx["store"]
    cut = ctx["head_cut"]
    knowledge = store.accepted_records("knowledge_state", cut)[0]
    discovery = store.accepted_records("discovery_record", cut)[0]
    return ctx, store, knowledge, discovery


def _discovery_with_knowledge_ref(ctx, discovery_record, knowledge_ref, discovery_id: str):
    body = dict(discovery_record["body"])
    body["discovery_id"] = discovery_id
    body["discovery_input_history_cut"] = ctx["head_cut"]
    body["knowledge_state_ref"] = knowledge_ref
    return CanonicalObject("discovery_record", body, logical_id=discovery_id)


def test_fabricated_canonical_prior_ref_is_rejected(tmp_path: Path) -> None:
    ctx, store, knowledge, discovery = _r5n15_context(
        tmp_path, "r5n15_fabricated.sqlite"
    )
    fabricated = dict(knowledge["ref"])
    fabricated["revision_digest"] = "f" * 64
    fabricated["ref_class"] = "PRIOR_ACCEPTED_ONLY"
    bad_discovery = _discovery_with_knowledge_ref(
        ctx, discovery, fabricated, "disc_r5n15_fabricated"
    )

    with pytest.raises(ValidationError) as exc:
        ctx["coordinator"].accept(
            ctx["next_cmd"](ctx["head_ref"]),
            immutable_objects=(bad_discovery,),
            expected_head=ctx["head"],
        )

    assert exc.value.code == "BACKWARD_REF_NOT_PRIOR_ACCEPTED"
    assert store.head() == ctx["head"]


def test_orphan_object_row_is_not_prior_acceptance_evidence(tmp_path: Path) -> None:
    ctx, store, knowledge, discovery = _r5n15_context(
        tmp_path, "r5n15_orphan.sqlite"
    )
    orphan_body = dict(knowledge["body"])
    orphan_id = "kstate_r5n15_orphan"
    orphan_body["knowledge_state_id"] = orphan_id
    orphan = CanonicalObject("knowledge_state", orphan_body, logical_id=orphan_id)

    con = store._connect()
    try:
        con.execute(
            "INSERT INTO immutable_objects(digest,kind,version,schema_ref,logical_id,body) "
            "VALUES(?,?,?,?,?,?)",
            (
                orphan.digest,
                orphan.kind,
                orphan.version,
                orphan.schema_revision_ref,
                orphan.logical_id,
                canonical_bytes(orphan.body),
            ),
        )
    finally:
        con.close()

    orphan_ref = orphan.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict()
    bad_discovery = _discovery_with_knowledge_ref(
        ctx, discovery, orphan_ref, "disc_r5n15_orphan"
    )

    with pytest.raises(ValidationError) as exc:
        ctx["coordinator"].accept(
            ctx["next_cmd"](ctx["head_ref"]),
            immutable_objects=(bad_discovery,),
            expected_head=ctx["head"],
        )

    assert exc.value.code == "BACKWARD_REF_NOT_PRIOR_ACCEPTED"
    assert store.object_record(orphan.digest) is not None
    assert store.head() == ctx["head"]
