"""Real external E5A/E5B campaign runtime.

The accepted-history order is deliberately acyclic:

E4 StageCompletion -> E5A external results -> frozen CandidateAssuranceCase
-> ChallengerAssignment pair -> E5B external proposals -> canonical
ChallengerResult pair -> E5 StageCompletion -> FINAL_POST_E5 STOP.

No challenger result is synthesized by BDB.  Counterevidence, inconclusive
execution, blocked execution, or pending E5A findings fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Mapping, Sequence

from ..assurance.candidate_case import (
    CandidateAssuranceCase,
    sort_refs_by_digest,
)
from ..assurance.challenger import (
    ChallengerAssignment,
    ChallengerResult,
    E5ChallengerOrchestrator,
    CHALLENGER_OUTCOME_STATUSES,
)
from ..coordinator import Coordinator
from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, CommandEnvelope, HistoryCut
from ..history.store import TransactionalHistoryStore
from .assignments import _command_id, _current_cut, _external_ref
from .inbox import _same_ref, _with_ref_class
from .manual_stage import (
    StageAssignmentService,
    StageAuthorizedContext,
    StageBatch,
    StageLaneDefinition,
    StageResultInbox,
)
from .stage_finalize import ExternalStageFinalizationService


E5A_LANES = (
    StageLaneDefinition(
        "E5-A-INTERACTION",
        "Interaction and bounded combinatorial attack",
        "INTERACTION_COMBINATORIAL_ATTACK",
    ),
    StageLaneDefinition(
        "E5-A-MUTATION",
        "Invariant-targeted implementation/oracle/spec mutation",
        "CONTRASTIVE_MUTATION_ATTACK",
    ),
    StageLaneDefinition(
        "E5-A-CALIBRATION",
        "Qualified auditor calibration",
        "CALIBRATION_PROFILE_EXECUTION",
    ),
)

E5B_LANES = (
    StageLaneDefinition(
        "E5-B1",
        "False-positive skeptic",
        "FALSE_POSITIVE_SKEPTIC",
    ),
    StageLaneDefinition(
        "E5-B2",
        "False-negative hunter",
        "FALSE_NEGATIVE_HUNTER",
    ),
)

E5_ALL_LANE_SLOTS = tuple(
    item.lane_slot for item in (*E5A_LANES, *E5B_LANES)
)
_E5B_ROLE_BY_SLOT = {
    "E5-B1": "FALSE_POSITIVE_SKEPTIC",
    "E5-B2": "FALSE_NEGATIVE_HUNTER",
}
_INTERACTION_STATUSES = {
    "PASS",
    "FAIL",
    "INCONCLUSIVE",
    "BLOCKED",
}
_MUTATION_CLASSES = {
    "IMPLEMENTATION",
    "ORACLE",
    "SPECIFICATION",
}
_MUTATION_STATUSES = {
    "MUTANT_KILLED",
    "MUTANT_SURVIVED",
    "MUTATION_NOT_ACTIVATED",
    "REDUNDANT_OBSERVER",
    "HARNESS_FAILURE",
    "INVALID_MUTATION",
    "INCONCLUSIVE",
}
_MUTATION_UNRESOLVED = {
    "MUTATION_NOT_ACTIVATED",
    "HARNESS_FAILURE",
    "INVALID_MUTATION",
    "INCONCLUSIVE",
}


def _latest(records: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    rows = tuple(records)
    return (
        max(rows, key=lambda row: int(row.get("accepted_seq", 0)))
        if rows
        else None
    )


def _latest_by(
    records: Iterable[dict[str, Any]],
    key_fn,
) -> tuple[dict[str, Any], ...]:
    selected: dict[str, dict[str, Any]] = {}
    for row in records:
        key = str(key_fn(row) or "")
        if not key:
            continue
        prior = selected.get(key)
        if (
            prior is None
            or int(row.get("accepted_seq", 0))
            > int(prior.get("accepted_seq", 0))
        ):
            selected[key] = row
    return tuple(selected[key] for key in sorted(selected))


def _accepted_result_for_job(
    store: TransactionalHistoryStore,
    batch: StageBatch,
    slot: str,
    cut: dict[str, Any],
) -> dict[str, Any]:
    job = batch.get_job(slot)
    rows = [
        row
        for row in store.accepted_records("bdb_audit_lane_result", cut)
        if row["body"].get("stage_id") == batch.stage_id
        and row["body"].get("phase_id") == batch.phase_id
        and row["body"].get("lane_slot") == slot
        and _same_ref(
            row["body"].get("assignment_ref"),
            job.assignment_ref,
        )
    ]
    if len(rows) != 1:
        raise ValidationError(
            "E5_RESULT_SET_INCOMPLETE",
            f"{batch.phase_id}/{slot}: expected 1, got {len(rows)}",
        )
    return rows[0]


def _accept_objects(
    store: TransactionalHistoryStore,
    objects: Sequence[CanonicalObject],
    *,
    scope: str,
) -> Any:
    if not objects:
        raise ValidationError("E5_EMPTY_ACCEPTANCE_BOUNDARY", scope)
    cut, prior_commit = _current_cut(store)
    head = store.head()
    if head is None:
        raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
    material = canonical_bytes(
        {
            "scope": scope,
            "input_history_cut": cut,
            "object_digests": [obj.digest for obj in objects],
        }
    )
    token = hashlib.sha256(material).hexdigest()
    command = CommandEnvelope(
        command_id=_command_id(f"{scope}:{token}"),
        command_kind="RECORD_ASSURANCE_DECISION",
        actor_ref=prior_commit.get("actor_ref", "installation-owner"),
        expected_parent_head={
            "tag": "ACCEPTED_HEAD_REF",
            **head.as_dict(),
        },
        governing_policy_ref=prior_commit["governing_policy_ref"],
        governing_spec_refs=tuple(
            prior_commit.get("governing_spec_refs", ())
        ),
        idempotency_scope=f"{scope}:{token}",
        campaign_ref=head.campaign_id,
    )
    return Coordinator(store).accept(
        command,
        immutable_objects=list(objects),
        expected_head=head,
    )


def _candidate_from_record(
    record: Mapping[str, Any],
) -> CandidateAssuranceCase:
    body = record["body"]
    return CandidateAssuranceCase(
        candidate_assurance_case_id=body[
            "candidate_assurance_case_id"
        ],
        campaign_ref=dict(body["campaign_ref"]),
        source_generation_ref=dict(
            body["source_generation_ref"]
        ),
        candidate_input_history_cut=dict(
            body["candidate_input_history_cut"]
        ),
        scope_inventory_ref=dict(body["scope_inventory_ref"]),
        coverage_obligation_refs=tuple(
            dict(ref)
            for ref in body.get("coverage_obligation_refs", ())
        ),
        coverage_obligation_qualification_refs=tuple(
            dict(ref)
            for ref in body.get(
                "coverage_obligation_qualification_refs", ()
            )
        ),
        finding_claim_revision_refs=tuple(
            dict(ref)
            for ref in body.get("finding_claim_revision_refs", ())
        ),
        finding_adjudication_refs=tuple(
            dict(ref)
            for ref in body.get("finding_adjudication_refs", ())
        ),
        contradiction_refs=tuple(
            dict(ref)
            for ref in body.get("contradiction_refs", ())
        ),
        evidence_qualification_refs=tuple(
            dict(ref)
            for ref in body.get("evidence_qualification_refs", ())
        ),
        residual_risk_refs=tuple(
            dict(ref)
            for ref in body.get("residual_risk_refs", ())
        ),
        assurance_claim_set_ref=dict(
            body["assurance_claim_set_ref"]
        ),
        coverage_obligation_summary_ref=(
            dict(body["coverage_obligation_summary_ref"])
            if isinstance(
                body.get("coverage_obligation_summary_ref"),
                dict,
            )
            else None
        ),
    )


def _challenger_assignment_from_record(
    record: Mapping[str, Any],
) -> ChallengerAssignment:
    body = record["body"]
    return ChallengerAssignment(
        challenge_assignment_id=body["challenge_assignment_id"],
        candidate_assurance_case_ref=dict(
            body["candidate_assurance_case_ref"]
        ),
        challenger_type=body["challenger_type"],
        challenge_scope=body["challenge_scope"],
        challenge_policy_ref=dict(body["challenge_policy_ref"]),
        executor_profile_ref=dict(body["executor_profile_ref"]),
        assignment_input_history_cut=dict(
            body["assignment_input_history_cut"]
        ),
        forbidden_prior_result_refs=tuple(
            dict(ref)
            for ref in body.get("forbidden_prior_result_refs", ())
        ),
    )


def _challenger_result_from_record(
    record: Mapping[str, Any],
) -> ChallengerResult:
    body = record["body"]
    return ChallengerResult(
        challenger_result_id=body["challenger_result_id"],
        challenge_assignment_ref=dict(
            body["challenge_assignment_ref"]
        ),
        candidate_assurance_case_ref=dict(
            body["candidate_assurance_case_ref"]
        ),
        result_input_history_cut=dict(
            body["result_input_history_cut"]
        ),
        status=body["status"],
        challenged_claim_or_scope_refs=tuple(
            dict(ref)
            for ref in body.get(
                "challenged_claim_or_scope_refs", ()
            )
        ),
        counterclaim_refs=tuple(
            dict(ref)
            for ref in body.get("counterclaim_refs", ())
        ),
        evidence_qualification_refs=tuple(
            dict(ref)
            for ref in body.get(
                "evidence_qualification_refs", ()
            )
        ),
        reason_codes=tuple(
            str(value)
            for value in body.get("reason_codes", ())
        ),
    )


@dataclass(frozen=True)
class E5AValidationSummary:
    result_refs: tuple[dict[str, Any], ...]
    accepted_result_seq: int
    pending_findings_count: int


class E5AValidationService:
    """Validate the E5A interaction/mutation/calibration proposal contract."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
        batch: StageBatch,
        inbox: StageResultInbox | None = None,
    ):
        if (
            batch.stage_id != "E5"
            or batch.phase_id != "E5A-ATTACK"
        ):
            raise ValidationError("E5A_BATCH_REQUIRED")
        self.store = store
        self.batch = batch
        self.inbox = inbox

    @staticmethod
    def _require_rationale(item: Mapping[str, Any]) -> None:
        rationale = item.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValidationError("E5A_RATIONALE_REQUIRED")

    @classmethod
    def validate_result_body(
        cls,
        slot: str,
        body: Mapping[str, Any],
    ) -> None:
        outputs = body.get("outputs", {})
        if not isinstance(outputs, Mapping):
            raise ValidationError("E5A_OUTPUTS_REQUIRED", slot)

        if slot == "E5-A-INTERACTION":
            rows = outputs.get("e5a_interaction_results")
            if not isinstance(rows, list) or not rows:
                raise ValidationError(
                    "E5A_INTERACTION_RESULTS_REQUIRED"
                )
            unresolved = []
            has_failure = False
            for item in rows:
                if not isinstance(item, Mapping):
                    raise ValidationError(
                        "E5A_INTERACTION_RESULT_INVALID"
                    )
                status = item.get("status")
                if status not in _INTERACTION_STATUSES:
                    raise ValidationError(
                        "E5A_INTERACTION_STATUS_INVALID",
                        str(status),
                    )
                cls._require_rationale(item)
                if status in {"INCONCLUSIVE", "BLOCKED"}:
                    unresolved.append(status)
                if status == "FAIL":
                    has_failure = True
            if unresolved:
                raise ValidationError(
                    "E5A_INTERACTION_UNRESOLVED",
                    ",".join(unresolved),
                )
            if has_failure and not body.get("findings"):
                raise ValidationError(
                    "E5A_FAILURE_FINDING_REQUIRED",
                    slot,
                )
            return

        if slot == "E5-A-MUTATION":
            rows = outputs.get("e5a_mutation_results")
            if not isinstance(rows, list) or not rows:
                raise ValidationError(
                    "E5A_MUTATION_RESULTS_REQUIRED"
                )
            classes: set[str] = set()
            unresolved: list[str] = []
            survived = False
            for item in rows:
                if not isinstance(item, Mapping):
                    raise ValidationError(
                        "E5A_MUTATION_RESULT_INVALID"
                    )
                mutation_class = item.get("mutation_class")
                status = item.get("status")
                if mutation_class not in _MUTATION_CLASSES:
                    raise ValidationError(
                        "E5A_MUTATION_CLASS_INVALID",
                        str(mutation_class),
                    )
                if status not in _MUTATION_STATUSES:
                    raise ValidationError(
                        "E5A_MUTATION_STATUS_INVALID",
                        str(status),
                    )
                cls._require_rationale(item)
                classes.add(str(mutation_class))
                if status in {
                    "MUTANT_KILLED",
                    "MUTANT_SURVIVED",
                }:
                    witness = item.get("activation_witness")
                    if (
                        not isinstance(witness, str)
                        or not witness.strip()
                    ):
                        raise ValidationError(
                            "E5A_MUTATION_ACTIVATION_WITNESS_REQUIRED",
                            str(mutation_class),
                        )
                if status in _MUTATION_UNRESOLVED:
                    unresolved.append(
                        f"{mutation_class}:{status}"
                    )
                if status == "MUTANT_SURVIVED":
                    survived = True
            missing = sorted(_MUTATION_CLASSES - classes)
            if missing:
                raise ValidationError(
                    "E5A_MUTATION_CLASS_SET_INCOMPLETE",
                    ",".join(missing),
                )
            if unresolved:
                raise ValidationError(
                    "E5A_MUTATION_UNRESOLVED",
                    ",".join(unresolved),
                )
            if survived and not body.get("findings"):
                raise ValidationError(
                    "E5A_FAILURE_FINDING_REQUIRED",
                    slot,
                )
            return

        if slot == "E5-A-CALIBRATION":
            result = outputs.get("e5a_calibration")
            if not isinstance(result, Mapping):
                raise ValidationError(
                    "E5A_CALIBRATION_RESULT_REQUIRED"
                )
            status = result.get("status")
            if status not in {
                "QUALIFIED",
                "INCONCLUSIVE",
                "BLOCKED",
            }:
                raise ValidationError(
                    "E5A_CALIBRATION_STATUS_INVALID",
                    str(status),
                )
            cls._require_rationale(result)
            profile_ref = result.get("profile_ref")
            metrics = result.get("per_class_metrics")
            unknown_count = result.get("unknown_count")
            if (
                not isinstance(profile_ref, Mapping)
                or not isinstance(metrics, Mapping)
                or type(unknown_count) is not int
                or unknown_count < 0
            ):
                raise ValidationError(
                    "E5A_CALIBRATION_EVIDENCE_INCOMPLETE"
                )
            if status != "QUALIFIED":
                raise ValidationError(
                    "E5A_CALIBRATION_UNRESOLVED",
                    str(status),
                )
            return

        raise ValidationError("UNKNOWN_E5A_LANE", slot)

    def validate(self) -> E5AValidationSummary:
        if self.inbox is not None:
            self.inbox._load_accepted_state()
            incomplete = [
                slot
                for slot, lane in self.inbox.lane_statuses.items()
                if lane.status != "ACCEPTED"
                or lane.completion_status != "LANE_COMPLETED"
            ]
            if incomplete:
                raise ValidationError(
                    "E5A_PHASE_NOT_COMPLETE",
                    ",".join(incomplete),
                )

        cut, _ = _current_cut(self.store)
        rows = []
        pending = 0
        for slot in self.batch.lane_slots:
            row = _accepted_result_for_job(
                self.store,
                self.batch,
                slot,
                cut,
            )
            self.validate_result_body(slot, row["body"])
            findings = row["body"].get("findings", ())
            if isinstance(findings, (list, tuple)):
                pending += len(findings)
            rows.append(row)
        return E5AValidationSummary(
            result_refs=tuple(
                _with_ref_class(
                    row["ref"], "CONTENT_OR_PRIOR"
                )
                for row in rows
            ),
            accepted_result_seq=max(
                int(row["accepted_seq"]) for row in rows
            ),
            pending_findings_count=pending,
        )


