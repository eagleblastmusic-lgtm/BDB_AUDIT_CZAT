"""M45 authority regressions for adaptive E6 StageSpec.

These tests deliberately cross the real Coordinator/history boundary.  Model
construction alone is not evidence that an adaptive E6 plan is canonical or
eligible for accepted history.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from bdb_audit.assurance.finalization_service import FinalizationService
from bdb_audit.coordinator.reference_slice import run_foundation_reference_slice
from bdb_audit.core.errors import ValidationError
from bdb_audit.orchestration.stages import StageSpec
from bdb_audit.schemas.foundation import executable_schema
from bdb_audit.stop.e6 import AdaptiveE6Generator, E6_RELATIONSHIP_PROFILE
from bdb_audit.workflow.stage_service import StageService
from bdb_audit.workflow.read_models import current_accepted_cut


def _prepare_e5_complete_store(tmp_path: Path):
    ctx = run_foundation_reference_slice(tmp_path / "e6_authority.sqlite", stop_at_seq=9)
    store = ctx["store"]

    # The foundation slice already completed E3.  Add the remaining canonical
    # ordinary stage specifications, then complete E1/E2/E4/E5 through the real
    # StageService so the final STOP sees the complete required stage set.
    stage_specs = []
    for ordinal, key in ((1, "E1"), (2, "E2"), (4, "E4"), (5, "E5")):
        predecessor = (f"E{ordinal - 1}",) if ordinal > 1 else ()
        stage_specs.append(
            StageSpec(
                stage_key=key,
                stage_spec_revision="1",
                stage_role=key,
                stage_ordinal=ordinal,
                purpose=f"M45 integration {key}",
                predecessor_requirements=predecessor,
                transition_policy_ref="TRANSITION_PROFILE_V1",
            ).as_object()
        )

    head = store.head()
    assert head is not None
    head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    ctx["coordinator"].accept(
        ctx["next_cmd"](head_ref),
        immutable_objects=tuple(stage_specs),
        expected_head=head,
    )

    stages = StageService(store)
    stages.qualify_and_complete_stage("E1")
    stages.qualify_and_complete_stage("E2")
    stages.qualify_and_complete_stage("E4")
    stages.qualify_and_complete_stage("E5")
    return ctx


def test_generated_e6_body_is_exact_executable_stage_spec() -> None:
    from tests.f7.test_pr11_adaptive_e6_generator import base_stop_artifacts as _fixture  # noqa: F401

    # Build a compact preview input locally; the authority test below proves
    # accepted-history provenance independently.
    from bdb_audit.stop.models import StopInput, StopEvaluation
    import hashlib

    def ref(kind: str, token: str, ref_class: str = "CONTENT_OR_PRIOR"):
        return {
            "kind": kind,
            "revision_digest": hashlib.sha256(token.encode()).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
            "ref_class": ref_class,
        }

    cut = {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "CAMP-E6-SCHEMA",
        "accepted_head_seq": 12,
        "accepted_head_hash": "a" * 64,
        "governing_policy_ref": "pin:initial_governing_policy_ref",
        "governing_spec_refs": ["pin:initial_transition_profile_ref"],
    }
    obligation = ref("coverage_obligation", "obligation")
    stop_input = StopInput(
        campaign_id="CAMP-E6-SCHEMA",
        source_generation_ref=ref("source_generation", "source"),
        input_history_cut=cut,
        evaluation_context="FINAL_POST_E5",
        governing_policy_ref=ref("policy_revision", "policy", "HISTORY_CONTEXT_BINDING"),
        policy_spec_refs=[ref("spec_revision", "spec", "HISTORY_CONTEXT_BINDING")],
        evaluator_revision_ref=ref("spec_revision", "eval", "HISTORY_CONTEXT_BINDING"),
        required_stage_set_ref=ref("external_profile_ref", "set", "HISTORY_CONTEXT_BINDING"),
        required_stage_spec_refs=[],
        completed_stage_refs=[],
        pending_required_stage_refs=[],
        stop_input_snapshot_ref=ref("snapshot", "snapshot"),
        inventory_revision_ref=ref("inventory_revision", "inventory"),
        mandatory_obligation_refs=[obligation],
        current_obligation_qualification_refs=[],
        evidence_invalidation_refs=[],
        contradiction_refs=[],
        residual_risk_refs=[],
        evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=ref("policy_revision", "release", "HISTORY_CONTEXT_BINDING"),
        effort_profile_ref=ref("external_profile_ref", "effort", "HISTORY_CONTEXT_BINDING"),
        effort_results_ref={"rounds_executed": 1},
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": False},
    )
    evaluation = StopEvaluation(
        stop_input_ref=stop_input.ref,
        continuation_decision="E6_REQUIRED",
        assurance_level="BOUNDED",
        release_readiness="QUALIFICATION_BLOCKED",
        reason_codes=("E6_REQUIRED",),
        blocking_obligation_refs=(obligation,),
        remaining_obligation_refs=(obligation,),
    )
    e6 = AdaptiveE6Generator.generate_e6_spec(
        spec_id="e6_schema_control",
        stop_evaluation=evaluation,
        stop_input=stop_input,
        trust_profile_ref=ref("trust_profile", "trust", "HISTORY_CONTEXT_BINDING"),
        isolation_profile_ref={
            "kind": "isolation_profile",
            "revision_digest": hashlib.sha256(b"isolation").hexdigest(),
            "isolation_level": "STRICT",
        },
    )

    body = e6.body()
    Draft202012Validator(executable_schema("stage_spec")).validate(body)
    assert body["stage_key"] == "E6"
    assert body["stage_role"] == "E6"
    assert body["stage_ordinal"] == 6
    assert body["stop_e6_relationship"].startswith(E6_RELATIONSHIP_PROFILE + "|")
    assert "e6_stage_spec_id" not in body
    assert e6.as_object().kind == "stage_spec"


def test_e6_stage_spec_is_accepted_only_from_prior_accepted_e6_required_stop(tmp_path: Path) -> None:
    ctx = _prepare_e5_complete_store(tmp_path)
    store = ctx["store"]

    finalization = FinalizationService(store)
    stop_result = finalization.evaluate_stop_gate(
        evaluation_context="FINAL_POST_E5",
        e6_plan_approved=True,
    )
    assert stop_result["continuation_decision"] == "E6_REQUIRED"

    cut = current_accepted_cut(store)
    stop_records = store.accepted_records("stop_evaluation", cut)
    stop_record = max(stop_records, key=lambda row: int(row["accepted_seq"]))

    e6 = AdaptiveE6Generator.generate_e6_spec_from_store(
        store,
        spec_id="e6_authoritative_01",
        stop_evaluation_ref=stop_record["ref"],
        isolation_profile_ref={
            "kind": "isolation_profile",
            "revision_digest": "b" * 64,
            "isolation_level": "STRICT",
        },
    )

    head = store.head()
    assert head is not None
    result = ctx["coordinator"].accept(
        ctx["next_cmd"]({"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}),
        immutable_objects=(e6.as_object(),),
        expected_head=head,
    )

    assert result.head.commit_seq == head.commit_seq + 1
    accepted = store.resolve_accepted(e6.ref, current_accepted_cut(store))
    assert accepted["body"]["stage_key"] == "E6"
    assert accepted["body"]["stop_e6_relationship"].startswith(E6_RELATIONSHIP_PROFILE + "|")


def test_e6_stage_spec_without_prior_accepted_stop_is_rejected_before_durability(tmp_path: Path) -> None:
    ctx = run_foundation_reference_slice(tmp_path / "e6_reject.sqlite", stop_at_seq=9)
    store = ctx["store"]
    head = store.head()
    assert head is not None

    forged = StageSpec(
        stage_key="E6",
        stage_spec_revision="e6-forged",
        stage_role="E6",
        stage_ordinal=6,
        purpose="forged E6",
        predecessor_requirements=("E5",),
        required_lane_slots=("E6_ADAPTIVE",),
        required_stage_completion_outputs=("POST_E6_GLOBAL_STOP_REEVALUATION",),
        coverage_obligation_policy_ref="BDB-REF-1:policy_revision:" + "1" * 64,
        transition_policy_ref="pin:initial_transition_profile_ref",
        stop_e6_relationship=(
            "BDB-E6-REL-1|stop=" + "1" * 64
            + "|source=" + "2" * 64
            + "|trust=" + "3" * 64
            + "|isolation=" + "4" * 64
            + "|level=STRICT"
        ),
    ).as_object()

    with pytest.raises(ValidationError, match="E6_REQUIRES_PRIOR_ACCEPTED_STOP"):
        ctx["coordinator"].accept(
            ctx["next_cmd"]({"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}),
            immutable_objects=(forged,),
            expected_head=head,
        )

    assert store.head() == head
    assert store.object_record(forged.digest) is None
