"""Trusted coordinator acceptance of E2 contradiction resolutions.

The external E2-CONTRADICTION lane proposes a resolution for every exact
ContradictionRevision exposed by its accepted ViewManifest.  This service
validates complete case coverage, enum semantics, and basis refs against that
positive view, then records the canonical resolution DAG in two accepted
commits:

ContradictionRevision(N)
→ ContradictionResolutionDecision(N)
→ ContradictionRevision(N+1)

The second edge is intentionally a later commit because both predecessor and
resolution_decision_ref are PRIOR_ACCEPTED_ONLY in the pinned R5.3 registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..adjudication.engine import (
    apply_contradiction_resolution,
    resolve_contradiction,
)
from ..adjudication.models import (
    ContradictionResolutionDecision,
    ContradictionRevision,
)
from ..coordinator import Coordinator
from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, CommandEnvelope
from ..history.store import TransactionalHistoryStore
from ..stop.models import StageCompletion
from .assignments import _command_id, _current_cut
from .e2_shadow import _main_decisions
from .inbox import _same_ref, _with_ref_class
from .manual_stage import StageBatch, StageResultInbox


_RESOLUTION_KINDS = {
    "REFUTED",
    "SCOPES_SEPARATED",
    "HARNESS_INVALIDATED",
    "CONTRACT_CHANGED",
    "BLOCKED",
}
_RESULTING_STATUSES = {
    "RESOLVED_SCOPED",
    "RESOLVED_FULL",
    "BLOCKED",
}


@dataclass(frozen=True)
class E2ContradictionResolutionSummary:
    campaign_id: str
    decision_refs: tuple[dict[str, Any], ...]
    successor_contradiction_refs: tuple[
        dict[str, Any], ...
    ]
    resulting_status_by_prior_digest: dict[
        str, str
    ]
    decision_commit_seq: int
    successor_commit_seq: int
    stage_completed: bool
    stage_completion_ref: dict[str, Any] | None
    stage_completion_commit_seq: int | None
    already_resolved: bool
    next_action: str


class E2ContradictionResolutionService:
    def __init__(
        self,
        store: TransactionalHistoryStore,
        batch: StageBatch,
        inbox: StageResultInbox | None = None,
    ):
        if (
            batch.stage_id != "E2"
            or batch.phase_id != "E2-CONTRADICTION"
        ):
            raise ValidationError(
                "E2_CONTRADICTION_BATCH_REQUIRED",
                f"{batch.stage_id}/{batch.phase_id}",
            )
        if len(batch.jobs) != 1:
            raise ValidationError(
                "E2_CONTRADICTION_SINGLE_LANE_REQUIRED"
            )
        self.store = store
        self.batch = batch
        self.inbox = inbox
        self.coordinator = Coordinator(store)

    def _require_complete(self) -> None:
        if self.inbox is None:
            return
        self.inbox._load_accepted_state()
        states = tuple(
            self.inbox.lane_statuses.values()
        )
        if any(
            state.status != "ACCEPTED"
            or state.completion_status
            != "LANE_COMPLETED"
            for state in states
        ):
            raise ValidationError(
                "E2_CONTRADICTION_PHASE_NOT_COMPLETE"
            )

    def _result(
        self,
        cut: dict[str, Any],
    ) -> dict[str, Any]:
        job = next(iter(self.batch.jobs.values()))
        rows = [
            row
            for row in self.store.accepted_records(
                "bdb_audit_lane_result",
                cut,
            )
            if row["body"].get("stage_id") == "E2"
            and row["body"].get("phase_id")
            == "E2-CONTRADICTION"
            and _same_ref(
                row["body"].get("assignment_ref"),
                job.assignment_ref,
            )
        ]
        if len(rows) != 1:
            raise ValidationError(
                "E2_CONTRADICTION_RESULT_REQUIRED",
                str(len(rows)),
            )
        return rows[0]

    def _authorized_cases_and_basis(
        self,
        cut: dict[str, Any],
    ) -> tuple[
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
    ]:
        job = next(iter(self.batch.jobs.values()))
        if not job.view_manifest_ref:
            raise ValidationError(
                "E2_CONTRADICTION_VIEW_REQUIRED"
            )
        manifest = self.store.resolve_accepted(
            job.view_manifest_ref,
            cut,
        )
        if (
            manifest["body"].get("phase_id")
            != "E2-CONTRADICTION"
        ):
            raise ValidationError(
                "E2_CONTRADICTION_VIEW_PHASE_MISMATCH"
            )

        allowed: dict[str, dict[str, Any]] = {}
        cases: dict[str, dict[str, Any]] = {}
        for ref in manifest["body"].get(
            "allowed_artifact_refs",
            [],
        ):
            if not isinstance(ref, dict):
                raise ValidationError(
                    "E2_CONTRADICTION_VIEW_REF_INVALID"
                )
            record = self.store.resolve_accepted(
                ref,
                cut,
            )
            digest = record["ref"][
                "revision_digest"
            ]
            if digest in allowed:
                raise ValidationError(
                    "E2_CONTRADICTION_VIEW_DUPLICATE_REF",
                    digest,
                )
            allowed[digest] = _with_ref_class(
                record["ref"],
                "CONTENT_OR_PRIOR",
            )
            if record["ref"]["kind"] == (
                "contradiction_revision"
            ):
                status = record["body"].get(
                    "status"
                )
                if status not in {
                    "OPEN",
                    "TESTING",
                    "REOPENED",
                }:
                    raise ValidationError(
                        "E2_CONTRADICTION_CASE_NOT_OPEN",
                        str(status),
                    )
                cases[digest] = record

        if not cases:
            raise ValidationError(
                "E2_CONTRADICTION_CASE_REQUIRED"
            )
        return cases, allowed

    def _proposal_rows(
        self,
        result: dict[str, Any],
        cases: Mapping[str, dict[str, Any]],
        allowed: Mapping[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        outputs = result["body"].get(
            "outputs",
            {},
        )
        rows = (
            outputs.get(
                "contradiction_resolutions"
            )
            if isinstance(outputs, dict)
            else None
        )
        if not isinstance(rows, list):
            raise ValidationError(
                "E2_CONTRADICTION_RESOLUTIONS_REQUIRED"
            )

        proposals: dict[
            str, dict[str, Any]
        ] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValidationError(
                    "E2_CONTRADICTION_RESOLUTION_INVALID"
                )
            digest = row.get(
                "contradiction_revision_digest"
            )
            if (
                not isinstance(digest, str)
                or digest not in cases
            ):
                raise ValidationError(
                    "E2_CONTRADICTION_UNKNOWN_CASE",
                    str(digest),
                )
            if digest in proposals:
                raise ValidationError(
                    "E2_CONTRADICTION_DUPLICATE_RESOLUTION",
                    digest,
                )

            resolution_kind = row.get(
                "resolution_kind"
            )
            resulting_status = row.get(
                "resulting_status"
            )
            resolved_scope = row.get(
                "resolved_scope"
            )
            basis_digests = row.get(
                "basis_ref_digests"
            )
            rationale = row.get(
                "rationale",
                "",
            )
            if resolution_kind not in _RESOLUTION_KINDS:
                raise ValidationError(
                    "E2_CONTRADICTION_RESOLUTION_KIND_INVALID",
                    str(resolution_kind),
                )
            if resulting_status not in _RESULTING_STATUSES:
                raise ValidationError(
                    "E2_CONTRADICTION_RESULTING_STATUS_INVALID",
                    str(resulting_status),
                )
            if (
                resolution_kind == "BLOCKED"
            ) != (
                resulting_status == "BLOCKED"
            ):
                raise ValidationError(
                    "E2_CONTRADICTION_BLOCKED_SEMANTICS_MISMATCH",
                    digest,
                )
            if not isinstance(
                resolved_scope,
                dict,
            ):
                raise ValidationError(
                    "E2_CONTRADICTION_RESOLVED_SCOPE_INVALID",
                    digest,
                )
            if (
                not isinstance(
                    basis_digests,
                    list,
                )
                or not basis_digests
                or any(
                    not isinstance(item, str)
                    for item in basis_digests
                )
                or len(basis_digests)
                != len(set(basis_digests))
            ):
                raise ValidationError(
                    "E2_CONTRADICTION_BASIS_INVALID",
                    digest,
                )
            unknown = [
                item
                for item in basis_digests
                if item not in allowed
            ]
            if unknown:
                raise ValidationError(
                    "E2_CONTRADICTION_BASIS_OUTSIDE_VIEW",
                    ",".join(sorted(unknown)),
                )
            if not isinstance(rationale, str):
                raise ValidationError(
                    "E2_CONTRADICTION_RATIONALE_INVALID",
                    digest,
                )

            proposals[digest] = {
                "resolution_kind": resolution_kind,
                "resulting_status": resulting_status,
                "resolved_scope": dict(
                    resolved_scope
                ),
                "basis_refs": [
                    allowed[item]
                    for item in basis_digests
                ],
                "rationale": rationale,
            }

        missing = sorted(
            set(cases) - set(proposals)
        )
        unexpected = sorted(
            set(proposals) - set(cases)
        )
        if missing or unexpected:
            raise ValidationError(
                "E2_CONTRADICTION_RESOLUTION_SET_INCOMPLETE",
                (
                    f"missing={missing}; "
                    f"unexpected={unexpected}"
                ),
            )
        return proposals

    def _existing_decisions(
        self,
        cut: dict[str, Any],
        cases: Mapping[str, dict[str, Any]],
    ) -> dict[
        str, dict[str, Any]
    ]:
        found: dict[
            str, dict[str, Any]
        ] = {}
        for row in self.store.accepted_records(
            "contradiction_resolution_decision",
            cut,
        ):
            prior = row["body"].get(
                "contradiction_prior_revision_ref"
            )
            if not isinstance(prior, dict):
                continue
            digest = prior.get(
                "revision_digest"
            )
            if digest not in cases:
                continue
            if digest in found:
                raise ValidationError(
                    "MULTIPLE_E2_CONTRADICTION_RESOLUTIONS",
                    str(digest),
                )
            found[str(digest)] = row
        return found

    def _accept_decisions(
        self,
        *,
        cut: dict[str, Any],
        prior_commit: dict[str, Any],
        result: dict[str, Any],
        cases: Mapping[str, dict[str, Any]],
        proposals: Mapping[
            str, dict[str, Any]
        ],
    ) -> tuple[
        dict[
            str, ContradictionResolutionDecision
        ],
        int,
        bool,
    ]:
        existing = self._existing_decisions(
            cut,
            cases,
        )
        if existing:
            if set(existing) != set(cases):
                raise ValidationError(
                    "PARTIAL_E2_CONTRADICTION_RESOLUTION_DECISION_SET"
                )
            models = {
                digest: ContradictionResolutionDecision(
                    **row["body"]
                )
                for digest, row in existing.items()
            }
            seqs = {
                row["accepted_seq"]
                for row in existing.values()
            }
            if len(seqs) != 1:
                raise ValidationError(
                    "E2_CONTRADICTION_RESOLUTION_DECISION_COMMIT_DIVERGENCE"
                )
            return (
                models,
                next(iter(seqs)),
                True,
            )

        result_ref = _with_ref_class(
            result["ref"],
            "CONTENT_OR_PRIOR",
        )
        models: dict[
            str,
            ContradictionResolutionDecision,
        ] = {}
        objects: list[
            CanonicalObject
        ] = []
        for digest in sorted(cases):
            prior_model = ContradictionRevision(
                **cases[digest]["body"]
            )
            proposal = proposals[digest]
            basis_refs = canonical_reference_set(
                [
                    *proposal["basis_refs"],
                    result_ref,
                ]
            )
            decision = resolve_contradiction(
                prior_model,
                resolved_scope=proposal[
                    "resolved_scope"
                ],
                resolution_kind=proposal[
                    "resolution_kind"
                ],
                basis_refs=basis_refs,
                input_history_cut=cut,
                resulting_status=proposal[
                    "resulting_status"
                ],
            )
            models[digest] = decision
            objects.append(
                decision.as_object()
            )

        head = self.store.head()
        if head is None:
            raise ValidationError(
                "CAMPAIGN_NOT_INITIALIZED"
            )
        command = CommandEnvelope(
            command_id=_command_id(
                "e2_contradiction_decisions:"
                + result["ref"][
                    "revision_digest"
                ]
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
                "e2_contradiction_decisions:"
                + result["ref"][
                    "revision_digest"
                ]
            ),
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=objects,
            expected_head=head,
        )
        return (
            models,
            accepted.head.commit_seq,
            False,
        )

    def _existing_successors(
        self,
        cut: dict[str, Any],
        cases: Mapping[str, dict[str, Any]],
        decisions: Mapping[
            str, ContradictionResolutionDecision
        ],
    ) -> dict[
        str, dict[str, Any]
    ]:
        found: dict[
            str, dict[str, Any]
        ] = {}
        for row in self.store.accepted_records(
            "contradiction_revision",
            cut,
        ):
            predecessor = row["body"].get(
                "predecessor_contradiction_revision_ref"
            )
            resolution = row["body"].get(
                "resolution_decision_ref"
            )
            if (
                not isinstance(
                    predecessor,
                    dict,
                )
                or not isinstance(
                    resolution,
                    dict,
                )
            ):
                continue
            prior_digest = predecessor.get(
                "revision_digest"
            )
            if prior_digest not in cases:
                continue
            expected_decision = decisions[
                str(prior_digest)
            ]
            if (
                resolution.get(
                    "revision_digest"
                )
                != expected_decision.digest
            ):
                continue
            if prior_digest in found:
                raise ValidationError(
                    "MULTIPLE_E2_CONTRADICTION_SUCCESSORS",
                    str(prior_digest),
                )
            found[str(prior_digest)] = row
        return found

    def _accept_successors(
        self,
        *,
        result: dict[str, Any],
        cases: Mapping[str, dict[str, Any]],
        decisions: Mapping[
            str, ContradictionResolutionDecision
        ],
    ) -> tuple[
        dict[str, dict[str, Any]],
        int,
        bool,
    ]:
        cut, prior_commit = _current_cut(
            self.store
        )
        existing = self._existing_successors(
            cut,
            cases,
            decisions,
        )
        if existing:
            if set(existing) != set(cases):
                raise ValidationError(
                    "PARTIAL_E2_CONTRADICTION_SUCCESSOR_SET"
                )
            seqs = {
                row["accepted_seq"]
                for row in existing.values()
            }
            if len(seqs) != 1:
                raise ValidationError(
                    "E2_CONTRADICTION_SUCCESSOR_COMMIT_DIVERGENCE"
                )
            return (
                existing,
                next(iter(seqs)),
                True,
            )

        objects = []
        successors: dict[
            str, CanonicalObject
        ] = {}
        for digest in sorted(cases):
            prior = ContradictionRevision(
                **cases[digest]["body"]
            )
            successor = (
                apply_contradiction_resolution(
                    prior,
                    decisions[digest],
                )
            )
            obj = successor.as_object()
            objects.append(obj)
            successors[digest] = obj

        head = self.store.head()
        if head is None:
            raise ValidationError(
                "CAMPAIGN_NOT_INITIALIZED"
            )
        command = CommandEnvelope(
            command_id=_command_id(
                "e2_contradiction_successors:"
                + result["ref"][
                    "revision_digest"
                ]
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
                "e2_contradiction_successors:"
                + result["ref"][
                    "revision_digest"
                ]
            ),
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=objects,
            expected_head=head,
        )

        current_cut, _ = _current_cut(
            self.store
        )
        rows = {
            digest: self.store.resolve_accepted(
                obj.as_ref(
                    ref_class="CONTENT_OR_PRIOR"
                ).as_dict(),
                current_cut,
            )
            for digest, obj in successors.items()
        }
        return (
            rows,
            accepted.head.commit_seq,
            False,
        )

    def _existing_e2_stage_completion(
        self,
        cut: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = []
        for row in self.store.accepted_records(
            "stage_completion",
            cut,
        ):
            if (
                row["body"].get(
                    "completion_predicate_result"
                )
                != "STAGE_COMPLETED"
            ):
                continue
            spec = self.store.resolve_accepted(
                row["body"]["stage_spec_ref"],
                cut,
            )
            if spec["body"].get("stage_key") == "E2":
                rows.append(row)
        if len(rows) > 1:
            raise ValidationError(
                "MULTIPLE_E2_STAGE_COMPLETIONS"
            )
        return rows[0] if rows else None

    def _e2_lane_completions(
        self,
        cut: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        phases = {
            "E2-BLIND",
            "E2-REVEAL",
            "E2-SHADOW",
            "E2-CONTRADICTION",
        }
        results = [
            row
            for row in self.store.accepted_records(
                "bdb_audit_lane_result",
                cut,
            )
            if row["body"].get("stage_id") == "E2"
            and row["body"].get("phase_id") in phases
        ]
        result_digests = {
            row["ref"]["revision_digest"]
            for row in results
        }
        covered: set[str] = set()
        completions: list[dict[str, Any]] = []
        for row in self.store.accepted_records(
            "lane_completion",
            cut,
        ):
            matched = {
                ref["revision_digest"]
                for ref in row["body"].get(
                    "required_output_refs",
                    [],
                )
                if isinstance(ref, dict)
                and ref.get("kind")
                == "bdb_audit_lane_result"
                and ref.get("revision_digest")
                in result_digests
            }
            if not matched:
                continue
            if (
                row["body"].get(
                    "completion_predicate_result"
                )
                != "LANE_COMPLETED"
            ):
                raise ValidationError(
                    "E2_LANE_COMPLETION_BLOCKED"
                )
            covered.update(matched)
            completions.append(row)
        if covered != result_digests:
            raise ValidationError(
                "E2_LANE_COMPLETION_SET_INCOMPLETE",
                f"missing={sorted(result_digests - covered)}",
            )
        return tuple(completions)

    def _accept_stage_completion(
        self,
        *,
        contradiction_result: dict[str, Any],
        case_records: Mapping[
            str, dict[str, Any]
        ],
        decision_refs: tuple[
            dict[str, Any], ...
        ],
        successor_refs: tuple[
            dict[str, Any], ...
        ],
    ) -> tuple[
        dict[str, Any],
        int,
        bool,
    ]:
        cut, prior_commit = _current_cut(
            self.store
        )
        existing = (
            self._existing_e2_stage_completion(
                cut
            )
        )
        if existing is not None:
            return (
                _with_ref_class(
                    existing["ref"],
                    "CONTENT_OR_PRIOR",
                ),
                existing["accepted_seq"],
                True,
            )

        lane_completions = (
            self._e2_lane_completions(cut)
        )
        job = next(
            iter(self.batch.jobs.values())
        )
        assignment = self.store.resolve_accepted(
            job.assignment_ref,
            cut,
        )
        attempt = self.store.resolve_accepted(
            assignment["body"]["attempt_ref"],
            cut,
        )
        lane_run = self.store.resolve_accepted(
            attempt["body"]["lane_run_ref"],
            cut,
        )
        stage_run = self.store.resolve_accepted(
            lane_run["body"]["stage_run_ref"],
            cut,
        )
        stage_spec = self.store.resolve_accepted(
            assignment["body"]["stage_spec_ref"],
            cut,
        )
        if stage_spec["body"].get(
            "stage_key"
        ) != "E2":
            raise ValidationError(
                "E2_STAGE_SPEC_BINDING_MISMATCH"
            )

        main_decisions = _main_decisions(
            self.store,
            cut,
        )
        main_decision_refs = [
            _with_ref_class(
                row["ref"],
                "CONTENT_OR_PRIOR",
            )
            for row in main_decisions
        ]
        checkpoints = [
            _with_ref_class(
                row["ref"],
                "CONTENT_OR_PRIOR",
            )
            for row in self.store.accepted_records(
                "checkpoint",
                cut,
            )
            if row["body"].get("stage_id") == "E2"
            and row["body"].get("phase_id")
            == "E2-BLIND"
        ]
        shadow_results = [
            _with_ref_class(
                row["ref"],
                "CONTENT_OR_PRIOR",
            )
            for row in self.store.accepted_records(
                "bdb_audit_lane_result",
                cut,
            )
            if row["body"].get("stage_id") == "E2"
            and row["body"].get("phase_id")
            == "E2-SHADOW"
        ]
        case_refs = [
            _with_ref_class(
                row["ref"],
                "CONTENT_OR_PRIOR",
            )
            for row in case_records.values()
        ]
        required_outputs = canonical_reference_set(
            [
                *main_decision_refs,
                *checkpoints,
                *shadow_results,
                *case_refs,
                *decision_refs,
                *successor_refs,
                _with_ref_class(
                    contradiction_result["ref"],
                    "CONTENT_OR_PRIOR",
                ),
            ]
        )
        completion_refs = canonical_reference_set(
            [
                _with_ref_class(
                    row["ref"],
                    "CONTENT_OR_PRIOR",
                )
                for row in lane_completions
            ]
        )

        completion = StageCompletion(
            stage_completion_id=deterministic_id(
                "stage_completion",
                "e2-contradiction-final:"
                + ":".join(
                    ref["revision_digest"]
                    for ref in required_outputs
                ),
            ),
            stage_run_ref=_with_ref_class(
                stage_run["ref"],
                "CONTENT_OR_PRIOR",
            ),
            stage_spec_ref=_with_ref_class(
                stage_spec["ref"],
                "HISTORY_CONTEXT_BINDING",
            ),
            input_history_cut=cut,
            required_lane_slot_results=(
                completion_refs
            ),
            required_output_refs=(
                required_outputs
            ),
            mandatory_obligation_summary={
                "blind_phase_required": True,
                "controlled_reveal_required": True,
                "shadow_adjudicator_required": True,
                "contradiction_protocol_required": True,
                "contradiction_cases": len(
                    case_records
                ),
                "contradiction_cases_resolved_full": len(
                    successor_refs
                ),
                "majority_vote_forbidden": True,
            },
            unresolved_material_refs=[],
            unknown_blocked_summary={
                "unknown_surfaces_count": 0,
                "scope_note": (
                    "E2 completion is stage-local and "
                    "does not imply global STOP PASS"
                ),
            },
            completion_predicate_result=(
                "STAGE_COMPLETED"
            ),
        )
        obj = completion.as_object()
        head = self.store.head()
        if head is None:
            raise ValidationError(
                "CAMPAIGN_NOT_INITIALIZED"
            )
        command = CommandEnvelope(
            command_id=_command_id(
                "e2_contradiction_stage_completion:"
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
                "e2_contradiction_stage_completion:"
                + obj.digest
            ),
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=[obj],
            expected_head=head,
        )
        return (
            obj.as_ref(
                ref_class="CONTENT_OR_PRIOR"
            ).as_dict(),
            accepted.head.commit_seq,
            False,
        )

    def resolve(
        self,
    ) -> E2ContradictionResolutionSummary:
        self._require_complete()
        cut, prior_commit = _current_cut(
            self.store
        )
        result = self._result(cut)
        cases, allowed = (
            self._authorized_cases_and_basis(
                cut
            )
        )
        proposals = self._proposal_rows(
            result,
            cases,
            allowed,
        )

        decisions, decision_seq, decision_existed = (
            self._accept_decisions(
                cut=cut,
                prior_commit=prior_commit,
                result=result,
                cases=cases,
                proposals=proposals,
            )
        )
        successors, successor_seq, successor_existed = (
            self._accept_successors(
                result=result,
                cases=cases,
                decisions=decisions,
            )
        )

        decision_refs = tuple(
            canonical_reference_set(
                [
                    decision.as_object().as_ref(
                        ref_class="CONTENT_OR_PRIOR"
                    ).as_dict()
                    for decision in decisions.values()
                ]
            )
        )
        successor_refs = tuple(
            canonical_reference_set(
                [
                    _with_ref_class(
                        row["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                    for row in successors.values()
                ]
            )
        )
        statuses = {
            digest: row["body"].get(
                "status",
                "",
            )
            for digest, row in successors.items()
        }
        all_full = all(
            status == "RESOLVED_FULL"
            for status in statuses.values()
        )
        stage_ref = None
        stage_seq = None
        stage_existed = False
        if all_full:
            (
                stage_ref,
                stage_seq,
                stage_existed,
            ) = self._accept_stage_completion(
                contradiction_result=result,
                case_records=cases,
                decision_refs=decision_refs,
                successor_refs=successor_refs,
            )

        return E2ContradictionResolutionSummary(
            campaign_id=self.batch.campaign_id,
            decision_refs=decision_refs,
            successor_contradiction_refs=(
                successor_refs
            ),
            resulting_status_by_prior_digest=(
                statuses
            ),
            decision_commit_seq=decision_seq,
            successor_commit_seq=(
                successor_seq
            ),
            stage_completed=all_full,
            stage_completion_ref=stage_ref,
            stage_completion_commit_seq=(
                stage_seq
            ),
            already_resolved=(
                decision_existed
                and successor_existed
                and (
                    not all_full
                    or stage_existed
                )
            ),
            next_action=(
                "PREPARE_E3"
                if all_full
                else "E2_CONTRADICTION_REMAINS_BLOCKING"
            ),
        )


__all__ = [
    "E2ContradictionResolutionSummary",
    "E2ContradictionResolutionService",
]