@dataclass(frozen=True)
class CandidateFreezeSummary:
    candidate: CandidateAssuranceCase
    candidate_ref: dict[str, Any]
    accepted_commit_seq: int
    already_frozen: bool


class CandidateAssuranceCaseService:
    """Freeze one candidate after a complete and adjudicated E5A cut."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
    ):
        self.store = store

    def current_candidate(self) -> CandidateFreezeSummary:
        cut, _ = _current_cut(self.store)
        record = _latest(
            self.store.accepted_records(
                "candidate_assurance_case", cut
            )
        )
        if record is None:
            raise ValidationError(
                "E5_CANDIDATE_NOT_FROZEN"
            )
        return CandidateFreezeSummary(
            candidate=_candidate_from_record(record),
            candidate_ref=_with_ref_class(
                record["ref"], "PRIOR_ACCEPTED_ONLY"
            ),
            accepted_commit_seq=int(record["accepted_seq"]),
            already_frozen=True,
        )

    def freeze(
        self,
        batch: StageBatch,
        inbox: StageResultInbox | None = None,
    ) -> CandidateFreezeSummary:
        validation = E5AValidationService(
            self.store,
            batch,
            inbox,
        ).validate()
        if validation.pending_findings_count:
            raise ValidationError(
                "E5A_FINDINGS_REQUIRE_ADJUDICATION",
                (
                    f"{validation.pending_findings_count} E5A "
                    "finding proposal(s) must be canonicalized and "
                    "adjudicated before candidate freeze"
                ),
            )

        cut, _ = _current_cut(self.store)
        existing = _latest(
            self.store.accepted_records(
                "candidate_assurance_case", cut
            )
        )
        if (
            existing is not None
            and int(existing["accepted_seq"])
            > validation.accepted_result_seq
        ):
            return CandidateFreezeSummary(
                candidate=_candidate_from_record(existing),
                candidate_ref=_with_ref_class(
                    existing["ref"], "PRIOR_ACCEPTED_ONLY"
                ),
                accepted_commit_seq=int(existing["accepted_seq"]),
                already_frozen=True,
            )

        source = _latest(
            self.store.accepted_records(
                "source_generation", cut
            )
        )
        if source is None:
            raise ValidationError(
                "CANDIDATE_SOURCE_GENERATION_REQUIRED"
            )
        inventory = _latest(
            self.store.accepted_records(
                "inventory_revision", cut
            )
        )
        if inventory is None:
            raise ValidationError(
                "CANDIDATE_SCOPE_INVENTORY_REQUIRED"
            )

        obligations = _latest_by(
            self.store.accepted_records(
                "coverage_obligation", cut
            ),
            lambda row: row["body"].get(
                "obligation_id",
                row["ref"]["revision_digest"],
            ),
        )
        obligation_digests = {
            row["ref"]["revision_digest"]
            for row in obligations
        }
        qualifications = _latest_by(
            (
                row
                for row in self.store.accepted_records(
                    "coverage_obligation_qualification",
                    cut,
                )
                if row["body"].get(
                    "obligation_revision_ref", {}
                ).get("revision_digest")
                in obligation_digests
            ),
            lambda row: row["body"].get(
                "obligation_revision_ref", {}
            ).get("revision_digest"),
        )
        findings = _latest_by(
            self.store.accepted_records(
                "finding_claim_revision", cut
            ),
            lambda row: row["body"].get(
                "claim_id", row["ref"]["revision_digest"]
            ),
        )
        adjudications = _latest_by(
            self.store.accepted_records(
                "finding_adjudication_decision", cut
            ),
            lambda row: row["body"].get(
                "claim_revision_ref", {}
            ).get("revision_digest"),
        )
        contradictions = _latest_by(
            self.store.accepted_records(
                "contradiction_revision", cut
            ),
            lambda row: row["body"].get(
                "contradiction_id",
                row["ref"]["revision_digest"],
            ),
        )
        evidence = _latest_by(
            self.store.accepted_records(
                "evidence_qualification_assessment", cut
            ),
            lambda row: row["body"].get(
                "assessment_id",
                row["ref"]["revision_digest"],
            ),
        )
        risks = _latest_by(
            self.store.accepted_records(
                "residual_risk", cut
            ),
            lambda row: row["body"].get(
                "residual_risk_id",
                row["ref"]["revision_digest"],
            ),
        )

        def refs(
            rows: Sequence[dict[str, Any]],
        ) -> tuple[dict[str, Any], ...]:
            return sort_refs_by_digest(
                [
                    _with_ref_class(
                        row["ref"], "CONTENT_OR_PRIOR"
                    )
                    for row in rows
                ]
            )

        e5a_refs = tuple(validation.result_refs)
        basis_payload = {
            "input_history_cut": cut,
            "e5a_result_refs": list(e5a_refs),
            "coverage_obligation_refs": list(refs(obligations)),
            "coverage_qualification_refs": list(
                refs(qualifications)
            ),
            "finding_refs": list(refs(findings)),
            "adjudication_refs": list(refs(adjudications)),
            "contradiction_refs": list(refs(contradictions)),
            "evidence_qualification_refs": list(refs(evidence)),
            "residual_risk_refs": list(refs(risks)),
        }
        claim_set_digest = hashlib.sha256(
            canonical_bytes(basis_payload)
        ).hexdigest()
        case_id = deterministic_id(
            "candidate_assurance_case",
            (
                cut["campaign_id"]
                + ":"
                + cut["accepted_head_hash"]
                + ":"
                + claim_set_digest
            ),
        )
        candidate = CandidateAssuranceCase(
            candidate_assurance_case_id=case_id,
            campaign_ref=_external_ref(
                "campaign_ref",
                cut["campaign_id"],
                "PRIOR_ACCEPTED_ONLY",
            ),
            source_generation_ref=_with_ref_class(
                source["ref"], "CONTENT_OR_PRIOR"
            ),
            candidate_input_history_cut=cut,
            scope_inventory_ref=_with_ref_class(
                inventory["ref"], "CONTENT_OR_PRIOR"
            ),
            coverage_obligation_refs=refs(obligations),
            coverage_obligation_qualification_refs=refs(
                qualifications
            ),
            finding_claim_revision_refs=refs(findings),
            finding_adjudication_refs=refs(adjudications),
            contradiction_refs=refs(contradictions),
            evidence_qualification_refs=refs(evidence),
            residual_risk_refs=refs(risks),
            assurance_claim_set_ref=_external_ref(
                "assurance_claim_set_ref",
                claim_set_digest,
                "CONTENT_OR_PRIOR",
            ),
        )
        obj = CanonicalObject(
            "candidate_assurance_case",
            candidate.body(),
            logical_id=candidate.candidate_assurance_case_id,
        )
        accepted = _accept_objects(
            self.store,
            [obj],
            scope="e5_candidate_freeze",
        )
        return CandidateFreezeSummary(
            candidate=candidate,
            candidate_ref=obj.as_ref(
                ref_class="PRIOR_ACCEPTED_ONLY"
            ).as_dict(),
            accepted_commit_seq=accepted.head.commit_seq,
            already_frozen=False,
        )


def _candidate_evidence_members(
    store: TransactionalHistoryStore,
    candidate_record: dict[str, Any],
    cut: dict[str, Any],
) -> dict[str, bytes]:
    body = candidate_record["body"]
    refs: list[dict[str, Any]] = []
    for key in (
        "source_generation_ref",
        "scope_inventory_ref",
    ):
        value = body.get(key)
        if isinstance(value, dict):
            refs.append(value)
    for key in (
        "coverage_obligation_refs",
        "coverage_obligation_qualification_refs",
        "finding_claim_revision_refs",
        "finding_adjudication_refs",
        "contradiction_refs",
        "evidence_qualification_refs",
        "residual_risk_refs",
    ):
        refs.extend(
            dict(ref)
            for ref in body.get(key, ())
            if isinstance(ref, dict)
        )
    records = []
    for ref in canonical_reference_set(refs):
        try:
            record = store.resolve_accepted(ref, cut)
        except ValidationError:
            continue
        records.append(
            {
                "ref": _with_ref_class(
                    record["ref"], "CONTENT_OR_PRIOR"
                ),
                "body": record["body"],
            }
        )
    candidate_ref = _with_ref_class(
        candidate_record["ref"], "PRIOR_ACCEPTED_ONLY"
    )
    return {
        "CANDIDATE_ASSURANCE_CASE.json": canonical_bytes(
            {
                "ref": candidate_ref,
                "body": body,
            }
        ),
        "CANDIDATE_EVIDENCE_VIEW.json": canonical_bytes(
            {"records": records}
        ),
    }


class E5ChallengeAuthorizationService:
    """Accept challenger assignments, then authorize candidate-only E5B view."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
        *,
        candidate: CandidateAssuranceCase,
        executor_profile: str,
        model: str,
    ):
        self.store = store
        self.candidate = candidate
        self.executor_profile = executor_profile
        self.model = model
        self.coordinator = Coordinator(store)

    def _candidate_record(
        self,
        cut: dict[str, Any],
    ) -> dict[str, Any]:
        digest = self.candidate.digest()
        rows = [
            row
            for row in self.store.accepted_records(
                "candidate_assurance_case", cut
            )
            if row["ref"]["revision_digest"] == digest
        ]
        if len(rows) != 1:
            raise ValidationError(
                "E5_CANDIDATE_ACCEPTANCE_REQUIRED"
            )
        return rows[0]

    def authorize(self) -> StageAuthorizedContext:
        stage_assignments = StageAssignmentService(
            self.store
        ).prepare_phase_assignments(
            stage_id="E5",
            phase_id="E5B-CHALLENGE",
            lane_definitions=E5B_LANES,
            all_stage_lane_slots=E5_ALL_LANE_SLOTS,
            executor_profile=self.executor_profile,
            model=self.model,
        )
        cut, prior_commit = _current_cut(self.store)
        candidate_record = self._candidate_record(cut)
        candidate_prior_ref = _with_ref_class(
            candidate_record["ref"], "PRIOR_ACCEPTED_ONLY"
        )
        candidate_digest = candidate_prior_ref[
            "revision_digest"
        ]

        existing_rows = [
            row
            for row in self.store.accepted_records(
                "challenger_assignment", cut
            )
            if row["body"].get(
                "candidate_assurance_case_ref", {}
            ).get("revision_digest") == candidate_digest
        ]
        by_role: dict[str, dict[str, Any]] = {}
        for row in existing_rows:
            role = row["body"].get("challenger_type")
            if role in by_role:
                raise ValidationError(
                    "MULTIPLE_E5_CHALLENGER_ASSIGNMENTS",
                    str(role),
                )
            if role in set(_E5B_ROLE_BY_SLOT.values()):
                by_role[str(role)] = row

        new_assignment_objects: list[CanonicalObject] = []
        assignment_payload: dict[str, dict[str, Any]] = {}
        prior_results = canonical_reference_set(
            [
                _with_ref_class(
                    row["ref"], "PRIOR_ACCEPTED_ONLY"
                )
                for row in self.store.accepted_records(
                    "challenger_result", cut
                )
            ]
        )
        for slot, prepared in stage_assignments.assignments.items():
            role = _E5B_ROLE_BY_SLOT[slot]
            existing = by_role.get(role)
            if existing is not None:
                assignment_payload[slot] = {
                    "ref": _with_ref_class(
                        existing["ref"], "CONTENT_OR_PRIOR"
                    ),
                    "body": existing["body"],
                }
                continue
            stage_assignment = self.store.resolve_accepted(
                prepared.assignment_ref,
                cut,
            )
            challenger = ChallengerAssignment(
                challenge_assignment_id=deterministic_id(
                    "challenger_assignment",
                    f"{candidate_digest}:{role}",
                ),
                candidate_assurance_case_ref=candidate_prior_ref,
                challenger_type=role,
                challenge_scope="EXACT_FROZEN_CANDIDATE",
                challenge_policy_ref=_external_ref(
                    "policy_revision",
                    "R5.3_BASELINE_DUAL_CHALLENGE",
                    "HISTORY_CONTEXT_BINDING",
                ),
                executor_profile_ref=dict(
                    stage_assignment["body"][
                        "executor_profile_ref"
                    ]
                ),
                assignment_input_history_cut=cut,
                forbidden_prior_result_refs=tuple(
                    prior_results
                ),
            )
            obj = CanonicalObject(
                "challenger_assignment",
                challenger.body(),
                logical_id=challenger.challenge_assignment_id,
            )
            new_assignment_objects.append(obj)
            assignment_payload[slot] = {
                "ref": obj.as_ref(
                    ref_class="CONTENT_OR_PRIOR"
                ).as_dict(),
                "body": challenger.body(),
            }

        members = _candidate_evidence_members(
            self.store,
            candidate_record,
            cut,
        )
        members["CHALLENGER_ASSIGNMENTS.json"] = (
            canonical_bytes(assignment_payload)
        )
        manifest = {
            name: hashlib.sha256(raw).hexdigest()
            for name, raw in sorted(members.items())
        }
        payload_sha = hashlib.sha256(
            canonical_bytes(manifest)
        ).hexdigest()

        existing_views = [
            row
            for row in self.store.accepted_records(
                "view_manifest", cut
            )
            if row["body"].get("phase_id")
            == "E5B-CHALLENGE"
            and row["body"].get(
                "candidate_assurance_case_ref", {}
            ).get("revision_digest") == candidate_digest
            and row["body"].get("payload_sha256")
            == payload_sha
        ]
        if len(existing_views) > 1:
            raise ValidationError(
                "MULTIPLE_E5B_VIEW_MANIFESTS"
            )
        if existing_views:
            view = existing_views[0]
            grant_refs: dict[str, dict[str, Any]] = {}
            knowledge_refs: dict[str, dict[str, Any]] = {}
            for slot, prepared in (
                stage_assignments.assignments.items()
            ):
                grants = [
                    row
                    for row in self.store.accepted_records(
                        "grant_body", cut
                    )
                    if _same_ref(
                        row["body"].get("attempt_ref"),
                        prepared.attempt_ref,
                    )
                    and _same_ref(
                        row["body"].get(
                            "view_manifest_ref"
                        ),
                        view["ref"],
                    )
                ]
                states = [
                    row
                    for row in self.store.accepted_records(
                        "knowledge_state", cut
                    )
                    if _same_ref(
                        row["body"].get("attempt_ref"),
                        prepared.attempt_ref,
                    )
                    and any(
                        _same_ref(ref, view["ref"])
                        for ref in row["body"].get(
                            "allowed_view_refs", ()
                        )
                        if isinstance(ref, dict)
                    )
                ]
                if len(grants) != 1 or len(states) != 1:
                    raise ValidationError(
                        "PARTIAL_E5B_AUTHORIZATION",
                        slot,
                    )
                grant_refs[slot] = _with_ref_class(
                    grants[0]["ref"], "CONTENT_OR_PRIOR"
                )
                knowledge_refs[slot] = _with_ref_class(
                    states[0]["ref"], "CONTENT_OR_PRIOR"
                )
            return StageAuthorizedContext(
                campaign_id=stage_assignments.campaign_id,
                stage_id="E5",
                phase_id="E5B-CHALLENGE",
                context_members=members,
                context_manifest=manifest,
                view_manifest_ref=_with_ref_class(
                    view["ref"], "CONTENT_OR_PRIOR"
                ),
                grant_refs_by_slot=grant_refs,
                knowledge_state_refs_by_slot=knowledge_refs,
                authorization_history_cut=cut,
                assignments=dict(
                    stage_assignments.assignments
                ),
                already_authorized=True,
            )

        allowed_refs = [
            candidate_prior_ref,
        ]
        for member_ref in candidate_record["body"].get(
            "coverage_obligation_refs", ()
        ):
            if isinstance(member_ref, dict):
                allowed_refs.append(dict(member_ref))
        for field in (
            "coverage_obligation_qualification_refs",
            "finding_claim_revision_refs",
            "finding_adjudication_refs",
            "contradiction_refs",
            "evidence_qualification_refs",
            "residual_risk_refs",
        ):
            allowed_refs.extend(
                dict(ref)
                for ref in candidate_record["body"].get(
                    field, ()
                )
                if isinstance(ref, dict)
            )

        policy = CanonicalObject(
            "projection_policy",
            {
                "projection_policy_id": deterministic_id(
                    "projection_policy",
                    f"E5B:{candidate_digest}",
                ),
                "stage_id": "E5",
                "phase_id": "E5B-CHALLENGE",
                "policy_input_history_cut": cut,
                "allowed_artifact_kinds": sorted(
                    {
                        ref.get("kind", "")
                        for ref in allowed_refs
                        if ref.get("kind")
                    }
                ),
                "forbidden_knowledge_classes": [
                    "PRIOR_CHALLENGER_RESULTS",
                    "FUTURE_STOP_OR_CONCLUSION",
                ],
            },
        )
        view = CanonicalObject(
            "view_manifest",
            {
                "view_manifest_id": deterministic_id(
                    "view_manifest",
                    f"E5B:{candidate_digest}:{payload_sha}",
                ),
                "stage_id": "E5",
                "phase_id": "E5B-CHALLENGE",
                "candidate_assurance_case_ref": (
                    candidate_prior_ref
                ),
                "projection_policy_ref": policy.as_ref().as_dict(),
                "allowed_artifact_refs": canonical_reference_set(
                    allowed_refs
                ),
                "payload_manifest": manifest,
                "payload_sha256": payload_sha,
                "view_input_history_cut": cut,
            },
        )
        objects: list[CanonicalObject] = [
            *new_assignment_objects,
            policy,
            view,
        ]
        grants: dict[str, CanonicalObject] = {}
        states: dict[str, CanonicalObject] = {}
        for slot, prepared in stage_assignments.assignments.items():
            initial = self.store.resolve_accepted(
                prepared.knowledge_state_ref,
                cut,
            )
            grant = CanonicalObject(
                "grant_body",
                {
                    "grant_id": deterministic_id(
                        "grant_body",
                        f"E5B:{candidate_digest}:{slot}",
                    ),
                    "attempt_ref": dict(
                        prepared.attempt_ref
                    ),
                    "view_manifest_ref": view.as_ref().as_dict(),
                    "grant_input_history_cut": cut,
                    "forbidden_knowledge_classes": [
                        "PRIOR_CHALLENGER_RESULTS",
                        "FUTURE_STOP_OR_CONCLUSION",
                    ],
                },
            )
            exposure = CanonicalObject(
                "potential_exposure_record",
                {
                    "potential_exposure_record_id": (
                        deterministic_id(
                            "potential_exposure_record",
                            f"E5B:{candidate_digest}:{slot}",
                        )
                    ),
                    "attempt_ref": dict(
                        prepared.attempt_ref
                    ),
                    "view_manifest_ref": view.as_ref().as_dict(),
                    "grant_ref": grant.as_ref().as_dict(),
                    "exposure_input_history_cut": cut,
                    "exposure_class": (
                        "FROZEN_CANDIDATE_ASSURANCE_CASE"
                    ),
                },
            )
            state = CanonicalObject(
                "knowledge_state",
                {
                    "knowledge_state_id": deterministic_id(
                        "knowledge_state",
                        f"E5B:{candidate_digest}:{slot}",
                    ),
                    "attempt_ref": dict(
                        prepared.attempt_ref
                    ),
                    "basis_history_cut": cut,
                    "isolation_qualification_ref": dict(
                        initial["body"][
                            "isolation_qualification_ref"
                        ]
                    ),
                    "previous_knowledge_state_ref": (
                        _with_ref_class(
                            initial["ref"],
                            "PRIOR_ACCEPTED_ONLY",
                        )
                    ),
                    "allowed_view_refs": [
                        view.as_ref().as_dict()
                    ],
                    "contamination_assessment_refs": [],
                    "potential_exposure_refs": [
                        exposure.as_ref().as_dict()
                    ],
                },
            )
            grants[slot] = grant
            states[slot] = state
            objects.extend((grant, exposure, state))

        accepted = _accept_objects(
            self.store,
            objects,
            scope="e5b_challenger_authorization",
        )
        authorization_cut = HistoryCut.accepted(
            accepted.head,
            accepted.commit.governing_policy_ref,
            accepted.commit.governing_spec_refs,
        ).as_dict()
        return StageAuthorizedContext(
            campaign_id=stage_assignments.campaign_id,
            stage_id="E5",
            phase_id="E5B-CHALLENGE",
            context_members=members,
            context_manifest=manifest,
            view_manifest_ref=view.as_ref(
                ref_class="CONTENT_OR_PRIOR"
            ).as_dict(),
            grant_refs_by_slot={
                slot: obj.as_ref(
                    ref_class="CONTENT_OR_PRIOR"
                ).as_dict()
                for slot, obj in grants.items()
            },
            knowledge_state_refs_by_slot={
                slot: obj.as_ref(
                    ref_class="CONTENT_OR_PRIOR"
                ).as_dict()
                for slot, obj in states.items()
            },
            authorization_history_cut=authorization_cut,
            assignments=dict(stage_assignments.assignments),
            already_authorized=False,
        )


