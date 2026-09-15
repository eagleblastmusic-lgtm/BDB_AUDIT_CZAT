"""R5.3 R5N-15 regressions for global PRIOR_ACCEPTED_ONLY semantics."""
from __future__ import annotations

from pathlib import Path

import pytest

from bdb_audit.coordinator import run_foundation_reference_slice
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
