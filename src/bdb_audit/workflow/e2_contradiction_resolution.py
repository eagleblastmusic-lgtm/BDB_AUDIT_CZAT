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
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, CommandEnvelope
from ..history.store import TransactionalHistoryStore
from .assignments import _command_id, _current_cut
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
            already_resolved=(
                decision_existed
                and successor_existed
            ),
            next_action=(
                "FINALIZE_E2"
                if all_full
                else "E2_CONTRADICTION_REMAINS_BLOCKING"
            ),
        )


__all__ = [
    "E2ContradictionResolutionSummary",
    "E2ContradictionResolutionService",
]