@dataclass(frozen=True)
class E5ChallengerResultSummary:
    challenger_result_refs: tuple[dict[str, Any], ...]
    accepted_commit_seq: int
    statuses: dict[str, str]
    already_materialized: bool


class E5ChallengerResultService:
    """Convert accepted E5B external proposals into canonical results."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
        batch: StageBatch,
        inbox: StageResultInbox | None = None,
    ):
        if (
            batch.stage_id != "E5"
            or batch.phase_id != "E5B-CHALLENGE"
        ):
            raise ValidationError("E5B_BATCH_REQUIRED")
        self.store = store
        self.batch = batch
        self.inbox = inbox

    @staticmethod
    def _candidate_allowed_refs(
        candidate: CandidateAssuranceCase,
    ) -> dict[str, dict[str, Any]]:
        refs = [
            candidate.scope_inventory_ref,
            *candidate.coverage_obligation_refs,
            *candidate.coverage_obligation_qualification_refs,
            *candidate.finding_claim_revision_refs,
            *candidate.finding_adjudication_refs,
            *candidate.contradiction_refs,
            *candidate.evidence_qualification_refs,
            *candidate.residual_risk_refs,
        ]
        return {
            str(ref["revision_digest"]): dict(ref)
            for ref in refs
            if isinstance(ref, dict)
            and isinstance(
                ref.get("revision_digest"), str
            )
        }

    @classmethod
    def validate_external_output(
        cls,
        *,
        slot: str,
        body: Mapping[str, Any],
        candidate_digest: str,
        assignment_digest: str,
    ) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
        outputs = body.get("outputs", {})
        payload = (
            outputs.get("challenger_result")
            if isinstance(outputs, Mapping)
            else None
        )
        if not isinstance(payload, Mapping):
            raise ValidationError(
                "E5B_CHALLENGER_RESULT_REQUIRED",
                slot,
            )
        status = payload.get("status")
        if status not in CHALLENGER_OUTCOME_STATUSES:
            raise ValidationError(
                "E5B_CHALLENGER_STATUS_INVALID",
                str(status),
            )
        if (
            payload.get("candidate_revision_digest")
            != candidate_digest
        ):
            raise ValidationError(
                "E5B_CANDIDATE_BINDING_MISMATCH",
                slot,
            )
        if (
            payload.get("challenge_assignment_revision_digest")
            != assignment_digest
        ):
            raise ValidationError(
                "E5B_ASSIGNMENT_BINDING_MISMATCH",
                slot,
            )
        reason_codes = payload.get("reason_codes", [])
        challenged = payload.get(
            "challenged_revision_digests", []
        )
        if not isinstance(reason_codes, list) or not all(
            isinstance(value, str) for value in reason_codes
        ):
            raise ValidationError(
                "E5B_REASON_CODES_INVALID", slot
            )
        if not isinstance(challenged, list) or not all(
            isinstance(value, str) for value in challenged
        ):
            raise ValidationError(
                "E5B_CHALLENGED_REFS_INVALID", slot
            )
        if (
            status == "MATERIAL_COUNTEREVIDENCE_FOUND"
            and not body.get("findings")
        ):
            raise ValidationError(
                "E5B_COUNTEREVIDENCE_FINDING_REQUIRED",
                slot,
            )
        return (
            str(status),
            tuple(challenged),
            tuple(reason_codes),
        )

    def materialize(self) -> E5ChallengerResultSummary:
        if self.inbox is not None:
            self.inbox._load_accepted_state()
            incomplete = [
                slot
                for slot, lane in self.inbox.lane_statuses.items()
                if lane.status != "ACCEPTED"
                or lane.completion_status != "LANE_COMPLETED"
            ]
            if incomplete:
                raise ValidationError(
                    "E5B_PHASE_NOT_COMPLETE",
                    ",".join(incomplete),
                )

        cut, _ = _current_cut(self.store)
        candidate_record = _latest(
            self.store.accepted_records(
                "candidate_assurance_case", cut
            )
        )
        if candidate_record is None:
            raise ValidationError(
                "E5_CANDIDATE_NOT_FROZEN"
            )
        candidate = _candidate_from_record(candidate_record)
        candidate_digest = candidate.digest()
        candidate_ref = _with_ref_class(
            candidate_record["ref"], "PRIOR_ACCEPTED_ONLY"
        )

        assignment_records = [
            row
            for row in self.store.accepted_records(
                "challenger_assignment", cut
            )
            if row["body"].get(
                "candidate_assurance_case_ref", {}
            ).get("revision_digest") == candidate_digest
        ]
        by_role = {
            row["body"].get("challenger_type"): row
            for row in assignment_records
            if row["body"].get("challenger_type")
            in set(_E5B_ROLE_BY_SLOT.values())
        }
        if set(by_role) != set(_E5B_ROLE_BY_SLOT.values()):
            raise ValidationError(
                "E5B_ASSIGNMENT_PAIR_REQUIRED"
            )

        existing_results = [
            row
            for row in self.store.accepted_records(
                "challenger_result", cut
            )
            if row["body"].get(
                "candidate_assurance_case_ref", {}
            ).get("revision_digest") == candidate_digest
        ]
        existing_by_assignment = {
            row["body"].get(
                "challenge_assignment_ref", {}
            ).get("revision_digest"): row
            for row in existing_results
        }
        expected_assignment_digests = {
            row["ref"]["revision_digest"]
            for row in by_role.values()
        }
        if expected_assignment_digests.issubset(
            set(existing_by_assignment)
        ):
            rows = [
                existing_by_assignment[digest]
                for digest in sorted(expected_assignment_digests)
            ]
            return E5ChallengerResultSummary(
                challenger_result_refs=tuple(
                    _with_ref_class(
                        row["ref"], "CONTENT_OR_PRIOR"
                    )
                    for row in rows
                ),
                accepted_commit_seq=max(
                    int(row["accepted_seq"]) for row in rows
                ),
                statuses={
                    row["body"]["challenge_assignment_ref"][
                        "revision_digest"
                    ]: row["body"]["status"]
                    for row in rows
                },
                already_materialized=True,
            )

        allowed_refs = self._candidate_allowed_refs(candidate)
        objects: list[CanonicalObject] = []
        result_models: dict[str, ChallengerResult] = {}
        assignment_models: dict[
            str, ChallengerAssignment
        ] = {}
        statuses: dict[str, str] = {}

        for slot in self.batch.lane_slots:
            role = _E5B_ROLE_BY_SLOT[slot]
            assignment_record = by_role[role]
            assignment = _challenger_assignment_from_record(
                assignment_record
            )
            assignment_models[slot] = assignment
            proposal = _accepted_result_for_job(
                self.store, self.batch, slot, cut
            )
            status, challenged_digests, reason_codes = (
                self.validate_external_output(
                    slot=slot,
                    body=proposal["body"],
                    candidate_digest=candidate_digest,
                    assignment_digest=assignment.digest(),
                )
            )
            unknown = [
                digest
                for digest in challenged_digests
                if digest not in allowed_refs
            ]
            if unknown:
                raise ValidationError(
                    "E5B_CHALLENGED_REF_OUTSIDE_CANDIDATE",
                    f"{slot}: {unknown}",
                )
            result = ChallengerResult(
                challenger_result_id=deterministic_id(
                    "challenger_result",
                    (
                        assignment.digest()
                        + ":"
                        + proposal["ref"]["revision_digest"]
                    ),
                ),
                challenge_assignment_ref=_with_ref_class(
                    assignment_record["ref"],
                    "PRIOR_ACCEPTED_ONLY",
                ),
                candidate_assurance_case_ref=candidate_ref,
                result_input_history_cut=cut,
                status=status,
                challenged_claim_or_scope_refs=tuple(
                    allowed_refs[digest]
                    for digest in challenged_digests
                ),
                counterclaim_refs=(
                    (
                        _with_ref_class(
                            proposal["ref"],
                            "CONTENT_OR_PRIOR",
                        ),
                    )
                    if status
                    == "MATERIAL_COUNTEREVIDENCE_FOUND"
                    else ()
                ),
                reason_codes=reason_codes,
            )
            obj = CanonicalObject(
                "challenger_result",
                result.body(),
                logical_id=result.challenger_result_id,
            )
            result_models[slot] = result
            objects.append(obj)
            statuses[slot] = status

        skeptic = result_models["E5-B1"]
        hunter = result_models["E5-B2"]
        eligible, reasons = (
            E5ChallengerOrchestrator.validate_challenger_results_pair(
                candidate,
                skeptic,
                hunter,
                assignment_models["E5-B1"],
                assignment_models["E5-B2"],
            )
        )
        if (
            not eligible
            and set(reasons)
            != {"CHALLENGER_EXECUTION_BLOCKED"}
        ):
            raise ValidationError(
                "E5_CHALLENGER_BINDING_INVALID",
                ",".join(reasons),
            )

        accepted = _accept_objects(
            self.store,
            objects,
            scope="e5b_challenger_results",
        )
        return E5ChallengerResultSummary(
            challenger_result_refs=tuple(
                obj.as_ref(
                    ref_class="CONTENT_OR_PRIOR"
                ).as_dict()
                for obj in objects
            ),
            accepted_commit_seq=accepted.head.commit_seq,
            statuses=statuses,
            already_materialized=False,
        )


class E5FinalizationService(ExternalStageFinalizationService):
    """Accept E5 StageCompletion only after the exact dual challenge pair."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
    ):
        super().__init__(
            store,
            stage_id="E5",
            required_phase_slots={
                "E5A-ATTACK": tuple(
                    item.lane_slot for item in E5A_LANES
                ),
                "E5B-CHALLENGE": tuple(
                    item.lane_slot for item in E5B_LANES
                ),
            },
            next_action="EVALUATE_FINAL_POST_E5_STOP",
        )

    def validate_result(
        self,
        phase_id: str,
        slot: str,
        result: dict[str, Any],
    ) -> None:
        if phase_id == "E5A-ATTACK":
            E5AValidationService.validate_result_body(
                slot, result["body"]
            )
            if result["body"].get("findings"):
                raise ValidationError(
                    "E5A_FINDINGS_REQUIRE_ADJUDICATION",
                    slot,
                )
            return
        if phase_id == "E5B-CHALLENGE":
            return
        raise ValidationError(
            "UNSUPPORTED_E5_PHASE", phase_id
        )

    def additional_required_output_refs(
        self,
        cut: dict[str, Any],
    ) -> Sequence[dict[str, Any]]:
        candidate_record = _latest(
            self.store.accepted_records(
                "candidate_assurance_case", cut
            )
        )
        if candidate_record is None:
            raise ValidationError(
                "E5_CANDIDATE_NOT_FROZEN"
            )
        candidate = _candidate_from_record(candidate_record)
        candidate_digest = candidate.digest()

        assignments = [
            row
            for row in self.store.accepted_records(
                "challenger_assignment", cut
            )
            if row["body"].get(
                "candidate_assurance_case_ref", {}
            ).get("revision_digest") == candidate_digest
        ]
        by_role = {
            row["body"].get("challenger_type"): row
            for row in assignments
            if row["body"].get("challenger_type")
            in set(_E5B_ROLE_BY_SLOT.values())
        }
        if set(by_role) != set(_E5B_ROLE_BY_SLOT.values()):
            raise ValidationError(
                "E5B_ASSIGNMENT_PAIR_REQUIRED"
            )

        results = [
            row
            for row in self.store.accepted_records(
                "challenger_result", cut
            )
            if row["body"].get(
                "candidate_assurance_case_ref", {}
            ).get("revision_digest") == candidate_digest
        ]
        by_assignment = {
            row["body"].get(
                "challenge_assignment_ref", {}
            ).get("revision_digest"): row
            for row in results
        }
        skeptic_assignment_record = by_role[
            "FALSE_POSITIVE_SKEPTIC"
        ]
        hunter_assignment_record = by_role[
            "FALSE_NEGATIVE_HUNTER"
        ]
        skeptic_record = by_assignment.get(
            skeptic_assignment_record["ref"][
                "revision_digest"
            ]
        )
        hunter_record = by_assignment.get(
            hunter_assignment_record["ref"][
                "revision_digest"
            ]
        )
        if skeptic_record is None or hunter_record is None:
            raise ValidationError(
                "E5B_CHALLENGER_RESULT_PAIR_REQUIRED"
            )

        skeptic_assignment = (
            _challenger_assignment_from_record(
                skeptic_assignment_record
            )
        )
        hunter_assignment = (
            _challenger_assignment_from_record(
                hunter_assignment_record
            )
        )
        skeptic = _challenger_result_from_record(
            skeptic_record
        )
        hunter = _challenger_result_from_record(
            hunter_record
        )
        eligible, reasons = (
            E5ChallengerOrchestrator.validate_challenger_results_pair(
                candidate,
                skeptic,
                hunter,
                skeptic_assignment,
                hunter_assignment,
            )
        )
        statuses = (skeptic.status, hunter.status)
        if (
            not eligible
            or statuses
            != (
                "NO_MATERIAL_COUNTEREVIDENCE",
                "NO_MATERIAL_COUNTEREVIDENCE",
            )
        ):
            raise ValidationError(
                "E5_CHALLENGER_ADJUDICATION_REQUIRED",
                (
                    f"statuses={statuses}; "
                    f"reasons={reasons}"
                ),
            )
        return canonical_reference_set(
            [
                _with_ref_class(
                    candidate_record["ref"],
                    "PRIOR_ACCEPTED_ONLY",
                ),
                _with_ref_class(
                    skeptic_assignment_record["ref"],
                    "PRIOR_ACCEPTED_ONLY",
                ),
                _with_ref_class(
                    hunter_assignment_record["ref"],
                    "PRIOR_ACCEPTED_ONLY",
                ),
                _with_ref_class(
                    skeptic_record["ref"],
                    "CONTENT_OR_PRIOR",
                ),
                _with_ref_class(
                    hunter_record["ref"],
                    "CONTENT_OR_PRIOR",
                ),
            ]
        )


__all__ = [
    "E5A_LANES",
    "E5B_LANES",
    "E5_ALL_LANE_SLOTS",
    "E5AValidationSummary",
    "E5AValidationService",
    "CandidateFreezeSummary",
    "CandidateAssuranceCaseService",
    "E5ChallengeAuthorizationService",
    "E5ChallengerResultSummary",
    "E5ChallengerResultService",
    "E5FinalizationService",
]
