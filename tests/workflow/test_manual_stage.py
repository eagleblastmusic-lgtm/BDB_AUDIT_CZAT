"""Targeted tests for durable external E2+ phase transport."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from bdb_audit.adjudication.models import (
    FindingAdjudicationDecision,
    FindingAxisAssessment,
    FindingClaimRevision,
)
from bdb_audit.coordinator import Coordinator
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import deterministic_id
from bdb_audit.history.objects import CanonicalObject, CommandEnvelope
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.e2_checkpoint import E2BlindCheckpointService
from bdb_audit.workflow.e2_reveal import E2ControlledRevealService
from bdb_audit.workflow.e2_synthesis import E2MainSynthesisService
from bdb_audit.workflow.e2_shadow import E2ShadowAuthorizationService
from bdb_audit.workflow.e2_finalize import E2FinalizationService
from bdb_audit.workflow.e2_contradiction import (
    E2ContradictionAuthorizationService,
)
from bdb_audit.workflow.e2_contradiction_resolution import (
    E2ContradictionResolutionService,
)
from bdb_audit.workflow.e3_checkpoint import E3BlindCheckpointService
from bdb_audit.workflow.e3_gap import E3PositiveGapAuthorizationService
from bdb_audit.workflow.e3_gap_result import E3GapResultValidationService
from bdb_audit.workflow.e3_cumulative import E3CumulativeAuthorizationService
from bdb_audit.workflow.e3_cumulative_result import (
    E3CumulativeResultValidationService,
)
from bdb_audit.workflow.e3_holdout import E3HoldoutAuthorizationService
from bdb_audit.workflow.e3_holdout_result import (
    E3HoldoutResultValidationService,
)
from bdb_audit.workflow.manual_stage import (
    StageAssignmentService,
    StageIsolationProof,
    StageLaneDefinition,
    StageResultInbox,
    prepare_stage_phase_batch,
)
from bdb_audit.workflow.assignments import _command_id, _current_cut, _external_ref
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.read_models import current_accepted_cut
from bdb_audit.workflow.inbox import E1ResultInbox
from bdb_audit.workflow.packaging import prepare_e1_batch
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS


LANES = (
    StageLaneDefinition(
        "E2-CONVERGENCE",
        "Blind verification",
        "BLIND_VERIFY",
    ),
    StageLaneDefinition(
        "E2-ADJUDICATION",
        "Blind falsification",
        "BLIND_FALSIFY",
    ),
)

REVEAL_LANES = (
    StageLaneDefinition(
        "E2-CONVERGENCE",
        "Controlled claim convergence",
        "CONTROLLED_REVEAL_CONVERGENCE",
    ),
    StageLaneDefinition(
        "E2-ADJUDICATION",
        "Controlled claim adjudication",
        "CONTROLLED_REVEAL_ADJUDICATION",
    ),
)


@pytest.fixture
def e2_phase(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(
        store_path,
        seed="manual_stage_transport",
    )
    api.prepare_stage(store_path, "E1")
    api.qualify_stage(store_path, "E1")
    api.prepare_stage(store_path, "E2")
    for lane in LANES:
        api.prepare_lane(
            store_path,
            "E2",
            lane.lane_slot,
        )

    source = ResolvedSource(
        target_type="github",
        location=(
            "https://github.com/example/manual-stage"
        ),
        display_name="example/manual-stage",
        ref="main",
        exact_commit_sha="c" * 40,
    )
    store = TransactionalHistoryStore(store_path)
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=source,
        stage_id="E2",
        phase_id="E2-BLIND",
        lane_definitions=LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in LANES
        ],
    )
    inbox = StageResultInbox(store, batch)
    return store, batch, inbox, tmp_path


def _write_result(
    path: Path,
    batch,
    slot: str,
    **overrides,
) -> Path:
    job = batch.get_job(slot)
    body = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": batch.stage_id,
        "phase_id": batch.phase_id,
        "lane_slot": slot,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "input_package_digest": job.package_digest,
        "source_commit_sha": job.source_commit_sha,
        "history_cut": batch.frozen_history_cut,
        "assignment_ref": job.assignment_ref,
        "attempt_ref": job.attempt_ref,
        "findings": [],
        "outputs": {
            "verdict": "INCONCLUSIVE"
        },
    }
    body.update(overrides)
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "MANIFEST.json",
            json.dumps(body),
        )
        archive.writestr(
            "REPORT.md",
            "bounded external result",
        )
    return path


def test_phase_packages_share_exact_input_cut_and_distinct_assignments(
    e2_phase,
):
    _, batch, _, _ = e2_phase
    assert batch.stage_id == "E2"
    assert batch.phase_id == "E2-BLIND"
    assert set(batch.jobs) == {
        "E2-CONVERGENCE",
        "E2-ADJUDICATION",
    }
    cuts = {
        json.dumps(
            job.input_history_cut,
            sort_keys=True,
        )
        for job in batch.jobs.values()
    }
    assert len(cuts) == 1
    assignment_digests = {
        job.assignment_ref["revision_digest"]
        for job in batch.jobs.values()
    }
    assert len(assignment_digests) == 2
    for job in batch.jobs.values():
        assert job.package_zip_path.is_file()
        assert job.package_zip_path.with_suffix(
            ".zip.sha256"
        ).is_file()


def test_phase_inbox_accepts_order_independent_results_without_stage_completion(
    e2_phase,
):
    store, batch, inbox, tmp = e2_phase
    preexisting = len(
        store.accepted_records(
            "stage_completion",
            current_accepted_cut(store),
        )
    )
    paths = [
        _write_result(
            tmp / "adjudication.zip",
            batch,
            "E2-ADJUDICATION",
        ),
        _write_result(
            tmp / "convergence.zip",
            batch,
            "E2-CONVERGENCE",
        ),
    ]
    summary = inbox.ingest_multiple_zips(paths)
    assert summary.accepted_count == 2
    assert summary.phase_complete is True
    assert (
        summary.ready_for_stage_synthesis
        is True
    )
    assert summary.missing_lanes == []
    # Phase transport does not itself accept E2 StageCompletion.
    current = current_accepted_cut(store)
    assert len(
        store.accepted_records(
            "stage_completion", current
        )
    ) == preexisting


def test_wrong_phase_rejected(e2_phase):
    _, batch, inbox, tmp = e2_phase
    path = _write_result(
        tmp / "wrong-phase.zip",
        batch,
        "E2-CONVERGENCE",
        phase_id="E2-REVEAL",
    )
    _, status, reason = inbox.ingest_zip(path)
    assert status == "REJECTED"
    assert "WRONG_PHASE" in (reason or "")


def test_exact_retry_is_idempotent(e2_phase):
    store, batch, inbox, tmp = e2_phase
    path = _write_result(
        tmp / "retry.zip",
        batch,
        "E2-CONVERGENCE",
    )
    before = store.head().commit_seq
    assert inbox.ingest_zip(path)[1] == "ACCEPTED"
    after_first = store.head().commit_seq
    assert after_first > before
    assert inbox.ingest_zip(path)[1] == "ACCEPTED"
    assert store.head().commit_seq == after_first


def test_manual_e3_enforced_lane_blocks_phase_completion(
    tmp_path: Path,
):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(
        store_path,
        seed="manual_e3_isolation",
    )
    for stage in ("E1", "E2"):
        api.prepare_stage(store_path, stage)
        api.qualify_stage(store_path, stage)
    api.prepare_stage(store_path, "E3")
    api.prepare_lane(
        store_path,
        "E3",
        "E3-X",
    )

    store = TransactionalHistoryStore(store_path)
    source = ResolvedSource(
        target_type="github",
        location=(
            "https://github.com/example/manual-e3"
        ),
        display_name="example/manual-e3",
        ref="main",
        exact_commit_sha="d" * 40,
    )
    lane = StageLaneDefinition(
        "E3-X",
        "Security / authority / trust",
        "BLIND_NOVELTY",
    )
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=source,
        stage_id="E3",
        phase_id="E3-BLIND",
        lane_definitions=(lane,),
        all_stage_lane_slots=("E3-X",),
    )
    inbox = StageResultInbox(store, batch)
    path = _write_result(
        tmp_path / "e3.zip",
        batch,
        "E3-X",
    )
    summary = inbox.ingest_multiple_zips([path])
    assert summary.accepted_count == 1
    assert summary.phase_complete is False
    assert "PHASE_COMPLETION_BLOCKED" in (
        summary.error or ""
    )



def _prepare_e3_isolation_fixture(
    tmp_path: Path,
    *,
    seed: str,
):
    store_path = tmp_path / f"{seed}.sqlite"
    api = AuditOperationApi()
    api.create_campaign(
        store_path,
        seed=seed,
    )
    for stage in ("E1", "E2"):
        api.prepare_stage(store_path, stage)
        api.qualify_stage(store_path, stage)
    api.prepare_stage(store_path, "E3")
    api.prepare_lane(
        store_path,
        "E3",
        "E3-X",
    )
    store = TransactionalHistoryStore(store_path)
    source = ResolvedSource(
        target_type="github",
        location=(
            "https://github.com/example/e3-isolation"
        ),
        display_name="example/e3-isolation",
        ref="main",
        exact_commit_sha="d" * 40,
    )
    lane = StageLaneDefinition(
        "E3-X",
        "Security / authority / trust",
        "BLIND_NOVELTY",
    )
    cut = current_accepted_cut(store)
    source_generation = store.accepted_records(
        "source_generation",
        cut,
    )[-1]["ref"]
    return store, source, lane, source_generation


def test_e3_enforced_proof_requires_accepted_boundary_receipts(
    tmp_path: Path,
):
    store, source, lane, accepted_ref = (
        _prepare_e3_isolation_fixture(
            tmp_path,
            seed="e3_proof_missing_receipts",
        )
    )
    proof = StageIsolationProof(
        result="ENFORCED",
        channel_inventory_ref=accepted_ref,
    )
    with pytest.raises(
        ValidationError,
        match="ENFORCED_ISOLATION_RECEIPTS_REQUIRED",
    ):
        prepare_stage_phase_batch(
            store=store,
            output_dir=tmp_path / "proof-missing",
            source_info=source,
            stage_id="E3",
            phase_id="E3-BLIND",
            lane_definitions=(lane,),
            all_stage_lane_slots=("E3-X",),
            isolation_proofs_by_slot={
                "E3-X": proof,
            },
        )


def test_e3_declared_proof_cannot_satisfy_enforced_lane(
    tmp_path: Path,
):
    store, source, lane, accepted_ref = (
        _prepare_e3_isolation_fixture(
            tmp_path,
            seed="e3_declared_proof",
        )
    )
    proof = StageIsolationProof(
        result="DECLARED",
        channel_inventory_ref=accepted_ref,
        enforcement_receipt_refs=(
            accepted_ref,
        ),
        session_boundary_evidence_refs=(
            accepted_ref,
        ),
    )
    with pytest.raises(
        ValidationError,
        match="ISOLATION_PROOF_INSUFFICIENT",
    ):
        prepare_stage_phase_batch(
            store=store,
            output_dir=tmp_path / "proof-declared",
            source_info=source,
            stage_id="E3",
            phase_id="E3-BLIND",
            lane_definitions=(lane,),
            all_stage_lane_slots=("E3-X",),
            isolation_proofs_by_slot={
                "E3-X": proof,
            },
        )


def test_e3_accepted_enforced_proof_allows_lane_completion(
    tmp_path: Path,
):
    store, source, lane, accepted_ref = (
        _prepare_e3_isolation_fixture(
            tmp_path,
            seed="e3_enforced_proof",
        )
    )
    proof = StageIsolationProof(
        result="ENFORCED",
        channel_inventory_ref=accepted_ref,
        enforcement_receipt_refs=(
            accepted_ref,
        ),
        session_boundary_evidence_refs=(
            accepted_ref,
        ),
        scope="TEST_CONTROLLED_SESSION",
        reason_codes=(
            "TEST_ACCEPTED_BOUNDARY_RECEIPTS",
        ),
    )
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / "proof-enforced",
        source_info=source,
        stage_id="E3",
        phase_id="E3-BLIND",
        lane_definitions=(lane,),
        all_stage_lane_slots=("E3-X",),
        isolation_proofs_by_slot={
            "E3-X": proof,
        },
    )
    cut = current_accepted_cut(store)
    assignment = store.resolve_accepted(
        batch.get_job(
            "E3-X"
        ).assignment_ref,
        cut,
    )
    knowledge = store.resolve_accepted(
        assignment["body"]["knowledge_state_ref"],
        cut,
    )
    isolation = store.resolve_accepted(
        knowledge["body"][
            "isolation_qualification_ref"
        ],
        cut,
    )
    assert isolation["body"]["result"] == "ENFORCED"
    assert isolation["body"][
        "enforcement_receipt_refs"
    ]
    assert isolation["body"][
        "session_boundary_evidence_refs"
    ]

    inbox = StageResultInbox(
        store,
        batch,
    )
    path = _write_result(
        tmp_path / "e3-enforced-result.zip",
        batch,
        "E3-X",
    )
    summary = inbox.ingest_multiple_zips(
        [path]
    )
    assert summary.accepted_count == 1
    assert summary.phase_complete is True
    assert summary.error is None


def test_e3_enforced_proof_rejects_unaccepted_receipt(
    tmp_path: Path,
):
    store, source, lane, accepted_ref = (
        _prepare_e3_isolation_fixture(
            tmp_path,
            seed="e3_unaccepted_receipt",
        )
    )
    fake_ref = {
        **accepted_ref,
        "revision_digest": "f" * 64,
    }
    proof = StageIsolationProof(
        result="ENFORCED",
        channel_inventory_ref=accepted_ref,
        enforcement_receipt_refs=(
            fake_ref,
        ),
        session_boundary_evidence_refs=(
            accepted_ref,
        ),
    )
    with pytest.raises(
        ValidationError,
        match=(
            "OBJECT_NOT_ACCEPTED_AT_CUT"
            "|ACCEPTED_HISTORY_INTEGRITY_FAILURE"
        ),
    ):
        prepare_stage_phase_batch(
            store=store,
            output_dir=tmp_path / "proof-unaccepted",
            source_info=source,
            stage_id="E3",
            phase_id="E3-BLIND",
            lane_definitions=(lane,),
            all_stage_lane_slots=("E3-X",),
            isolation_proofs_by_slot={
                "E3-X": proof,
            },
        )




def _accept_scope_gap(
    store: TransactionalHistoryStore,
    *,
    scope_key: str = "runtime-unknown-surface",
):
    cut, prior_commit = _current_cut(store)
    obj = CanonicalObject(
        "scope_state_record",
        {
            "scope_state_record_id": (
                "scope_state_record_"
                + hashlib.sha256(
                    scope_key.encode("utf-8")
                ).hexdigest()[:32]
            ),
            "scope_key": scope_key,
            "state": "UNKNOWN_SCOPE",
            "basis_refs": [],
            "scope_state_input_history_cut": cut,
            "reason_codes": [
                "E3_GAP_TEST_UNKNOWN_SCOPE"
            ],
        },
    )
    head = store.head()
    assert head is not None
    command = CommandEnvelope(
        command_id=_command_id(
            "test_e3_scope_gap:" + obj.digest
        ),
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref=prior_commit.get(
            "actor_ref",
            "installation-owner",
        ),
        expected_parent_head={
            "tag": "ACCEPTED_HEAD_REF",
            **head.as_dict(),
        },
        governing_policy_ref=prior_commit[
            "governing_policy_ref"
        ],
        governing_spec_refs=tuple(
            prior_commit.get(
                "governing_spec_refs",
                (),
            )
        ),
        idempotency_scope=(
            "test_e3_scope_gap:" + obj.digest
        ),
        campaign_ref=head.campaign_id,
    )
    Coordinator(store).accept(
        command,
        immutable_objects=[obj],
        expected_head=head,
    )
    return obj.as_ref(
        ref_class="CONTENT_OR_PRIOR"
    ).as_dict()


def _prepare_e3_gap_fixture(
    tmp_path: Path,
    *,
    seed: str,
):
    store, source, blind_lane, accepted_ref = (
        _prepare_e3_isolation_fixture(
            tmp_path,
            seed=seed,
        )
    )
    proof = StageIsolationProof(
        result="ENFORCED",
        channel_inventory_ref=accepted_ref,
        enforcement_receipt_refs=(accepted_ref,),
        session_boundary_evidence_refs=(accepted_ref,),
        scope="TEST_CONTROLLED_SESSION",
        reason_codes=(
            "TEST_ACCEPTED_BOUNDARY_RECEIPTS",
        ),
    )
    blind_batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / f"{seed}-blind",
        source_info=source,
        stage_id="E3",
        phase_id="E3-BLIND",
        lane_definitions=(blind_lane,),
        all_stage_lane_slots=("E3-X",),
        isolation_proofs_by_slot={
            "E3-X": proof,
        },
    )
    blind_inbox = StageResultInbox(
        store,
        blind_batch,
    )
    blind_result = _write_result(
        tmp_path / f"{seed}-blind-result.zip",
        blind_batch,
        "E3-X",
        findings=[
            {
                "statement": "blind novelty precursor",
            }
        ],
    )
    imported = blind_inbox.ingest_multiple_zips(
        [blind_result]
    )
    assert imported.phase_complete is True
    E3BlindCheckpointService(
        store,
        blind_batch,
        blind_inbox,
    ).seal()
    scope_ref = _accept_scope_gap(store)

    gap_lane = StageLaneDefinition(
        "E3-X",
        "Security / authority / trust gap exploration",
        "AUTHORITY_TRUST_GAP_DIRECTED_SEARCH",
    )
    authorization = E3PositiveGapAuthorizationService(
        store,
        lane_definitions=(gap_lane,),
        all_stage_lane_slots=("E3-X",),
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
        isolation_proofs_by_slot={
            "E3-X": proof,
        },
    ).authorize()
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / f"{seed}-gap",
        source_info=source,
        stage_id="E3",
        phase_id="E3-GAP",
        lane_definitions=(gap_lane,),
        all_stage_lane_slots=("E3-X",),
        authorized_context=authorization,
        isolation_proofs_by_slot={
            "E3-X": proof,
        },
    )
    return (
        store,
        batch,
        authorization,
        scope_ref,
    )


def test_e3_positive_gap_view_is_grant_bound_and_excludes_finding_corpus(
    tmp_path: Path,
):
    store, batch, authorization, scope_ref = (
        _prepare_e3_gap_fixture(
            tmp_path,
            seed="e3_gap_positive_view",
        )
    )
    payload = json.loads(
        authorization.context_members[
            "E3_POSITIVE_GAP_VIEW.json"
        ].decode("utf-8")
    )
    assert (
        payload["format"]
        == "BDB-E3-POSITIVE-GAP-VIEW-1"
    )
    assert payload["explicit_scope_gaps"]
    raw = json.dumps(payload)
    assert "prior_finding_corpus" not in raw.lower()
    assert "producer_identity" not in raw.lower()

    job = batch.get_job("E3-X")
    assert job.view_manifest_ref
    assert job.grant_ref
    assert job.authorized_knowledge_state_ref
    assert (
        "E3 GAP-DIRECTED OUTPUT CONTRACT"
        in job.prompt_text
    )


def test_e3_gap_result_validation_requires_authorized_target_coverage(
    tmp_path: Path,
):
    store, batch, authorization, scope_ref = (
        _prepare_e3_gap_fixture(
            tmp_path,
            seed="e3_gap_result_validation",
        )
    )
    target_digest = scope_ref["revision_digest"]
    result_path = _write_result(
        tmp_path / "e3-gap-result.zip",
        batch,
        "E3-X",
        findings=[
            {
                "statement": (
                    "post-reveal observation on unknown scope"
                ),
                "classification": (
                    "POST_REVEAL_CONFIRMATION"
                ),
            }
        ],
        outputs={
            "gap_target_results": [
                {
                    "target_ref_digest": (
                        target_digest
                    ),
                    "target_kind": "SCOPE_GAP",
                    "status": "EXPLORED",
                    "rationale": (
                        "authorized gap inspected"
                    ),
                    "discovery_indexes": [0],
                }
            ]
        },
    )
    inbox = StageResultInbox(store, batch)
    imported = inbox.ingest_multiple_zips(
        [result_path]
    )
    assert imported.phase_complete is True

    summary = E3GapResultValidationService(
        store,
        batch,
        inbox,
    ).validate()
    assert summary.authorized_target_digests == (
        target_digest,
    )
    assert summary.covered_target_digests == (
        target_digest,
    )
    assert summary.findings_count == 1
    assert (
        summary.next_action
        == "PREPARE_E3_CUMULATIVE_CORPUS_REVEAL"
    )


def test_e3_gap_rejects_post_reveal_finding_mislabelled_as_blind(
    tmp_path: Path,
):
    store, batch, authorization, scope_ref = (
        _prepare_e3_gap_fixture(
            tmp_path,
            seed="e3_gap_mislabel",
        )
    )
    result_path = _write_result(
        tmp_path / "e3-gap-mislabel.zip",
        batch,
        "E3-X",
        findings=[
            {
                "statement": "revealed target discovery",
                "classification": (
                    "PRE_REVEAL_DISCOVERY"
                ),
            }
        ],
        outputs={
            "gap_target_results": [
                {
                    "target_ref_digest": (
                        scope_ref[
                            "revision_digest"
                        ]
                    ),
                    "target_kind": "SCOPE_GAP",
                    "status": "EXPLORED",
                    "rationale": "invalid label test",
                    "discovery_indexes": [0],
                }
            ]
        },
    )
    inbox = StageResultInbox(store, batch)
    imported = inbox.ingest_multiple_zips(
        [result_path]
    )
    assert imported.phase_complete is True
    with pytest.raises(
        ValidationError,
        match=(
            "POST_REVEAL_DISCOVERY_MISCLASSIFIED_AS_BLIND"
        ),
    ):
        E3GapResultValidationService(
            store,
            batch,
            inbox,
        ).validate()


def test_e3_gap_authorization_requires_fresh_isolation_proof(
    tmp_path: Path,
):
    store, source, blind_lane, accepted_ref = (
        _prepare_e3_isolation_fixture(
            tmp_path,
            seed="e3_gap_requires_proof",
        )
    )
    with pytest.raises(
        ValidationError,
        match="E3_GAP_ENFORCED_ISOLATION_PROOF_REQUIRED",
    ):
        E3PositiveGapAuthorizationService(
            store,
            lane_definitions=(
                StageLaneDefinition(
                    "E3-X",
                    "Gap search",
                    "GAP_DIRECTED",
                ),
            ),
            all_stage_lane_slots=("E3-X",),
            executor_profile="ChatGPT / GitHub",
            model="Sol 5.6",
            isolation_proofs_by_slot={},
        )




def _accept_prior_adjudicated_claim(
    store: TransactionalHistoryStore,
):
    cut, prior_commit = _current_cut(store)
    source_rows = store.accepted_records(
        "source_generation",
        cut,
    )
    assert len(source_rows) == 1
    source_ref = {
        **source_rows[0]["ref"],
        "ref_class": "CONTENT_OR_PRIOR",
    }
    claim = FindingClaimRevision(
        statement="Accepted prior E2 claim for cumulative comparison",
        source_generation_ref=source_ref,
        claim_id=deterministic_id(
            "finding_claim_revision",
            "test-e3-cumulative-prior-claim",
        ),
    )
    claim_obj = claim.as_object()
    claim_ref = claim_obj.as_ref(
        ref_class="CONTENT_OR_PRIOR"
    ).as_dict()
    policy_ref = _external_ref(
        "external_profile_ref",
        "TEST_E3_CUMULATIVE_AXIS_POLICY",
        "HISTORY_CONTEXT_BINDING",
    )
    axis_objects = {}
    for axis in (
        "MECHANISM",
        "REACHABILITY",
        "IMPACT",
        "SEVERITY",
    ):
        assessment = FindingAxisAssessment(
            claim_revision_ref=claim_ref,
            assessment_input_history_cut=cut,
            assessment_policy_ref=policy_ref,
            axis=axis,
            epistemic_outcome="INCONCLUSIVE",
            method="TEST_ACCEPTED_PRIOR_CORPUS",
            assessment_id=deterministic_id(
                "finding_axis_assessment",
                "test-e3-cumulative-" + axis,
            ),
        ).as_object()
        axis_objects[axis] = assessment

    adjudicator_ref = _external_ref(
        "actor_or_authority_ref",
        "TEST_TRUSTED_COORDINATOR",
        "CONTENT_OR_PRIOR",
    )
    decision = FindingAdjudicationDecision(
        claim_revision_ref=claim_ref,
        input_history_cut=cut,
        adjudicator_ref=adjudicator_ref,
        mechanism_assessment_ref=axis_objects[
            "MECHANISM"
        ].as_ref(
            ref_class="CONTENT_OR_PRIOR"
        ).as_dict(),
        reachability_assessment_ref=axis_objects[
            "REACHABILITY"
        ].as_ref(
            ref_class="CONTENT_OR_PRIOR"
        ).as_dict(),
        impact_assessment_ref=axis_objects[
            "IMPACT"
        ].as_ref(
            ref_class="CONTENT_OR_PRIOR"
        ).as_dict(),
        severity_assessment_ref=axis_objects[
            "SEVERITY"
        ].as_ref(
            ref_class="CONTENT_OR_PRIOR"
        ).as_dict(),
        lifecycle_status="OPEN",
        decision_id=deterministic_id(
            "finding_adjudication_decision",
            "test-e3-cumulative-prior-decision",
        ),
    ).as_object()

    objects = [
        claim_obj,
        *axis_objects.values(),
        decision,
    ]
    head = store.head()
    assert head is not None
    command = CommandEnvelope(
        command_id=_command_id(
            "test_e3_prior_corpus:"
            + decision.digest
        ),
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref=prior_commit.get(
            "actor_ref",
            "installation-owner",
        ),
        expected_parent_head={
            "tag": "ACCEPTED_HEAD_REF",
            **head.as_dict(),
        },
        governing_policy_ref=prior_commit[
            "governing_policy_ref"
        ],
        governing_spec_refs=tuple(
            prior_commit.get(
                "governing_spec_refs",
                (),
            )
        ),
        idempotency_scope=(
            "test_e3_prior_corpus:"
            + decision.digest
        ),
        campaign_ref=head.campaign_id,
    )
    Coordinator(store).accept(
        command,
        immutable_objects=objects,
        expected_head=head,
    )
    return claim_ref


def _prepare_e3_cumulative_fixture(
    tmp_path: Path,
    *,
    seed: str,
):
    (
        store,
        gap_batch,
        gap_authorization,
        scope_ref,
    ) = _prepare_e3_gap_fixture(
        tmp_path,
        seed=seed,
    )
    gap_result = _write_result(
        tmp_path / f"{seed}-gap-result.zip",
        gap_batch,
        "E3-X",
        findings=[
            {
                "statement": (
                    "post-reveal gap discovery"
                ),
                "classification": (
                    "POST_REVEAL_CONFIRMATION"
                ),
            }
        ],
        outputs={
            "gap_target_results": [
                {
                    "target_ref_digest": (
                        scope_ref[
                            "revision_digest"
                        ]
                    ),
                    "target_kind": "SCOPE_GAP",
                    "status": "EXPLORED",
                    "rationale": (
                        "gap target inspected"
                    ),
                    "discovery_indexes": [0],
                }
            ]
        },
    )
    gap_inbox = StageResultInbox(
        store,
        gap_batch,
    )
    imported = gap_inbox.ingest_multiple_zips(
        [gap_result]
    )
    assert imported.phase_complete is True
    gap_summary = E3GapResultValidationService(
        store,
        gap_batch,
        gap_inbox,
    ).validate()
    assert gap_summary.discovery_refs

    prior_claim_ref = (
        _accept_prior_adjudicated_claim(
            store
        )
    )
    cut = current_accepted_cut(store)
    accepted_ref = store.accepted_records(
        "source_generation",
        cut,
    )[0]["ref"]
    proof = StageIsolationProof(
        result="ENFORCED",
        channel_inventory_ref=accepted_ref,
        enforcement_receipt_refs=(
            accepted_ref,
        ),
        session_boundary_evidence_refs=(
            accepted_ref,
        ),
        scope="TEST_CONTROLLED_SESSION",
        reason_codes=(
            "TEST_ACCEPTED_BOUNDARY_RECEIPTS",
        ),
    )
    lane = StageLaneDefinition(
        "E3-X",
        "Cumulative corpus comparison",
        "CUMULATIVE_COMPARISON",
    )
    authorization = (
        E3CumulativeAuthorizationService(
            store,
            lane_definitions=(lane,),
            all_stage_lane_slots=("E3-X",),
            executor_profile="ChatGPT / GitHub",
            model="Sol 5.6",
            isolation_proofs_by_slot={
                "E3-X": proof,
            },
        ).authorize()
    )
    source = ResolvedSource(
        target_type="github",
        location=(
            "https://github.com/example/e3-isolation"
        ),
        display_name="example/e3-isolation",
        ref="main",
        exact_commit_sha="d" * 40,
    )
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / f"{seed}-cumulative",
        source_info=source,
        stage_id="E3",
        phase_id="E3-CUMULATIVE",
        lane_definitions=(lane,),
        all_stage_lane_slots=("E3-X",),
        authorized_context=authorization,
        isolation_proofs_by_slot={
            "E3-X": proof,
        },
    )
    return (
        store,
        batch,
        authorization,
        prior_claim_ref,
    )


def _cumulative_match_rows(
    authorization,
    prior_claim_ref,
):
    payload = json.loads(
        authorization.context_members[
            "E3_CUMULATIVE_CORPUS_VIEW.json"
        ].decode("utf-8")
    )
    rows = []
    for index, item in enumerate(
        payload["own_e3_discoveries"]
    ):
        rows.append(
            {
                "discovery_id": item[
                    "discovery_id"
                ],
                "relation": (
                    "MATCHED_PRIOR"
                    if index == 0
                    else "NO_PRIOR_MATCH"
                ),
                "matched_prior_claim_revision_digests": (
                    [
                        prior_claim_ref[
                            "revision_digest"
                        ]
                    ]
                    if index == 0
                    else []
                ),
                "rationale": (
                    "bounded comparison"
                ),
            }
        )
    return rows


def test_e3_cumulative_view_is_late_grant_bound_and_preserves_origin(
    tmp_path: Path,
):
    (
        store,
        batch,
        authorization,
        prior_claim_ref,
    ) = _prepare_e3_cumulative_fixture(
        tmp_path,
        seed="e3_cumulative_view",
    )
    payload = json.loads(
        authorization.context_members[
            "E3_CUMULATIVE_CORPUS_VIEW.json"
        ].decode("utf-8")
    )
    assert (
        payload["format"]
        == "BDB-E3-CUMULATIVE-CORPUS-VIEW-1"
    )
    assert payload[
        "own_e3_discoveries"
    ]
    assert payload[
        "prior_e1_e2_adjudicated_claims"
    ]
    origins = {
        item["origin_classification"]
        for item in payload[
            "own_e3_discoveries"
        ]
    }
    assert "PRE_REVEAL_DISCOVERY" in origins
    assert (
        "POST_REVEAL_CONFIRMATION"
        in origins
    )
    raw = json.dumps(payload).lower()
    assert "raw_report_path" not in raw
    assert "producer_identity" not in raw
    assert "support_count" not in raw

    job = batch.get_job("E3-X")
    assert job.grant_ref
    assert job.authorized_knowledge_state_ref
    assert (
        "E3 CUMULATIVE CORPUS OUTPUT CONTRACT"
        in job.prompt_text
    )


def test_e3_cumulative_result_exactly_covers_own_discoveries(
    tmp_path: Path,
):
    (
        store,
        batch,
        authorization,
        prior_claim_ref,
    ) = _prepare_e3_cumulative_fixture(
        tmp_path,
        seed="e3_cumulative_validate",
    )
    rows = _cumulative_match_rows(
        authorization,
        prior_claim_ref,
    )
    result_path = _write_result(
        tmp_path / "e3-cumulative-result.zip",
        batch,
        "E3-X",
        findings=[],
        outputs={
            "corpus_matches": rows,
        },
    )
    inbox = StageResultInbox(
        store,
        batch,
    )
    imported = inbox.ingest_multiple_zips(
        [result_path]
    )
    assert imported.phase_complete is True

    summary = (
        E3CumulativeResultValidationService(
            store,
            batch,
            inbox,
        ).validate()
    )
    assert (
        summary.comparison_count
        == len(rows)
    )
    assert summary.matched_discovery_ids
    assert summary.no_prior_match_discovery_ids
    assert (
        summary.next_action
        == "PREPARE_OPTIONAL_E3_HOLDOUT_OR_FINALIZE"
    )


def test_e3_cumulative_rejects_match_outside_authorized_view(
    tmp_path: Path,
):
    (
        store,
        batch,
        authorization,
        prior_claim_ref,
    ) = _prepare_e3_cumulative_fixture(
        tmp_path,
        seed="e3_cumulative_bad_match",
    )
    rows = _cumulative_match_rows(
        authorization,
        prior_claim_ref,
    )
    rows[0][
        "matched_prior_claim_revision_digests"
    ] = ["f" * 64]
    result_path = _write_result(
        tmp_path / "e3-cumulative-bad-match.zip",
        batch,
        "E3-X",
        outputs={
            "corpus_matches": rows,
        },
    )
    inbox = StageResultInbox(
        store,
        batch,
    )
    imported = inbox.ingest_multiple_zips(
        [result_path]
    )
    assert imported.phase_complete is True
    with pytest.raises(
        ValidationError,
        match=(
            "E3_CUMULATIVE_MATCH_OUTSIDE_AUTHORIZED_VIEW"
        ),
    ):
        E3CumulativeResultValidationService(
            store,
            batch,
            inbox,
        ).validate()


def test_e3_cumulative_new_finding_cannot_claim_blind_origin(
    tmp_path: Path,
):
    (
        store,
        batch,
        authorization,
        prior_claim_ref,
    ) = _prepare_e3_cumulative_fixture(
        tmp_path,
        seed="e3_cumulative_bad_origin",
    )
    rows = _cumulative_match_rows(
        authorization,
        prior_claim_ref,
    )
    result_path = _write_result(
        tmp_path / "e3-cumulative-bad-origin.zip",
        batch,
        "E3-X",
        findings=[
            {
                "statement": (
                    "late cumulative observation"
                ),
                "classification": (
                    "PRE_REVEAL_DISCOVERY"
                ),
            }
        ],
        outputs={
            "corpus_matches": rows,
        },
    )
    inbox = StageResultInbox(
        store,
        batch,
    )
    imported = inbox.ingest_multiple_zips(
        [result_path]
    )
    assert imported.phase_complete is True
    with pytest.raises(
        ValidationError,
        match=(
            "POST_REVEAL_DISCOVERY_MISCLASSIFIED_AS_BLIND"
        ),
    ):
        E3CumulativeResultValidationService(
            store,
            batch,
            inbox,
        ).validate()




def _accept_holdout_manifest(
    store: TransactionalHistoryStore,
    *,
    role: str = "AUXILIARY_HOLDOUT",
):
    cut, prior_commit = _current_cut(store)
    obj = CanonicalObject(
        "corpus_manifest",
        {
            "corpus_manifest_id": (
                "corpus_manifest_test_e3_holdout"
            ),
            "corpus_role": role,
            "snapshot_id": (
                "holdout_snapshot_test_001"
            ),
            "entries": [
                {
                    "locator": "entry-1",
                    "summary": (
                        "independent holdout mechanism"
                    ),
                },
                {
                    "locator": "entry-2",
                    "summary": (
                        "independent negative control"
                    ),
                },
            ],
        },
    )
    head = store.head()
    assert head is not None
    command = CommandEnvelope(
        command_id=_command_id(
            "test_e3_holdout_manifest:"
            + obj.digest
        ),
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref=prior_commit.get(
            "actor_ref",
            "installation-owner",
        ),
        expected_parent_head={
            "tag": "ACCEPTED_HEAD_REF",
            **head.as_dict(),
        },
        governing_policy_ref=prior_commit[
            "governing_policy_ref"
        ],
        governing_spec_refs=tuple(
            prior_commit.get(
                "governing_spec_refs",
                (),
            )
        ),
        idempotency_scope=(
            "test_e3_holdout_manifest:"
            + obj.digest
        ),
        campaign_ref=head.campaign_id,
    )
    Coordinator(store).accept(
        command,
        immutable_objects=[obj],
        expected_head=head,
    )
    return obj.as_ref(
        ref_class="CONTENT_OR_PRIOR"
    ).as_dict()


def _prepare_e3_holdout_fixture(
    tmp_path: Path,
    *,
    seed: str,
):
    (
        store,
        cumulative_batch,
        cumulative_authorization,
        prior_claim_ref,
    ) = _prepare_e3_cumulative_fixture(
        tmp_path,
        seed=seed,
    )
    cumulative_rows = _cumulative_match_rows(
        cumulative_authorization,
        prior_claim_ref,
    )
    cumulative_result = _write_result(
        tmp_path
        / f"{seed}-cumulative-result.zip",
        cumulative_batch,
        "E3-X",
        outputs={
            "corpus_matches": cumulative_rows,
        },
    )
    cumulative_inbox = StageResultInbox(
        store,
        cumulative_batch,
    )
    imported = (
        cumulative_inbox.ingest_multiple_zips(
            [cumulative_result]
        )
    )
    assert imported.phase_complete is True
    cumulative_summary = (
        E3CumulativeResultValidationService(
            store,
            cumulative_batch,
            cumulative_inbox,
        ).validate()
    )
    assert cumulative_summary.comparison_count

    holdout_ref = _accept_holdout_manifest(
        store
    )
    cut = current_accepted_cut(store)
    accepted_ref = store.accepted_records(
        "source_generation",
        cut,
    )[0]["ref"]
    proof = StageIsolationProof(
        result="ENFORCED",
        channel_inventory_ref=accepted_ref,
        enforcement_receipt_refs=(
            accepted_ref,
        ),
        session_boundary_evidence_refs=(
            accepted_ref,
        ),
        scope="TEST_CONTROLLED_SESSION",
        reason_codes=(
            "TEST_ACCEPTED_BOUNDARY_RECEIPTS",
        ),
    )
    lane = StageLaneDefinition(
        "E3-X",
        "External holdout comparison",
        "HOLDOUT_COMPARISON",
    )
    authorization = (
        E3HoldoutAuthorizationService(
            store,
            holdout_corpus_manifest_ref=(
                holdout_ref
            ),
            lane_definitions=(lane,),
            all_stage_lane_slots=("E3-X",),
            executor_profile=(
                "ChatGPT / GitHub"
            ),
            model="Sol 5.6",
            isolation_proofs_by_slot={
                "E3-X": proof,
            },
        ).authorize()
    )
    source = ResolvedSource(
        target_type="github",
        location=(
            "https://github.com/example/e3-isolation"
        ),
        display_name="example/e3-isolation",
        ref="main",
        exact_commit_sha="d" * 40,
    )
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=(
            tmp_path / f"{seed}-holdout"
        ),
        source_info=source,
        stage_id="E3",
        phase_id="E3-HOLDOUT",
        lane_definitions=(lane,),
        all_stage_lane_slots=("E3-X",),
        authorized_context=authorization,
        isolation_proofs_by_slot={
            "E3-X": proof,
        },
    )
    return (
        store,
        batch,
        authorization,
        holdout_ref,
        proof,
        lane,
    )


def _holdout_match_rows(
    authorization,
):
    payload = json.loads(
        authorization.context_members[
            "E3_EXTERNAL_HOLDOUT_VIEW.json"
        ].decode("utf-8")
    )
    rows = []
    for index, item in enumerate(
        payload["own_e3_discoveries"]
    ):
        rows.append(
            {
                "discovery_id": item[
                    "discovery_id"
                ],
                "relation": (
                    "MATCHED_HOLDOUT"
                    if index == 0
                    else "NO_HOLDOUT_MATCH"
                ),
                "matched_holdout_locators": (
                    ["entry-1"]
                    if index == 0
                    else []
                ),
                "rationale": (
                    "comparison relative to exact holdout"
                ),
            }
        )
    return rows


def test_e3_holdout_reveal_marks_exact_corpus_consumed(
    tmp_path: Path,
):
    (
        store,
        batch,
        authorization,
        holdout_ref,
        proof,
        lane,
    ) = _prepare_e3_holdout_fixture(
        tmp_path,
        seed="e3_holdout_consumed",
    )
    payload = json.loads(
        authorization.context_members[
            "E3_EXTERNAL_HOLDOUT_VIEW.json"
        ].decode("utf-8")
    )
    assert (
        payload["format"]
        == "BDB-E3-EXTERNAL-HOLDOUT-VIEW-1"
    )
    assert (
        payload["corpus_role"]
        == "AUXILIARY_HOLDOUT"
    )
    assert (
        payload[
            "holdout_corpus_manifest_ref"
        ]["revision_digest"]
        == holdout_ref["revision_digest"]
    )

    job = batch.get_job("E3-X")
    cut = current_accepted_cut(store)
    knowledge = store.resolve_accepted(
        job.authorized_knowledge_state_ref,
        cut,
    )
    assert (
        "CONSUMED_EXTERNAL_HOLDOUT"
        in knowledge["body"]["known_classes"]
    )
    assert (
        "E3 EXTERNAL HOLDOUT OUTPUT CONTRACT"
        in job.prompt_text
    )


def test_e3_holdout_result_is_comparison_not_false_negative_authority(
    tmp_path: Path,
):
    (
        store,
        batch,
        authorization,
        holdout_ref,
        proof,
        lane,
    ) = _prepare_e3_holdout_fixture(
        tmp_path,
        seed="e3_holdout_validate",
    )
    rows = _holdout_match_rows(
        authorization
    )
    result_path = _write_result(
        tmp_path / "e3-holdout-result.zip",
        batch,
        "E3-X",
        outputs={
            "holdout_matches": rows,
        },
    )
    inbox = StageResultInbox(
        store,
        batch,
    )
    imported = inbox.ingest_multiple_zips(
        [result_path]
    )
    assert imported.phase_complete is True

    summary = (
        E3HoldoutResultValidationService(
            store,
            batch,
            inbox,
        ).validate()
    )
    assert (
        summary.comparison_count
        == len(rows)
    )
    assert (
        summary.holdout_corpus_manifest_ref[
            "revision_digest"
        ]
        == holdout_ref["revision_digest"]
    )
    assert (
        summary.next_action
        == "ASSESS_HOLDOUT_RELATIONSHIPS_AND_E3_GATE"
    )

    cut = current_accepted_cut(store)
    # The comparison proposal itself does not create a canonical
    # false-negative relationship object.
    assert not [
        row
        for row in store.accepted_records(
            "blind_origin_eligibility_assessment",
            cut,
        )
        if row["body"].get(
            "classification"
        )
        == "MULTI_STAGE_FALSE_NEGATIVE"
    ]


def test_e3_holdout_authorization_retry_is_idempotent(
    tmp_path: Path,
):
    (
        store,
        batch,
        authorization,
        holdout_ref,
        proof,
        lane,
    ) = _prepare_e3_holdout_fixture(
        tmp_path,
        seed="e3_holdout_retry",
    )
    seq = store.head().commit_seq
    retry = E3HoldoutAuthorizationService(
        store,
        holdout_corpus_manifest_ref=(
            holdout_ref
        ),
        lane_definitions=(lane,),
        all_stage_lane_slots=("E3-X",),
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
        isolation_proofs_by_slot={
            "E3-X": proof,
        },
    ).authorize()
    assert retry.already_authorized is True
    assert store.head().commit_seq == seq
    assert (
        retry.view_manifest_ref
        == authorization.view_manifest_ref
    )


def test_e3_holdout_rejects_non_auxiliary_role(
    tmp_path: Path,
):
    (
        store,
        cumulative_batch,
        cumulative_authorization,
        prior_claim_ref,
    ) = _prepare_e3_cumulative_fixture(
        tmp_path,
        seed="e3_holdout_wrong_role",
    )
    cumulative_rows = _cumulative_match_rows(
        cumulative_authorization,
        prior_claim_ref,
    )
    cumulative_inbox = StageResultInbox(
        store,
        cumulative_batch,
    )
    imported = cumulative_inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp_path
                / "cumulative-wrong-role.zip",
                cumulative_batch,
                "E3-X",
                outputs={
                    "corpus_matches": (
                        cumulative_rows
                    )
                },
            )
        ]
    )
    assert imported.phase_complete is True
    E3CumulativeResultValidationService(
        store,
        cumulative_batch,
        cumulative_inbox,
    ).validate()

    wrong_ref = _accept_holdout_manifest(
        store,
        role="CANONICAL_PREDECESSOR",
    )
    cut = current_accepted_cut(store)
    accepted_ref = store.accepted_records(
        "source_generation",
        cut,
    )[0]["ref"]
    proof = StageIsolationProof(
        result="ENFORCED",
        channel_inventory_ref=accepted_ref,
        enforcement_receipt_refs=(
            accepted_ref,
        ),
        session_boundary_evidence_refs=(
            accepted_ref,
        ),
    )
    with pytest.raises(
        ValidationError,
        match="E3_HOLDOUT_ROLE_INVALID",
    ):
        E3HoldoutAuthorizationService(
            store,
            holdout_corpus_manifest_ref=(
                wrong_ref
            ),
            lane_definitions=(
                StageLaneDefinition(
                    "E3-X",
                    "Holdout",
                    "HOLDOUT",
                ),
            ),
            all_stage_lane_slots=("E3-X",),
            executor_profile=(
                "ChatGPT / GitHub"
            ),
            model="Sol 5.6",
            isolation_proofs_by_slot={
                "E3-X": proof,
            },
        ).authorize()


def test_unbound_context_members_fail_closed(e2_phase):
    store, _, _, tmp = e2_phase
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/manual-stage",
        display_name="example/manual-stage",
        ref="main",
        exact_commit_sha="c" * 40,
    )
    with pytest.raises(
        ValidationError,
        match="UNBOUND_STAGE_CONTEXT_FORBIDDEN",
    ):
        prepare_stage_phase_batch(
            store=store,
            output_dir=tmp / "work2",
            source_info=source,
            stage_id="E2",
            phase_id="E2-REVEAL",
            lane_definitions=LANES,
            all_stage_lane_slots=[
                lane.lane_slot for lane in LANES
            ],
            context_members={
                "prior_claims.json": b"{}"
            },
        )


def test_distinct_phase_does_not_reuse_blind_assignments(e2_phase):
    store, blind_batch, _, _ = e2_phase
    reveal_lanes = (
        StageLaneDefinition(
            "E2-CONVERGENCE",
            "Re-adjudication after controlled reveal",
            "REVEALED_REVIEW",
        ),
        StageLaneDefinition(
            "E2-ADJUDICATION",
            "Falsification after controlled reveal",
            "REVEALED_FALSIFY",
        ),
    )
    reveal = StageAssignmentService(
        store
    ).prepare_phase_assignments(
        stage_id="E2",
        phase_id="E2-REVEAL",
        lane_definitions=reveal_lanes,
        all_stage_lane_slots=[
            lane.lane_slot for lane in LANES
        ],
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    )
    assert reveal.phase_id == "E2-REVEAL"
    for slot, assignment in reveal.assignments.items():
        assert (
            assignment.assignment_ref["revision_digest"]
            != blind_batch.get_job(slot).assignment_ref["revision_digest"]
        )


def test_e2_blind_checkpoint_seals_both_lanes_on_one_cut(e2_phase):
    store, batch, inbox, tmp = e2_phase
    paths = [
        _write_result(
            tmp / "convergence-checkpoint.zip",
            batch,
            "E2-CONVERGENCE",
            findings=[
                {
                    "finding_id": "e2-conv-1",
                    "statement": "Independent blind precursor finding",
                }
            ],
        ),
        _write_result(
            tmp / "adjudication-checkpoint.zip",
            batch,
            "E2-ADJUDICATION",
            findings=[],
        ),
    ]
    imported = inbox.ingest_multiple_zips(paths)
    assert imported.phase_complete is True

    before = store.head().commit_seq
    summary = E2BlindCheckpointService(
        store,
        batch,
        inbox,
    ).seal()
    assert summary.already_sealed is False
    assert set(summary.checkpoint_refs) == {
        "E2-CONVERGENCE",
        "E2-ADJUDICATION",
    }
    assert summary.accepted_commit_seq == before + 1

    cut = current_accepted_cut(store)
    rows = [
        row
        for row in store.accepted_records("checkpoint", cut)
        if row["body"].get("phase_id") == "E2-BLIND"
    ]
    assert len(rows) == 2
    assert {row["accepted_seq"] for row in rows} == {
        summary.accepted_commit_seq
    }
    convergence = next(
        row
        for row in rows
        if row["body"].get("lane_slot") == "E2-CONVERGENCE"
    )
    kinds = {
        ref["kind"]
        for ref in convergence["body"]["sealed_output_refs"]
    }
    assert "bdb_audit_lane_result" in kinds
    assert "discovery_record" in kinds


def test_e2_blind_checkpoint_retry_is_idempotent(e2_phase):
    store, batch, inbox, tmp = e2_phase
    inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "convergence-retry.zip",
                batch,
                "E2-CONVERGENCE",
            ),
            _write_result(
                tmp / "adjudication-retry.zip",
                batch,
                "E2-ADJUDICATION",
            ),
        ]
    )
    service = E2BlindCheckpointService(store, batch, inbox)
    first = service.seal()
    seq = store.head().commit_seq
    second = service.seal()
    assert second.already_sealed is True
    assert store.head().commit_seq == seq
    assert second.checkpoint_refs == first.checkpoint_refs


def test_e2_blind_checkpoint_rejects_incomplete_phase(e2_phase):
    store, batch, inbox, tmp = e2_phase
    inbox.ingest_zip(
        _write_result(
            tmp / "only-convergence.zip",
            batch,
            "E2-CONVERGENCE",
        )
    )
    with pytest.raises(
        ValidationError,
        match="E2_BLIND_PHASE_NOT_COMPLETE",
    ):
        E2BlindCheckpointService(
            store,
            batch,
            inbox,
        ).seal()


def _write_e1_result(path: Path, batch, slot: str) -> Path:
    job = batch.get_job(slot)
    body = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": slot,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "input_package_digest": job.package_digest,
        "source_commit_sha": job.source_commit_sha,
        "history_cut": batch.frozen_history_cut,
        "assignment_ref": job.assignment_ref,
        "attempt_ref": job.attempt_ref,
        "findings": [
            {
                "finding_id": f"{slot}-finding",
                "statement": f"Claim discovered by {slot}",
                "mechanism": "bounded mechanism",
                "location": "src/example.py",
                "severity": "CRITICAL",
                "support_count": 99,
                "producer_identity": "SHOULD_NOT_REVEAL",
                "raw_report_path": "/secret/report.md",
            }
        ],
    }
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("MANIFEST.json", json.dumps(body))
    return path


@pytest.fixture
def e2_reveal_flow(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(
        store_path,
        seed="e2_reveal_flow",
    )
    api.prepare_stage(store_path, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(store_path, "E1", slot)

    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/e2-reveal",
        display_name="example/e2-reveal",
        ref="main",
        exact_commit_sha="e" * 40,
    )
    store = TransactionalHistoryStore(store_path)
    e1_batch = prepare_e1_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=source,
    )
    e1_inbox = E1ResultInbox(store, e1_batch)
    e1_summary = e1_inbox.ingest_multiple_zips(
        [
            _write_e1_result(
                tmp_path / f"{slot}.zip",
                e1_batch,
                slot,
            )
            for slot in E1_LANE_SLOTS
        ]
    )
    assert e1_summary.stage_complete is True

    api.prepare_stage(store_path, "E2")
    for lane in LANES:
        api.prepare_lane(
            store_path,
            "E2",
            lane.lane_slot,
        )

    blind_batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=source,
        stage_id="E2",
        phase_id="E2-BLIND",
        lane_definitions=LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in LANES
        ],
    )
    blind_inbox = StageResultInbox(
        store,
        blind_batch,
    )
    blind_summary = blind_inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp_path / "blind-convergence.zip",
                blind_batch,
                "E2-CONVERGENCE",
                findings=[
                    {
                        "finding_id": "blind-c1",
                        "statement": "blind independent discovery",
                    }
                ],
            ),
            _write_result(
                tmp_path / "blind-adjudication.zip",
                blind_batch,
                "E2-ADJUDICATION",
            ),
        ]
    )
    assert blind_summary.phase_complete is True
    checkpoint = E2BlindCheckpointService(
        store,
        blind_batch,
        blind_inbox,
    ).seal()
    return {
        "store": store,
        "source": source,
        "blind_batch": blind_batch,
        "blind_inbox": blind_inbox,
        "checkpoint": checkpoint,
        "tmp": tmp_path,
    }


def test_e2_controlled_reveal_authorized_before_package_delivery(
    e2_reveal_flow,
):
    store = e2_reveal_flow["store"]
    source = e2_reveal_flow["source"]
    tmp = e2_reveal_flow["tmp"]

    authorization = E2ControlledRevealService(
        store,
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()

    assert authorization.phase_id == "E2-REVEAL"
    assert set(authorization.grant_refs_by_slot) == {
        "E2-CONVERGENCE",
        "E2-ADJUDICATION",
    }
    payload = json.loads(
        authorization.context_members[
            "E1_CLAIM_VIEW.json"
        ].decode("utf-8")
    )
    assert payload["format"] == "BDB-E2-POSITIVE-CLAIM-VIEW-1"
    assert payload["claims"]
    encoded = json.dumps(payload)
    assert "severity" not in encoded
    assert "support_count" not in encoded
    assert "producer_identity" not in encoded
    assert "raw_report_path" not in encoded

    seq_before_publish = store.head().commit_seq
    reveal_batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp / "work",
        source_info=source,
        stage_id="E2",
        phase_id="E2-REVEAL",
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        authorized_context=authorization,
    )
    # Package publication is a transport write only; accepted grant/history
    # existed first and publication does not advance canonical history.
    assert store.head().commit_seq == seq_before_publish

    for slot, job in reveal_batch.jobs.items():
        assert job.grant_ref == authorization.grant_refs_by_slot[slot]
        assert (
            job.authorized_knowledge_state_ref
            == authorization.knowledge_state_refs_by_slot[slot]
        )
        with zipfile.ZipFile(job.package_zip_path, "r") as archive:
            names = set(archive.namelist())
            assert "CONTEXT/E1_CLAIM_VIEW.json" in names
            manifest = json.loads(
                archive.read("MANIFEST.json")
            )
        assert manifest["context_authorization"]["grant_ref"] == job.grant_ref
        assert manifest["context_manifest"] == authorization.context_manifest


def test_e2_reveal_result_completion_uses_authorized_knowledge_state(
    e2_reveal_flow,
):
    store = e2_reveal_flow["store"]
    source = e2_reveal_flow["source"]
    tmp = e2_reveal_flow["tmp"]
    authorization = E2ControlledRevealService(
        store,
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()
    reveal_batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp / "work",
        source_info=source,
        stage_id="E2",
        phase_id="E2-REVEAL",
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        authorized_context=authorization,
    )
    inbox = StageResultInbox(store, reveal_batch)
    path = _write_result(
        tmp / "reveal-convergence.zip",
        reveal_batch,
        "E2-CONVERGENCE",
    )
    assert inbox.ingest_zip(path)[1] == "ACCEPTED"

    cut = current_accepted_cut(store)
    result = next(
        row
        for row in store.accepted_records(
            "bdb_audit_lane_result",
            cut,
        )
        if row["body"].get("phase_id") == "E2-REVEAL"
        and row["body"].get("lane_slot") == "E2-CONVERGENCE"
    )
    completion = next(
        row
        for row in store.accepted_records(
            "lane_completion",
            cut,
        )
        if any(
            ref.get("revision_digest")
            == result["ref"]["revision_digest"]
            for ref in row["body"].get(
                "required_output_refs", []
            )
        )
    )
    assert (
        completion["body"][
            "final_knowledge_state_ref"
        ]["revision_digest"]
        == authorization.knowledge_state_refs_by_slot[
            "E2-CONVERGENCE"
        ]["revision_digest"]
    )


def test_e2_reveal_authorization_retry_is_idempotent(
    e2_reveal_flow,
):
    store = e2_reveal_flow["store"]
    kwargs = {
        "lane_definitions": REVEAL_LANES,
        "all_stage_lane_slots": [
            lane.lane_slot for lane in REVEAL_LANES
        ],
        "executor_profile": "ChatGPT / GitHub",
        "model": "Sol 5.6",
    }
    first = E2ControlledRevealService(
        store,
        **kwargs,
    ).authorize()
    seq = store.head().commit_seq
    second = E2ControlledRevealService(
        store,
        **kwargs,
    ).authorize()
    assert second.already_authorized is True
    assert store.head().commit_seq == seq
    assert second.view_manifest_ref == first.view_manifest_ref
    assert second.grant_refs_by_slot == first.grant_refs_by_slot


def test_reveal_package_without_authorization_fails_closed(e2_phase):
    store, _, _, tmp = e2_phase
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/manual-stage",
        display_name="example/manual-stage",
        ref="main",
        exact_commit_sha="c" * 40,
    )
    with pytest.raises(
        ValidationError,
        match="STAGE_REVEAL_AUTHORIZATION_REQUIRED",
    ):
        prepare_stage_phase_batch(
            store=store,
            output_dir=tmp / "work-reveal-denied",
            source_info=source,
            stage_id="E2",
            phase_id="E2-REVEAL",
            lane_definitions=REVEAL_LANES,
            all_stage_lane_slots=[
                lane.lane_slot for lane in REVEAL_LANES
            ],
        )


def _reveal_assessments_from_authorization(authorization, outcome="INCONCLUSIVE"):
    payload = json.loads(
        authorization.context_members[
            "E1_CLAIM_VIEW.json"
        ].decode("utf-8")
    )
    return [
        {
            "opaque_claim_view_id": item["opaque_claim_view_id"],
            "claim_outcome": outcome,
            "axis_outcomes": {
                "MECHANISM": outcome,
                "REACHABILITY": outcome,
                "IMPACT": outcome,
                "SEVERITY": outcome,
            },
            "rationale": "bounded external proposal",
        }
        for item in payload["claims"]
    ]


def test_e2_main_synthesis_is_individual_and_evidence_fail_closed(
    e2_reveal_flow,
):
    store = e2_reveal_flow["store"]
    source = e2_reveal_flow["source"]
    tmp = e2_reveal_flow["tmp"]
    authorization = E2ControlledRevealService(
        store,
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()
    reveal_batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp / "work",
        source_info=source,
        stage_id="E2",
        phase_id="E2-REVEAL",
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        authorized_context=authorization,
    )
    assessments = _reveal_assessments_from_authorization(
        authorization,
        outcome="SUPPORTED",
    )
    reveal_inbox = StageResultInbox(
        store,
        reveal_batch,
    )
    imported = reveal_inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "reveal-main-convergence.zip",
                reveal_batch,
                "E2-CONVERGENCE",
                outputs={
                    "claim_assessments": assessments
                },
            ),
            _write_result(
                tmp / "reveal-main-adjudication.zip",
                reveal_batch,
                "E2-ADJUDICATION",
                outputs={
                    "claim_assessments": assessments
                },
            ),
        ]
    )
    assert imported.phase_complete is True

    before = store.head().commit_seq
    synthesis = E2MainSynthesisService(
        store,
        reveal_batch,
        reveal_inbox,
    ).synthesize()
    assert synthesis.accepted_commit_seq == before + 1
    assert len(synthesis.claim_refs) == len(assessments)
    assert len(
        synthesis.adjudication_decision_refs
    ) == len(assessments)

    cut = current_accepted_cut(store)
    decisions = [
        row
        for row in store.accepted_records(
            "finding_adjudication_decision",
            cut,
        )
        if row["body"].get("decision_id")
        in {
            store.resolve_accepted(ref, cut)["body"]["decision_id"]
            for ref in synthesis.adjudication_decision_refs.values()
        }
    ]
    assert len(decisions) == len(assessments)
    assert {
        row["body"]["lifecycle_status"]
        for row in decisions
    } == {"OPEN"}

    axis_rows = [
        store.resolve_accepted(ref, cut)["body"]
        for axes in synthesis.axis_assessment_refs.values()
        for ref in axes.values()
    ]
    # External SUPPORTED proposals are not canonical qualified evidence.
    assert {
        row["epistemic_outcome"]
        for row in axis_rows
    } == {"INCONCLUSIVE"}
    assert all(
        row["evidence_qualification_refs"] == []
        for row in axis_rows
    )
    assert all(
        "NO_QUALIFIED_EVIDENCE" in row["method"]
        for row in axis_rows
    )
    # Main synthesis deliberately does not finalize E2.
    e2_stage_completion = [
        row
        for row in store.accepted_records(
            "stage_completion",
            cut,
        )
        if store.resolve_accepted(
            row["body"]["stage_spec_ref"],
            cut,
        )["body"].get("stage_key") == "E2"
    ]
    assert e2_stage_completion == []


def test_e2_main_synthesis_rejects_missing_claim_assessment(
    e2_reveal_flow,
):
    store = e2_reveal_flow["store"]
    source = e2_reveal_flow["source"]
    tmp = e2_reveal_flow["tmp"]
    authorization = E2ControlledRevealService(
        store,
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()
    reveal_batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp / "work-missing",
        source_info=source,
        stage_id="E2",
        phase_id="E2-REVEAL",
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        authorized_context=authorization,
    )
    assessments = _reveal_assessments_from_authorization(
        authorization,
    )
    reveal_inbox = StageResultInbox(store, reveal_batch)
    reveal_inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "reveal-missing-convergence.zip",
                reveal_batch,
                "E2-CONVERGENCE",
                outputs={
                    "claim_assessments": assessments
                },
            ),
            _write_result(
                tmp / "reveal-missing-adjudication.zip",
                reveal_batch,
                "E2-ADJUDICATION",
                outputs={
                    "claim_assessments": assessments[:-1]
                },
            ),
        ]
    )
    with pytest.raises(
        ValidationError,
        match="E2_REVEAL_ASSESSMENT_INCOMPLETE",
    ):
        E2MainSynthesisService(
            store,
            reveal_batch,
            reveal_inbox,
        ).synthesize()


def test_e2_main_synthesis_records_proposal_disagreement(
    e2_reveal_flow,
):
    store = e2_reveal_flow["store"]
    source = e2_reveal_flow["source"]
    tmp = e2_reveal_flow["tmp"]
    authorization = E2ControlledRevealService(
        store,
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()
    reveal_batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp / "work-disagree",
        source_info=source,
        stage_id="E2",
        phase_id="E2-REVEAL",
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        authorized_context=authorization,
    )
    supports = _reveal_assessments_from_authorization(
        authorization,
        outcome="SUPPORTED",
    )
    refutes = _reveal_assessments_from_authorization(
        authorization,
        outcome="REFUTED",
    )
    reveal_inbox = StageResultInbox(store, reveal_batch)
    reveal_inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "reveal-disagree-convergence.zip",
                reveal_batch,
                "E2-CONVERGENCE",
                outputs={
                    "claim_assessments": supports
                },
            ),
            _write_result(
                tmp / "reveal-disagree-adjudication.zip",
                reveal_batch,
                "E2-ADJUDICATION",
                outputs={
                    "claim_assessments": refutes
                },
            ),
        ]
    )
    synthesis = E2MainSynthesisService(
        store,
        reveal_batch,
        reveal_inbox,
    ).synthesize()
    assert set(
        synthesis.proposal_disagreement_claim_ids
    ) == {
        item["opaque_claim_view_id"]
        for item in supports
    }


@pytest.fixture
def e2_shadow_flow(e2_reveal_flow):
    store = e2_reveal_flow["store"]
    source = e2_reveal_flow["source"]
    tmp = e2_reveal_flow["tmp"]
    authorization = E2ControlledRevealService(
        store,
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()
    reveal_batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp / "shadow-work",
        source_info=source,
        stage_id="E2",
        phase_id="E2-REVEAL",
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        authorized_context=authorization,
    )
    assessments = _reveal_assessments_from_authorization(
        authorization,
    )
    reveal_inbox = StageResultInbox(
        store,
        reveal_batch,
    )
    summary = reveal_inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "shadow-prep-convergence.zip",
                reveal_batch,
                "E2-CONVERGENCE",
                outputs={
                    "claim_assessments": assessments
                },
            ),
            _write_result(
                tmp / "shadow-prep-adjudication.zip",
                reveal_batch,
                "E2-ADJUDICATION",
                outputs={
                    "claim_assessments": assessments
                },
            ),
        ]
    )
    assert summary.phase_complete is True
    synthesis = E2MainSynthesisService(
        store,
        reveal_batch,
        reveal_inbox,
    ).synthesize()
    shadow_lane = StageLaneDefinition(
        "E2-ADJUDICATION",
        "Independent bounded shadow adjudicator",
        "INDEPENDENT_SHADOW_ADJUDICATION",
    )
    shadow_authorization = E2ShadowAuthorizationService(
        store,
        lane_definition=shadow_lane,
        all_stage_lane_slots=(
            "E2-CONVERGENCE",
            "E2-ADJUDICATION",
        ),
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()
    shadow_batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp / "shadow-work",
        source_info=source,
        stage_id="E2",
        phase_id="E2-SHADOW",
        lane_definitions=(shadow_lane,),
        all_stage_lane_slots=(
            "E2-CONVERGENCE",
            "E2-ADJUDICATION",
        ),
        authorized_context=shadow_authorization,
    )
    return {
        **e2_reveal_flow,
        "reveal_authorization": authorization,
        "reveal_batch": reveal_batch,
        "synthesis": synthesis,
        "shadow_authorization": shadow_authorization,
        "shadow_batch": shadow_batch,
    }


def test_e2_shadow_view_is_bounded_and_granted_before_delivery(
    e2_shadow_flow,
):
    store = e2_shadow_flow["store"]
    authorization = e2_shadow_flow[
        "shadow_authorization"
    ]
    batch = e2_shadow_flow["shadow_batch"]
    payload = json.loads(
        authorization.context_members[
            "E2_MAIN_ADJUDICATION_VIEW.json"
        ].decode("utf-8")
    )
    assert payload["format"] == "BDB-E2-SHADOW-VIEW-1"
    assert payload["claims"]
    raw = json.dumps(payload)
    assert "raw_report_path" not in raw
    assert "producer_identity" not in raw
    assert "support_count" not in raw
    assert "prior_popularity" not in raw

    job = batch.get_job("E2-ADJUDICATION")
    assert job.grant_ref == authorization.grant_refs_by_slot[
        "E2-ADJUDICATION"
    ]
    assert job.authorized_knowledge_state_ref == (
        authorization.knowledge_state_refs_by_slot[
            "E2-ADJUDICATION"
        ]
    )
    assert "E2 INDEPENDENT SHADOW OUTPUT CONTRACT" in job.prompt_text
    with zipfile.ZipFile(job.package_zip_path, "r") as archive:
        manifest = json.loads(
            archive.read("MANIFEST.json")
        )
        assert (
            "CONTEXT/E2_MAIN_ADJUDICATION_VIEW.json"
            in set(archive.namelist())
        )
    assert manifest["context_authorization"]["grant_ref"] == job.grant_ref

    cut = current_accepted_cut(store)
    store.resolve_accepted(
        job.grant_ref,
        cut,
    )
    store.resolve_accepted(
        job.authorized_knowledge_state_ref,
        cut,
    )


def test_e2_shadow_result_uses_authorized_shadow_knowledge(
    e2_shadow_flow,
):
    store = e2_shadow_flow["store"]
    batch = e2_shadow_flow["shadow_batch"]
    authorization = e2_shadow_flow[
        "shadow_authorization"
    ]
    tmp = e2_shadow_flow["tmp"]
    payload = json.loads(
        authorization.context_members[
            "E2_MAIN_ADJUDICATION_VIEW.json"
        ].decode("utf-8")
    )
    checks = [
        {
            "claim_revision_digest": item[
                "claim_revision_ref"
            ]["revision_digest"],
            "conflict": False,
            "conflict_types": [],
            "rationale": "no bounded conflict found",
        }
        for item in payload["claims"]
    ]
    inbox = StageResultInbox(store, batch)
    result_path = _write_result(
        tmp / "shadow-result.zip",
        batch,
        "E2-ADJUDICATION",
        outputs={
            "shadow_checks": checks
        },
    )
    assert inbox.ingest_zip(result_path)[1] == "ACCEPTED"
    cut = current_accepted_cut(store)
    result = next(
        row
        for row in store.accepted_records(
            "bdb_audit_lane_result",
            cut,
        )
        if row["body"].get("phase_id") == "E2-SHADOW"
    )
    completion = next(
        row
        for row in store.accepted_records(
            "lane_completion",
            cut,
        )
        if any(
            ref.get("revision_digest")
            == result["ref"]["revision_digest"]
            for ref in row["body"].get(
                "required_output_refs",
                [],
            )
        )
    )
    assert (
        completion["body"]["final_knowledge_state_ref"][
            "revision_digest"
        ]
        == authorization.knowledge_state_refs_by_slot[
            "E2-ADJUDICATION"
        ]["revision_digest"]
    )


def _shadow_checks(authorization, conflict=False):
    payload = json.loads(
        authorization.context_members[
            "E2_MAIN_ADJUDICATION_VIEW.json"
        ].decode("utf-8")
    )
    return [
        {
            "claim_revision_digest": item[
                "claim_revision_ref"
            ]["revision_digest"],
            "conflict": conflict,
            "conflict_types": (
                ["EVIDENCE_OVERSTATING"]
                if conflict
                else []
            ),
            "rationale": (
                "bounded challenge"
                if conflict
                else "no bounded conflict found"
            ),
        }
        for item in payload["claims"]
    ]


def test_e2_finalization_accepts_stage_completion_only_after_clean_shadow(
    e2_shadow_flow,
):
    store = e2_shadow_flow["store"]
    batch = e2_shadow_flow["shadow_batch"]
    authorization = e2_shadow_flow[
        "shadow_authorization"
    ]
    tmp = e2_shadow_flow["tmp"]
    inbox = StageResultInbox(store, batch)
    imported = inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "shadow-clean-final.zip",
                batch,
                "E2-ADJUDICATION",
                outputs={
                    "shadow_checks": _shadow_checks(
                        authorization,
                        conflict=False,
                    )
                },
            )
        ]
    )
    assert imported.phase_complete is True

    before = store.head().commit_seq
    result = E2FinalizationService(
        store,
        batch,
        inbox,
    ).finalize()
    assert result.stage_completed is True
    assert result.stage_completion_ref is not None
    assert result.accepted_commit_seq == before + 1
    assert result.next_action == "PREPARE_E3"

    status = AuditOperationApi().get_campaign_status(
        store.path
    )
    assert "E2" in status["stages_completed"]

    cut = current_accepted_cut(store)
    stage_completion = store.resolve_accepted(
        result.stage_completion_ref,
        cut,
    )
    assert (
        stage_completion["body"][
            "completion_predicate_result"
        ]
        == "STAGE_COMPLETED"
    )
    assert (
        stage_completion["body"][
            "mandatory_obligation_summary"
        ]["shadow_conflicts"]
        == 0
    )

    # Retry is read-only/idempotent.
    seq = store.head().commit_seq
    retry = E2FinalizationService(
        store,
        batch,
        inbox,
    ).finalize()
    assert retry.already_finalized is True
    assert store.head().commit_seq == seq


def test_e2_finalization_conflict_requires_contradiction_protocol(
    e2_shadow_flow,
):
    store = e2_shadow_flow["store"]
    batch = e2_shadow_flow["shadow_batch"]
    authorization = e2_shadow_flow[
        "shadow_authorization"
    ]
    tmp = e2_shadow_flow["tmp"]
    inbox = StageResultInbox(store, batch)
    checks = _shadow_checks(
        authorization,
        conflict=False,
    )
    checks[0] = {
        **checks[0],
        "conflict": True,
        "conflict_types": [
            "EVIDENCE_OVERSTATING"
        ],
        "rationale": "shadow challenges main evidence restraint",
    }
    imported = inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "shadow-conflict-final.zip",
                batch,
                "E2-ADJUDICATION",
                outputs={
                    "shadow_checks": checks
                },
            )
        ]
    )
    assert imported.phase_complete is True
    seq = store.head().commit_seq

    result = E2FinalizationService(
        store,
        batch,
        inbox,
    ).finalize()
    assert result.stage_completed is False
    assert result.stage_completion_ref is None
    assert result.shadow_conflict_claim_digests
    assert result.contradiction_refs
    assert (
        result.next_action
        == "E2_CONTRADICTION_PROTOCOL_REQUIRED"
    )
    # The conflict is no longer ephemeral: one atomic commit records the
    # shadow challenge claim(s) and canonical ContradictionRevision case(s).
    assert store.head().commit_seq == seq + 1

    cut = current_accepted_cut(store)
    for ref in result.contradiction_refs:
        contradiction = store.resolve_accepted(
            ref,
            cut,
        )
        assert contradiction["body"]["status"] == "OPEN"
        assert len(
            contradiction["body"]["claim_revision_refs"]
        ) == 2
        assert (
            contradiction["body"][
                "opposing_evidence_qualification_refs"
            ]
            == []
        )

    # Retry is idempotent and reuses the same accepted contradiction set.
    committed_seq = store.head().commit_seq
    retry = E2FinalizationService(
        store,
        batch,
        inbox,
    ).finalize()
    assert retry.already_finalized is True
    assert retry.contradiction_refs == result.contradiction_refs
    assert store.head().commit_seq == committed_seq

    status = AuditOperationApi().get_campaign_status(
        store.path
    )
    assert "E2" not in status["stages_completed"]


@pytest.fixture
def e2_contradiction_flow(e2_shadow_flow):
    store = e2_shadow_flow["store"]
    shadow_batch = e2_shadow_flow["shadow_batch"]
    shadow_authorization = e2_shadow_flow[
        "shadow_authorization"
    ]
    source = e2_shadow_flow["source"]
    tmp = e2_shadow_flow["tmp"]

    shadow_inbox = StageResultInbox(
        store,
        shadow_batch,
    )
    imported = shadow_inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "shadow-all-conflicts.zip",
                shadow_batch,
                "E2-ADJUDICATION",
                outputs={
                    "shadow_checks": _shadow_checks(
                        shadow_authorization,
                        conflict=True,
                    )
                },
            )
        ]
    )
    assert imported.phase_complete is True
    finalization = E2FinalizationService(
        store,
        shadow_batch,
        shadow_inbox,
    ).finalize()
    assert finalization.stage_completed is False
    assert finalization.contradiction_refs

    contradiction_lane = StageLaneDefinition(
        "E2-ADJUDICATION",
        "Scoped contradiction protocol adjudicator",
        "CONTRADICTION_PROTOCOL",
    )
    authorization = E2ContradictionAuthorizationService(
        store,
        contradiction_refs=finalization.contradiction_refs,
        lane_definition=contradiction_lane,
        all_stage_lane_slots=(
            "E2-CONVERGENCE",
            "E2-ADJUDICATION",
        ),
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp / "contradiction-work",
        source_info=source,
        stage_id="E2",
        phase_id="E2-CONTRADICTION",
        lane_definitions=(contradiction_lane,),
        all_stage_lane_slots=(
            "E2-CONVERGENCE",
            "E2-ADJUDICATION",
        ),
        authorized_context=authorization,
    )
    return {
        **e2_shadow_flow,
        "shadow_inbox": shadow_inbox,
        "shadow_finalization": finalization,
        "contradiction_authorization": authorization,
        "contradiction_batch": batch,
    }


def _contradiction_resolutions(
    authorization,
    *,
    blocked=False,
):
    payload = json.loads(
        authorization.context_members[
            "E2_CONTRADICTION_CASES.json"
        ].decode("utf-8")
    )
    rows = []
    for item in payload["contradictions"]:
        ref = item["contradiction_revision_ref"]
        rows.append(
            {
                "contradiction_revision_digest": ref[
                    "revision_digest"
                ],
                "resolution_kind": (
                    "BLOCKED"
                    if blocked
                    else "REFUTED"
                ),
                "resulting_status": (
                    "BLOCKED"
                    if blocked
                    else "RESOLVED_FULL"
                ),
                "resolved_scope": dict(
                    item["scope"]
                ),
                "basis_ref_digests": [
                    ref["revision_digest"]
                ],
                "rationale": (
                    "authorized evidence is insufficient"
                    if blocked
                    else "bounded contradiction falsifier resolves the case"
                ),
            }
        )
    return rows


def test_e2_contradiction_view_is_grant_bound_and_bounded(
    e2_contradiction_flow,
):
    authorization = e2_contradiction_flow[
        "contradiction_authorization"
    ]
    batch = e2_contradiction_flow[
        "contradiction_batch"
    ]
    payload = json.loads(
        authorization.context_members[
            "E2_CONTRADICTION_CASES.json"
        ].decode("utf-8")
    )
    assert (
        payload["format"]
        == "BDB-E2-CONTRADICTION-PROTOCOL-VIEW-1"
    )
    assert payload["contradictions"]
    raw = json.dumps(payload)
    assert "raw_report_path" not in raw
    assert "producer_identity" not in raw
    assert "support_count" not in raw
    assert "prior_popularity" not in raw

    job = batch.get_job("E2-ADJUDICATION")
    assert job.grant_ref == authorization.grant_refs_by_slot[
        "E2-ADJUDICATION"
    ]
    assert (
        "E2 CONTRADICTION PROTOCOL OUTPUT CONTRACT"
        in job.prompt_text
    )
    with zipfile.ZipFile(
        job.package_zip_path,
        "r",
    ) as archive:
        names = set(archive.namelist())
        assert (
            "CONTEXT/E2_CONTRADICTION_CASES.json"
            in names
        )
        manifest = json.loads(
            archive.read("MANIFEST.json")
        )
    assert (
        manifest["context_authorization"]["grant_ref"]
        == job.grant_ref
    )


def test_e2_contradiction_resolution_uses_two_commit_dag_and_completes_e2(
    e2_contradiction_flow,
):
    store = e2_contradiction_flow["store"]
    batch = e2_contradiction_flow[
        "contradiction_batch"
    ]
    authorization = e2_contradiction_flow[
        "contradiction_authorization"
    ]
    tmp = e2_contradiction_flow["tmp"]
    inbox = StageResultInbox(store, batch)
    imported = inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "contradiction-resolved.zip",
                batch,
                "E2-ADJUDICATION",
                outputs={
                    "contradiction_resolutions": (
                        _contradiction_resolutions(
                            authorization,
                            blocked=False,
                        )
                    )
                },
            )
        ]
    )
    assert imported.phase_complete is True

    before = store.head().commit_seq
    result = E2ContradictionResolutionService(
        store,
        batch,
        inbox,
    ).resolve()
    assert result.stage_completed is True
    assert result.stage_completion_ref is not None
    # Decision commit -> successor contradiction commit -> StageCompletion.
    assert result.decision_commit_seq == before + 1
    assert result.successor_commit_seq == before + 2
    assert (
        result.stage_completion_commit_seq
        == before + 3
    )
    assert set(
        result.resulting_status_by_prior_digest.values()
    ) == {"RESOLVED_FULL"}

    cut = current_accepted_cut(store)
    for ref in result.successor_contradiction_refs:
        successor = store.resolve_accepted(
            ref,
            cut,
        )
        assert (
            successor["body"]["status"]
            == "RESOLVED_FULL"
        )
        assert (
            successor["body"][
                "predecessor_contradiction_revision_ref"
            ]["ref_class"]
            == "PRIOR_ACCEPTED_ONLY"
        )
        assert (
            successor["body"][
                "resolution_decision_ref"
            ]["ref_class"]
            == "PRIOR_ACCEPTED_ONLY"
        )

    status = AuditOperationApi().get_campaign_status(
        store.path
    )
    assert "E2" in status["stages_completed"]

    seq = store.head().commit_seq
    retry = E2ContradictionResolutionService(
        store,
        batch,
        inbox,
    ).resolve()
    assert retry.already_resolved is True
    assert store.head().commit_seq == seq


def test_e2_contradiction_blocked_resolution_keeps_stage_incomplete(
    e2_contradiction_flow,
):
    store = e2_contradiction_flow["store"]
    batch = e2_contradiction_flow[
        "contradiction_batch"
    ]
    authorization = e2_contradiction_flow[
        "contradiction_authorization"
    ]
    tmp = e2_contradiction_flow["tmp"]
    inbox = StageResultInbox(store, batch)
    imported = inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "contradiction-blocked.zip",
                batch,
                "E2-ADJUDICATION",
                outputs={
                    "contradiction_resolutions": (
                        _contradiction_resolutions(
                            authorization,
                            blocked=True,
                        )
                    )
                },
            )
        ]
    )
    assert imported.phase_complete is True

    result = E2ContradictionResolutionService(
        store,
        batch,
        inbox,
    ).resolve()
    assert result.stage_completed is False
    assert result.stage_completion_ref is None
    assert (
        result.next_action
        == "E2_CONTRADICTION_REMAINS_BLOCKING"
    )
    assert set(
        result.resulting_status_by_prior_digest.values()
    ) == {"BLOCKED"}

    status = AuditOperationApi().get_campaign_status(
        store.path
    )
    assert "E2" not in status["stages_completed"]


def test_e2_contradiction_rejects_basis_outside_authorized_view(
    e2_contradiction_flow,
):
    store = e2_contradiction_flow["store"]
    batch = e2_contradiction_flow[
        "contradiction_batch"
    ]
    authorization = e2_contradiction_flow[
        "contradiction_authorization"
    ]
    tmp = e2_contradiction_flow["tmp"]
    resolutions = _contradiction_resolutions(
        authorization,
        blocked=False,
    )
    resolutions[0]["basis_ref_digests"] = [
        "f" * 64
    ]
    inbox = StageResultInbox(store, batch)
    inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "contradiction-bad-basis.zip",
                batch,
                "E2-ADJUDICATION",
                outputs={
                    "contradiction_resolutions": (
                        resolutions
                    )
                },
            )
        ]
    )
    with pytest.raises(
        ValidationError,
        match="E2_CONTRADICTION_BASIS_OUTSIDE_VIEW",
    ):
        E2ContradictionResolutionService(
            store,
            batch,
            inbox,
        ).resolve()


@pytest.mark.parametrize(
    "phase_id",
    ["E2-SHADOW", "E2-CONTRADICTION"],
)
def test_controlled_e2_context_phase_without_authorization_fails_closed(
    e2_phase,
    phase_id,
):
    store, _, _, tmp = e2_phase
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/manual-stage",
        display_name="example/manual-stage",
        ref="main",
        exact_commit_sha="c" * 40,
    )
    lanes = (
        StageLaneDefinition(
            "E2-ADJUDICATION",
            "Controlled phase",
            "CONTROLLED_CONTEXT",
        ),
    )
    with pytest.raises(
        ValidationError,
        match="STAGE_CONTEXT_AUTHORIZATION_REQUIRED",
    ):
        prepare_stage_phase_batch(
            store=store,
            output_dir=tmp / (
                "work-ungranted-"
                + phase_id.lower()
            ),
            source_info=source,
            stage_id="E2",
            phase_id=phase_id,
            lane_definitions=lanes,
            all_stage_lane_slots=(
                "E2-CONVERGENCE",
                "E2-ADJUDICATION",
            ),
        )
