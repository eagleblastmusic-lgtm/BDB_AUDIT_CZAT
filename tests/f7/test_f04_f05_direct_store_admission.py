"""Direct real-store regressions for STOP freshness and challenger closure.

The raw append helper is used only to set up an internally consistent prior
accepted-history fixture. Every result under test goes through Coordinator.accept.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import uuid

import pytest

from bdb_audit.assurance.conclusion import CampaignConclusion, FinalAssuranceCase
from bdb_audit.assurance.finalization_service import FinalizationService
from bdb_audit.assurance.release import ReleaseQualification
from bdb_audit.coordinator import Coordinator
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id
from bdb_audit.core.registry import canonical_reference_set
from bdb_audit.history.objects import CanonicalObject, CommandEnvelope
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.stop.evaluator import evaluate_stop
from bdb_audit.stop.models import StopInput
from bdb_audit.workflow.read_models import current_accepted_cut
from tests.f7.test_adaptive_e6_canonical_authority import _append_raw_commit


def _typed_ref(kind: str, token: str, ref_class: str = "HISTORY_CONTEXT_BINDING") -> dict:
    return {
        "kind": kind,
        "revision_digest": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": (
            "BDB_TARGET/external_profile_ref"
            if kind == "external_profile_ref"
            else f"BDB_SCHEMA_REGISTRY::{kind}/1"
        ),
        "ref_class": ref_class,
    }


def _seed_store_with_stop(
    tmp_path: Path,
    *,
    roles: tuple[str, str] = ("FALSE_POSITIVE_SKEPTIC", "FALSE_NEGATIVE_HUNTER"),
    challenger_candidate: str = "current",
):
    store_path = tmp_path / f"{uuid.uuid4().hex}.sqlite"
    AuditOperationApi().create_campaign(store_path, seed="f04-f05-store-admission")
    store = TransactionalHistoryStore(store_path)
    cut = current_accepted_cut(store)
    source = store.accepted_records("source_generation", cut)[0]
    inventory_ref = _typed_ref("inventory_revision", "inventory-fixture")

    if challenger_candidate == "foreign":
        foreign = CanonicalObject("candidate_assurance_case", {"fixture": "foreign"})
        foreign_ref = foreign.as_ref().as_dict()
        foreign_assignments = []
        foreign_results = []
        for position, role in enumerate(
            ("FALSE_POSITIVE_SKEPTIC", "FALSE_NEGATIVE_HUNTER")
        ):
            assignment = CanonicalObject(
                "challenger_assignment",
                {
                    "candidate_assurance_case_ref": foreign_ref,
                    "challenger_type": role,
                },
            )
            result = CanonicalObject(
                "challenger_result",
                {
                    "candidate_assurance_case_ref": foreign_ref,
                    "challenge_assignment_ref": assignment.as_ref().as_dict(),
                    "status": "NO_MATERIAL_COUNTEREVIDENCE",
                },
            )
            foreign_assignments.append(assignment)
            foreign_results.append(result)
        _append_raw_commit(store, [foreign, *foreign_assignments, *foreign_results], index=21)

    candidate = CanonicalObject(
        "candidate_assurance_case", {"fixture": "current"}
    )
    candidate_ref = candidate.as_ref().as_dict()
    objects = [candidate]
    result_refs_by_role = {}
    for position, role in enumerate(roles):
        bound_candidate_ref = candidate_ref
        if challenger_candidate == "foreign":
            foreign_records = store.accepted_records(
                "challenger_result", current_accepted_cut(store)
            )
            foreign_assignments = store.accepted_records(
                "challenger_assignment", current_accepted_cut(store)
            )
            foreign_by_role = {
                row["body"]["challenger_type"]: row
                for row in foreign_assignments
            }
            foreign_result = next(
                row
                for row in foreign_records
                if row["body"].get("challenge_assignment_ref", {}).get(
                    "revision_digest"
                )
                == foreign_by_role[role]["ref"]["revision_digest"]
            )
            result_refs_by_role[role] = foreign_result["ref"]
            continue
        assignment = CanonicalObject(
            "challenger_assignment",
                {
                    "candidate_assurance_case_ref": bound_candidate_ref,
                    "challenger_type": role,
                    "fixture_position": position,
                },
        )
        result = CanonicalObject(
            "challenger_result",
            {
                "candidate_assurance_case_ref": bound_candidate_ref,
                    "challenge_assignment_ref": assignment.as_ref().as_dict(),
                    "status": "NO_MATERIAL_COUNTEREVIDENCE",
                    "fixture_position": position,
                },
        )
        objects.extend((assignment, result))
        result_refs_by_role[role] = result.as_ref().as_dict()

    _append_raw_commit(store, objects, index=22 if challenger_candidate == "foreign" else 21)

    # An independently accepted but unlisted result makes the extra-ref
    # admission case test the exact STOP set comparison, not object lookup.
    extra_assignment = CanonicalObject(
        "challenger_assignment",
        {
            "candidate_assurance_case_ref": candidate_ref,
            "challenger_type": "UNEXPECTED_REVIEWER",
        },
    )
    extra_result = CanonicalObject(
        "challenger_result",
        {
            "candidate_assurance_case_ref": candidate_ref,
            "challenge_assignment_ref": extra_assignment.as_ref().as_dict(),
            "status": "NO_MATERIAL_COUNTEREVIDENCE",
        },
    )
    _append_raw_commit(store, [extra_assignment, extra_result], index=23)

    cut = current_accepted_cut(store)
    release_policy_ref = FinalizationService._policy_ref_from_cut(cut)
    selected_roles = list(roles)
    challenger_refs = [result_refs_by_role[role] for role in selected_roles]
    stop_input = StopInput(
        campaign_id=cut["campaign_id"],
        source_generation_ref=source["ref"],
        input_history_cut=cut,
        evaluation_context="FINAL_POST_E5",
        governing_policy_ref=release_policy_ref,
        policy_spec_refs=(release_policy_ref,),
        evaluator_revision_ref=_typed_ref("external_profile_ref", "stop-evaluator"),
        required_stage_set_ref=_typed_ref("external_profile_ref", "e1-e5-stage-set"),
        required_stage_spec_refs=(),
        completed_stage_refs=(),
        pending_required_stage_refs=(),
        stop_input_snapshot_ref=_typed_ref("snapshot", "stop-snapshot"),
        inventory_revision_ref=inventory_ref,
        mandatory_obligation_refs=(),
        current_obligation_qualification_refs=(),
        evidence_invalidation_refs=(),
        contradiction_refs=(),
        residual_risk_refs=(),
        evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=release_policy_ref,
        effort_profile_ref=_typed_ref("external_profile_ref", "effort-profile"),
        effort_results_ref={"rounds_executed": 1},
        unknown_blocked_summary={
            "unknown_surfaces_count": 0,
            "is_blocked": False,
            "challenger_binding_verified": True,
            "challenger_blocked_count": 0,
            "challenger_inconclusive_count": 0,
            "challenger_material_counterevidence_count": 0,
            "qualification_binding_verified": True,
            "unqualified_mandatory_obligations_count": 0,
        },
        candidate_assurance_case_ref=candidate_ref,
        challenger_refs=challenger_refs,
    )
    stop_eval = evaluate_stop(stop_input, insufficient_data=False)
    assert stop_eval.continuation_decision == "PASS"
    assert stop_eval.release_readiness == "READY"
    _append_raw_commit(
        store,
        [stop_input.as_object(), stop_eval.as_object()],
        index=24,
    )
    return {
        "store": store,
        "store_path": store_path,
        "source_ref": source["ref"],
        "inventory_ref": inventory_ref,
        "candidate_ref": candidate_ref,
        "challenger_refs": challenger_refs,
        "extra_challenger_ref": extra_result.as_ref().as_dict(),
        "stop_input": stop_input,
        "stop_eval": stop_eval,
    }


def _command(store: TransactionalHistoryStore, label: str) -> CommandEnvelope:
    head = store.head()
    assert head is not None
    prior = store.commits()[-1]
    return CommandEnvelope(
        command_id=f"command_{uuid.uuid4()}",
        command_kind="RECORD_ASSURANCE_DECISION",
        actor_ref=prior["actor_ref"],
        expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
        governing_policy_ref=prior["governing_policy_ref"],
        governing_spec_refs=tuple(prior["governing_spec_refs"]),
        idempotency_scope=f"{label}:{uuid.uuid4().hex}",
        campaign_ref=head.campaign_id,
    )


def _conclusion(basis: dict, *, statement: str = "Store admission regression") -> CanonicalObject:
    store = basis["store"]
    head = store.head()
    assert head is not None
    body = CampaignConclusion(
        campaign_conclusion_id=new_id("campaign_conclusion"),
        campaign_ref={
            "kind": "campaign_ref",
            "revision_digest": hashlib.sha256(head.campaign_id.encode()).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_TARGET/campaign_ref",
            "ref_class": "PRIOR_ACCEPTED_ONLY",
        },
        source_generation_ref=dict(basis["source_ref"], ref_class="PRIOR_ACCEPTED_ONLY"),
        stop_evaluation_ref=basis["stop_eval"].as_object().as_ref(
            ref_class="PRIOR_ACCEPTED_ONLY"
        ).as_dict(),
        termination_state="COMPLETED",
        assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
        bounded_conclusion_statement=statement,
        conclusion_command_input_history_cut=current_accepted_cut(store),
        candidate_assurance_case_ref=dict(
            basis["candidate_ref"], ref_class="PRIOR_ACCEPTED_ONLY"
        ),
    )
    return CanonicalObject(
        "campaign_conclusion", body.body(), logical_id=body.campaign_conclusion_id
    )


def _final_case(basis: dict, conclusion_ref: dict, *, challenger_refs=None) -> CanonicalObject:
    store = basis["store"]
    model = FinalAssuranceCase(
        final_assurance_case_id=new_id("final_assurance_case"),
        campaign_conclusion_ref=dict(conclusion_ref, ref_class="PRIOR_ACCEPTED_ONLY"),
        stop_evaluation_ref=basis["stop_eval"].as_object().as_ref(
            ref_class="PRIOR_ACCEPTED_ONLY"
        ).as_dict(),
        public_conclusion_statement_ref=_typed_ref(
            "public_conclusion_statement_ref",
            "store-admission-public-statement",
            "PRIOR_ACCEPTED_ONLY",
        ),
        final_case_input_history_cut=current_accepted_cut(store),
        candidate_assurance_case_ref=dict(
            basis["candidate_ref"], ref_class="PRIOR_ACCEPTED_ONLY"
        ),
        challenger_result_refs=tuple(
            canonical_reference_set(
                [
                    dict(ref, ref_class="PRIOR_ACCEPTED_ONLY")
                    for ref in (
                        basis["challenger_refs"]
                        if challenger_refs is None
                        else challenger_refs
                    )
                ]
            )
        ),
    )
    return CanonicalObject(
        "final_assurance_case", model.body(), logical_id=model.final_assurance_case_id
    )


def _accept(store: TransactionalHistoryStore, obj: CanonicalObject, label: str):
    head = store.head()
    assert head is not None
    return Coordinator(store).accept(
        _command(store, label),
        immutable_objects=[obj],
        expected_head=head,
    )


def test_stop_freshness_is_enforced_in_direct_base_and_release_admission(
    tmp_path: Path,
) -> None:
    basis = _seed_store_with_stop(tmp_path)
    store = basis["store"]

    conclusion = _conclusion(basis)
    _accept(store, conclusion, "fresh-conclusion")
    cut = current_accepted_cut(store)
    final_case = _final_case(basis, conclusion.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict())
    _accept(store, final_case, "fresh-final-case")

    successor = CanonicalObject(
        "candidate_assurance_case", {"fixture": "material-successor-after-stop"}
    )
    _append_raw_commit(store, [successor], index=25)

    stale_conclusion = _conclusion(basis, statement="stale direct conclusion")
    head_before = store.head()
    count_before = len(store.commits())
    with pytest.raises(ValidationError, match="STOP_INPUT_CUT_MISMATCH"):
        Coordinator(store).accept(
            _command(store, "stale-base-finalizer"),
            immutable_objects=[stale_conclusion],
            expected_head=head_before,
        )
    assert store.head() == head_before
    assert len(store.commits()) == count_before
    assert store.object_record(stale_conclusion.digest) is None

    release_cut = current_accepted_cut(store)
    qualification_model = ReleaseQualification(
        release_qualification_id=new_id("release_qualification"),
        campaign_conclusion_ref=conclusion.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
        final_assurance_case_ref=final_case.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
        stop_evaluation_ref=basis["stop_eval"].as_object().as_ref(
            ref_class="PRIOR_ACCEPTED_ONLY"
        ).as_dict(),
        source_generation_ref=dict(basis["source_ref"], ref_class="PRIOR_ACCEPTED_ONLY"),
        release_policy_ref=FinalizationService._policy_ref_from_cut(release_cut),
        release_assessment_basis_cut=release_cut,
        qualification_command_input_history_cut=release_cut,
        assessment_basis="STOP_AXIS_MATERIALIZATION",
        result="READY",
    )
    stale_release = CanonicalObject(
        "release_qualification",
        qualification_model.body(),
        logical_id=qualification_model.release_qualification_id,
    )
    head_before = store.head()
    count_before = len(store.commits())
    with pytest.raises(ValidationError, match="STOP_INPUT_CUT_MISMATCH"):
        Coordinator(store).accept(
            _command(store, "stale-release-finalizer"),
            immutable_objects=[stale_release],
            expected_head=head_before,
        )
    assert store.head() == head_before
    assert len(store.commits()) == count_before
    assert store.object_record(stale_release.digest) is None


def test_administrative_history_after_stop_does_not_stale_direct_finalization(
    tmp_path: Path,
) -> None:
    basis = _seed_store_with_stop(tmp_path)
    store = basis["store"]
    admin_eval = evaluate_stop(basis["stop_input"], insufficient_data=False)
    _accept(store, admin_eval.as_object(), "administrative-stop-replay")

    conclusion = _conclusion(basis, statement="admin-only successor remains current")
    head_before = store.head()
    accepted = Coordinator(store).accept(
        _command(store, "admin-positive-control"),
        immutable_objects=[conclusion],
        expected_head=head_before,
    )
    assert accepted.head.commit_seq == head_before.commit_seq + 1
    assert store.object_record(conclusion.digest) is not None


def test_stop_freshness_admission_guard_is_mutation_sensitive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    basis = _seed_store_with_stop(tmp_path)
    store = basis["store"]
    _append_raw_commit(
        store,
        [CanonicalObject("candidate_assurance_case", {"fixture": "stale-successor"})],
        index=25,
    )
    stale_conclusion = _conclusion(basis, statement="stale guard mutation control")

    with pytest.raises(ValidationError, match="STOP_INPUT_CUT_MISMATCH"):
        _accept(store, stale_conclusion, "freshness-guard-enabled")

    # Controlled deletion of the shared freshness predicate: a stale STOP
    # would otherwise be accepted by the canonical Coordinator path.
    from bdb_audit.stop import operation as stop_operation

    monkeypatch.setattr(
        stop_operation,
        "_require_material_stop_basis_current",
        lambda *_args, **_kwargs: None,
    )
    accepted = _accept(store, stale_conclusion, "freshness-guard-bypassed")
    assert accepted.head.commit_seq == store.head().commit_seq
    assert store.object_record(stale_conclusion.digest) is not None


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("missing", "FINALIZATION_BINDING_CONFLICT"),
        ("extra", "FINALIZATION_BINDING_CONFLICT"),
        ("wrong_role", "FINALIZATION_CHALLENGER_MISMATCH"),
        ("wrong_candidate", "FINALIZATION_CHALLENGER_MISMATCH"),
        ("exact", "ACCEPT"),
    ],
)
def test_direct_final_assurance_admission_requires_exact_challenger_closure(
    tmp_path: Path,
    case: str,
    expected_code: str,
) -> None:
    if case == "wrong_role":
        basis = _seed_store_with_stop(
            tmp_path,
            roles=("FALSE_POSITIVE_SKEPTIC", "UNEXPECTED_REVIEWER"),
        )
    elif case == "wrong_candidate":
        basis = _seed_store_with_stop(tmp_path, challenger_candidate="foreign")
    else:
        basis = _seed_store_with_stop(tmp_path)
    store = basis["store"]

    # The conclusion is prior accepted history. The test target is the final
    # assurance admission gate, which independently rechecks the STOP closure.
    conclusion = _conclusion(basis)
    _append_raw_commit(store, [conclusion], index=31)
    refs = list(basis["challenger_refs"])
    if case == "missing":
        refs = []
    elif case == "extra":
        refs.append(basis["extra_challenger_ref"])
    final_case = _final_case(
        basis,
        conclusion.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
        challenger_refs=refs,
    )
    head_before = store.head()
    count_before = len(store.commits())

    if case == "exact":
        accepted = Coordinator(store).accept(
            _command(store, "exact-challenger-set"),
            immutable_objects=[final_case],
            expected_head=head_before,
        )
        assert accepted.head.commit_seq == head_before.commit_seq + 1
        assert store.object_record(final_case.digest) is not None
    else:
        with pytest.raises(ValidationError) as exc:
            Coordinator(store).accept(
                _command(store, f"challenger-{case}"),
                immutable_objects=[final_case],
                expected_head=head_before,
            )
        assert exc.value.code == expected_code
        assert store.head() == head_before
        assert len(store.commits()) == count_before
        assert store.object_record(final_case.digest) is None


def test_full_challenger_closure_guard_is_mutation_sensitive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    basis = _seed_store_with_stop(
        tmp_path,
        roles=("FALSE_POSITIVE_SKEPTIC", "UNEXPECTED_REVIEWER"),
    )
    store = basis["store"]
    conclusion = _conclusion(basis, statement="challenger mutation control")
    _append_raw_commit(store, [conclusion], index=31)
    final_case = _final_case(
        basis,
        conclusion.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
    )

    with pytest.raises(ValidationError, match="FINALIZATION_CHALLENGER_MISMATCH"):
        _accept(store, final_case, "challenger-guard-enabled")

    # The ref set still exactly matches STOP; only the role-closure predicate
    # rejects it. This bypass confirms that the direct admission regression is
    # sensitive to removal of that canonical semantic guard.
    from bdb_audit.history import authority_hooks

    monkeypatch.setattr(
        authority_hooks,
        "_validate_full_challenger_closure",
        lambda *_args, **_kwargs: None,
    )
    accepted = _accept(store, final_case, "challenger-guard-bypassed")
    assert accepted.head.commit_seq == store.head().commit_seq
    assert store.object_record(final_case.digest) is not None


@pytest.mark.parametrize(
    ("crash_at", "partial_counts"),
    [
        ("campaign_conclusion", (0, 0, 0)),
        ("final_assurance_case", (1, 0, 0)),
        ("release_qualification", (1, 1, 0)),
        ("after_release_qualification", (1, 1, 1)),
    ],
)
def test_real_store_finalization_recovers_each_boundary_without_duplicates(
    tmp_path: Path,
    monkeypatch,
    capsys,
    crash_at: str,
    partial_counts: tuple[int, int, int],
) -> None:
    basis = _seed_store_with_stop(tmp_path)
    store = basis["store"]
    service = FinalizationService(store)
    original_accept_one = service._accept_one
    tripped = False

    def crash_once(obj: CanonicalObject, scope: str):
        nonlocal tripped
        after_release = (
            crash_at == "after_release_qualification"
            and scope == "release_qualification"
        )
        if not tripped and (scope == crash_at or after_release):
            tripped = True
            if after_release:
                result = original_accept_one(obj, scope)
                raise RuntimeError("simulated crash after durable release qualification")
            raise RuntimeError(f"simulated crash before {scope}")
        return original_accept_one(obj, scope)

    monkeypatch.setattr(service, "_accept_one", crash_once)
    with pytest.raises(RuntimeError, match="simulated crash"):
        service.conclude_campaign(
            termination_state="COMPLETED",
            bounded_statement="Real store crash recovery regression",
        )

    def counts() -> tuple[int, int, int]:
        cut = current_accepted_cut(store)
        return tuple(
            len(store.accepted_records(kind, cut))
            for kind in (
                "campaign_conclusion",
                "final_assurance_case",
                "release_qualification",
            )
        )

    assert counts() == partial_counts
    monkeypatch.setattr(service, "_accept_one", original_accept_one)

    if partial_counts[0]:
        progress = AuditOperationApi().continue_campaign(basis["store_path"])
        assert progress["next_action"] == (
            "CAMPAIGN_FINISHED"
            if partial_counts == (1, 1, 1)
            else "RESUME_FINALIZATION"
        )
        assert progress["workflow_finished"] is (partial_counts == (1, 1, 1))
        if partial_counts == (1, 0, 0):
            from bdb_audit.cli import run_cli

            assert run_cli(
                ["audit", "resume", "--store", str(basis["store_path"]), "--json"]
            ) == 0
            import json

            cli_progress = json.loads(capsys.readouterr().out)
            assert cli_progress["next_action"] == "RESUME_FINALIZATION"
            assert cli_progress["workflow_finished"] is False

    result = service.conclude_campaign(
        termination_state="COMPLETED",
        bounded_statement="Real store crash recovery regression",
    )
    assert result["status"] == "SUCCESS"
    assert counts() == (1, 1, 1)
    assert result["commit_seq"] == store.head().commit_seq

    retry = service.conclude_campaign(
        termination_state="COMPLETED",
        bounded_statement="Real store crash recovery regression",
    )
    assert retry["commit_seq"] == result["commit_seq"]
    assert counts() == (1, 1, 1)
