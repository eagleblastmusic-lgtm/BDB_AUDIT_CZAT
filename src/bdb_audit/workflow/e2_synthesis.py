"""Main E2 per-claim synthesis after controlled reveal.

Each E1 historical finding is reconstructed as an individual canonical
FindingClaimRevision and receives four axis assessments plus an adjudication
decision.  External E2 reveal results remain accepted proposals: without
canonical EvidenceQualificationAssessment refs they cannot upgrade a canonical
axis to SUPPORTED/REFUTED.  The proposal results are retained as
method/characterization refs, while the canonical axis stays INCONCLUSIVE and
the finding stays OPEN.

This service intentionally does *not* merge root causes, resolve
contradictions, or accept StageCompletion.  Those are later E2 steps, including
the independent shadow adjudicator required by the R5.3 plan.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..adjudication.models import (
    FindingAdjudicationDecision,
    FindingAxisAssessment,
    FindingClaimRevision,
)
from ..coordinator import Coordinator
from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, CommandEnvelope
from ..history.store import TransactionalHistoryStore
from .assignments import _command_id, _current_cut, _external_ref
from .e2_reveal import opaque_claim_view_id
from .inbox import _same_ref, _with_ref_class
from .manual_stage import StageBatch, StageResultInbox


_AXES = ("MECHANISM", "REACHABILITY", "IMPACT", "SEVERITY")
_OUTCOMES = {
    "SUPPORTED",
    "REFUTED",
    "INCONCLUSIVE",
    "BLOCKED",
    "NOT_APPLICABLE",
}


@dataclass(frozen=True)
class E2MainSynthesisSummary:
    campaign_id: str
    stage_id: str
    phase_id: str
    claim_refs: dict[str, dict[str, Any]]
    axis_assessment_refs: dict[str, dict[str, dict[str, Any]]]
    adjudication_decision_refs: dict[str, dict[str, Any]]
    proposal_disagreement_claim_ids: tuple[str, ...]
    accepted_commit_seq: int
    already_synthesized: bool


@dataclass(frozen=True)
class _ClaimSource:
    opaque_id: str
    result_record: dict[str, Any]
    finding_index: int
    finding: dict[str, Any]
    discovery_ref: dict[str, Any]


def _typed_refs(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, (list, tuple)) else [value]
    required = {
        "kind",
        "revision_digest",
        "digest_profile",
        "schema_revision_ref",
    }
    return [
        dict(item)
        for item in values
        if isinstance(item, dict)
        and required.issubset(item)
    ]


def _claim_statement(finding: Mapping[str, Any]) -> str:
    for key in ("statement", "claim"):
        value = finding.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValidationError("E2_CLAIM_STATEMENT_REQUIRED")


class E2MainSynthesisService:
    """Synthesize individual E1 claims from completed E2 controlled reveal."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
        reveal_batch: StageBatch,
        reveal_inbox: StageResultInbox | None = None,
    ):
        if (
            reveal_batch.stage_id != "E2"
            or reveal_batch.phase_id != "E2-REVEAL"
        ):
            raise ValidationError(
                "E2_REVEAL_BATCH_REQUIRED",
                f"{reveal_batch.stage_id}/{reveal_batch.phase_id}",
            )
        self.store = store
        self.batch = reveal_batch
        self.inbox = reveal_inbox
        self.coordinator = Coordinator(store)

    def _require_phase_complete(self) -> None:
        if self.inbox is None:
            return
        self.inbox._load_accepted_state()
        missing = [
            slot
            for slot, state in self.inbox.lane_statuses.items()
            if state.status != "ACCEPTED"
        ]
        blocked = [
            slot
            for slot, state in self.inbox.lane_statuses.items()
            if state.status == "ACCEPTED"
            and state.completion_status != "LANE_COMPLETED"
        ]
        if missing or blocked:
            raise ValidationError(
                "E2_REVEAL_PHASE_NOT_COMPLETE",
                f"missing={missing}; blocked={blocked}",
            )

    def _claim_sources(
        self,
        cut: dict[str, Any],
    ) -> dict[str, _ClaimSource]:
        discoveries = tuple(
            self.store.accepted_records("discovery_record", cut)
        )
        sources: dict[str, _ClaimSource] = {}
        for result in self.store.accepted_records(
            "bdb_audit_lane_result",
            cut,
        ):
            body = result["body"]
            if body.get("stage_id") != "E1":
                continue
            slot = body.get("lane_slot")
            findings = body.get("findings", [])
            if not isinstance(slot, str) or not isinstance(findings, list):
                raise ValidationError("INVALID_E1_RESULT_FOR_E2_SYNTHESIS")
            for index, finding in enumerate(findings):
                if not isinstance(finding, dict):
                    raise ValidationError("INVALID_FINDING_STRUCTURE", slot)
                opaque_id = opaque_claim_view_id(
                    result["ref"]["revision_digest"],
                    index,
                    finding,
                )
                expected_discovery_id = (
                    f"disc_E1_{slot}_"
                    f"{result['ref']['revision_digest'][:12]}_"
                    f"{index + 1}"
                )
                matches = [
                    row
                    for row in discoveries
                    if row["body"].get("discovery_id")
                    == expected_discovery_id
                ]
                if len(matches) != 1:
                    raise ValidationError(
                        "E1_DISCOVERY_RELATION_REQUIRED",
                        expected_discovery_id,
                    )
                if opaque_id in sources:
                    raise ValidationError(
                        "DUPLICATE_OPAQUE_CLAIM_VIEW_ID",
                        opaque_id,
                    )
                sources[opaque_id] = _ClaimSource(
                    opaque_id=opaque_id,
                    result_record=result,
                    finding_index=index,
                    finding=dict(finding),
                    discovery_ref=_with_ref_class(
                        matches[0]["ref"],
                        "CONTENT_OR_PRIOR",
                    ),
                )
        if not sources:
            raise ValidationError("E1_RESULT_CORPUS_REQUIRED")
        return sources

    def _reveal_results(
        self,
        cut: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for slot, job in self.batch.jobs.items():
            matches = [
                row
                for row in self.store.accepted_records(
                    "bdb_audit_lane_result",
                    cut,
                )
                if row["body"].get("stage_id") == "E2"
                and row["body"].get("phase_id") == "E2-REVEAL"
                and _same_ref(
                    row["body"].get("assignment_ref"),
                    job.assignment_ref,
                )
            ]
            if len(matches) != 1:
                raise ValidationError(
                    "E2_REVEAL_RESULT_SET_INCOMPLETE",
                    f"{slot}: expected 1, got {len(matches)}",
                )
            results[slot] = matches[0]
        return results

    def _proposal_matrix(
        self,
        reveal_results: Mapping[str, dict[str, Any]],
        expected_claim_ids: Sequence[str],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        expected = set(expected_claim_ids)
        matrix: dict[str, dict[str, dict[str, Any]]] = {
            claim_id: {} for claim_id in expected_claim_ids
        }
        for slot, result in reveal_results.items():
            outputs = result["body"].get("outputs", {})
            assessments = (
                outputs.get("claim_assessments")
                if isinstance(outputs, dict)
                else None
            )
            if not isinstance(assessments, list):
                raise ValidationError(
                    "E2_REVEAL_CLAIM_ASSESSMENTS_REQUIRED",
                    slot,
                )
            seen: set[str] = set()
            for item in assessments:
                if not isinstance(item, dict):
                    raise ValidationError(
                        "E2_REVEAL_ASSESSMENT_INVALID",
                        slot,
                    )
                claim_id = item.get("opaque_claim_view_id")
                if not isinstance(claim_id, str) or claim_id not in expected:
                    raise ValidationError(
                        "E2_REVEAL_UNKNOWN_CLAIM_ID",
                        str(claim_id),
                    )
                if claim_id in seen:
                    raise ValidationError(
                        "E2_REVEAL_DUPLICATE_CLAIM_ASSESSMENT",
                        claim_id,
                    )
                seen.add(claim_id)

                claim_outcome = item.get("claim_outcome")
                if claim_outcome not in _OUTCOMES:
                    raise ValidationError(
                        "E2_REVEAL_CLAIM_OUTCOME_INVALID",
                        claim_id,
                    )
                axes = item.get("axis_outcomes")
                if not isinstance(axes, dict) or set(axes) != set(_AXES):
                    raise ValidationError(
                        "E2_REVEAL_AXIS_SET_INVALID",
                        claim_id,
                    )
                if any(value not in _OUTCOMES for value in axes.values()):
                    raise ValidationError(
                        "E2_REVEAL_AXIS_OUTCOME_INVALID",
                        claim_id,
                    )
                rationale = item.get("rationale", "")
                if not isinstance(rationale, str):
                    raise ValidationError(
                        "E2_REVEAL_RATIONALE_INVALID",
                        claim_id,
                    )
                matrix[claim_id][slot] = {
                    "claim_outcome": claim_outcome,
                    "axis_outcomes": dict(axes),
                    "rationale": rationale,
                    "result_ref": _with_ref_class(
                        result["ref"],
                        "CONTENT_OR_PRIOR",
                    ),
                }

            if seen != expected:
                missing = sorted(expected - seen)
                raise ValidationError(
                    "E2_REVEAL_ASSESSMENT_INCOMPLETE",
                    f"{slot}: missing={missing}",
                )
        return matrix

    @staticmethod
    def _proposal_disagrees(
        rows: Mapping[str, dict[str, Any]],
    ) -> bool:
        claim_outcomes = {
            row["claim_outcome"]
            for row in rows.values()
        }
        if len(claim_outcomes) > 1:
            return True
        for axis in _AXES:
            values = {
                row["axis_outcomes"][axis]
                for row in rows.values()
            }
            if len(values) > 1:
                return True
        return False

    def _existing(
        self,
        cut: dict[str, Any],
        expected_claim_ids: Sequence[str],
    ) -> E2MainSynthesisSummary | None:
        decisions = tuple(
            self.store.accepted_records(
                "finding_adjudication_decision",
                cut,
            )
        )
        found: dict[str, dict[str, Any]] = {}
        for opaque_id in expected_claim_ids:
            expected_id = deterministic_id(
                "finding_adjudication_decision",
                "e2-main-decision:" + opaque_id,
            )
            matches = [
                row
                for row in decisions
                if row["body"].get("decision_id") == expected_id
            ]
            if len(matches) > 1:
                raise ValidationError(
                    "MULTIPLE_E2_MAIN_DECISIONS",
                    opaque_id,
                )
            if matches:
                found[opaque_id] = matches[0]
        if not found:
            return None
        if set(found) != set(expected_claim_ids):
            raise ValidationError(
                "PARTIAL_E2_MAIN_SYNTHESIS",
                f"found={sorted(found)}",
            )

        claim_refs: dict[str, dict[str, Any]] = {}
        axis_refs: dict[str, dict[str, dict[str, Any]]] = {}
        decision_refs: dict[str, dict[str, Any]] = {}
        seqs: set[int] = set()
        for opaque_id, decision in found.items():
            seqs.add(decision["accepted_seq"])
            body = decision["body"]
            claim_refs[opaque_id] = dict(body["claim_revision_ref"])
            axis_refs[opaque_id] = {
                "MECHANISM": dict(body["mechanism_assessment_ref"]),
                "REACHABILITY": dict(body["reachability_assessment_ref"]),
                "IMPACT": dict(body["impact_assessment_ref"]),
                "SEVERITY": dict(body["severity_assessment_ref"]),
            }
            decision_refs[opaque_id] = _with_ref_class(
                decision["ref"],
                "CONTENT_OR_PRIOR",
            )
        if len(seqs) != 1:
            raise ValidationError("E2_MAIN_SYNTHESIS_COMMIT_DIVERGENCE")
        return E2MainSynthesisSummary(
            campaign_id=self.batch.campaign_id,
            stage_id="E2",
            phase_id="E2-MAIN-SYNTHESIS",
            claim_refs=claim_refs,
            axis_assessment_refs=axis_refs,
            adjudication_decision_refs=decision_refs,
            proposal_disagreement_claim_ids=(),
            accepted_commit_seq=next(iter(seqs)),
            already_synthesized=True,
        )

    def synthesize(self) -> E2MainSynthesisSummary:
        self._require_phase_complete()
        cut, prior_commit = _current_cut(self.store)
        claim_sources = self._claim_sources(cut)
        existing = self._existing(
            cut,
            tuple(sorted(claim_sources)),
        )
        if existing is not None:
            return existing

        reveal_results = self._reveal_results(cut)
        matrix = self._proposal_matrix(
            reveal_results,
            tuple(sorted(claim_sources)),
        )

        source_rows = tuple(
            self.store.accepted_records(
                "source_generation",
                cut,
            )
        )
        if len(source_rows) != 1:
            raise ValidationError(
                "SOURCE_GENERATION_AMBIGUOUS",
                str(len(source_rows)),
            )
        source_ref = _with_ref_class(
            source_rows[0]["ref"],
            "CONTENT_OR_PRIOR",
        )
        assessment_policy_ref = _external_ref(
            "external_profile_ref",
            "E2_MAIN_ADJUDICATION_POLICY_R5_3",
            "HISTORY_CONTEXT_BINDING",
        )
        adjudicator_ref = _external_ref(
            "actor_or_authority_ref",
            "trusted_coordinator_e2_main",
            "CONTENT_OR_PRIOR",
        )

        objects: list[CanonicalObject] = []
        claim_refs: dict[str, dict[str, Any]] = {}
        axis_refs: dict[str, dict[str, dict[str, Any]]] = {}
        decision_refs: dict[str, dict[str, Any]] = {}
        disagreements: list[str] = []

        for opaque_id in sorted(claim_sources):
            source = claim_sources[opaque_id]
            finding = source.finding
            scope_refs = canonical_reference_set(
                _typed_refs(
                    finding.get("scope_refs")
                    or finding.get("scope_ref")
                    or []
                )
            )
            invariant_refs = canonical_reference_set(
                _typed_refs(
                    finding.get("violated_invariant_refs")
                    or finding.get("violated_invariant_ref")
                    or finding.get("invariant_ref")
                    or []
                )
            )
            claim = FindingClaimRevision(
                statement=_claim_statement(finding),
                source_generation_ref=source_ref,
                scope_refs=scope_refs,
                violated_invariant_refs=invariant_refs,
                discovery_relation_refs=[
                    source.discovery_ref
                ],
                claim_id=deterministic_id(
                    "finding_claim_revision",
                    "e2-main-claim:" + opaque_id,
                ),
            )
            claim_obj = claim.as_object()
            objects.append(claim_obj)
            claim_ref = claim_obj.as_ref(
                ref_class="CONTENT_OR_PRIOR"
            ).as_dict()
            claim_refs[opaque_id] = claim_ref

            proposals = matrix[opaque_id]
            proposal_refs = canonical_reference_set(
                [
                    row["result_ref"]
                    for row in proposals.values()
                ]
            )
            if self._proposal_disagrees(proposals):
                disagreements.append(opaque_id)

            per_axis: dict[str, FindingAxisAssessment] = {}
            axis_refs[opaque_id] = {}
            for axis in _AXES:
                proposed_values = sorted(
                    {
                        row["axis_outcomes"][axis]
                        for row in proposals.values()
                    }
                )
                assessment = FindingAxisAssessment(
                    claim_revision_ref=claim_ref,
                    assessment_input_history_cut=cut,
                    assessment_policy_ref=assessment_policy_ref,
                    axis=axis,
                    epistemic_outcome="INCONCLUSIVE",
                    method=(
                        "E2_EXTERNAL_PROPOSALS_"
                        + "_".join(proposed_values)
                        + "_NO_QUALIFIED_EVIDENCE"
                    ),
                    evidence_qualification_refs=(),
                    method_or_characterization_refs=proposal_refs,
                    assessment_id=deterministic_id(
                        "finding_axis_assessment",
                        f"e2-main-axis:{opaque_id}:{axis}",
                    ),
                )
                assessment_obj = assessment.as_object()
                objects.append(assessment_obj)
                axis_refs[opaque_id][axis] = (
                    assessment_obj.as_ref(
                        ref_class="CONTENT_OR_PRIOR"
                    ).as_dict()
                )
                per_axis[axis] = assessment

            knowledge_refs = canonical_reference_set(
                [
                    _with_ref_class(
                        job.authorized_knowledge_state_ref,
                        "CONTENT_OR_PRIOR",
                    )
                    for job in self.batch.jobs.values()
                    if job.authorized_knowledge_state_ref
                ]
            )
            decision = FindingAdjudicationDecision(
                claim_revision_ref=claim_ref,
                input_history_cut=cut,
                adjudicator_ref=adjudicator_ref,
                mechanism_assessment_ref=axis_refs[
                    opaque_id
                ]["MECHANISM"],
                reachability_assessment_ref=axis_refs[
                    opaque_id
                ]["REACHABILITY"],
                impact_assessment_ref=axis_refs[
                    opaque_id
                ]["IMPACT"],
                severity_assessment_ref=axis_refs[
                    opaque_id
                ]["SEVERITY"],
                lifecycle_status="OPEN",
                evidence_qualification_refs=(),
                knowledge_state_refs=knowledge_refs,
                decision_id=deterministic_id(
                    "finding_adjudication_decision",
                    "e2-main-decision:" + opaque_id,
                ),
            )
            decision_obj = decision.as_object()
            objects.append(decision_obj)
            decision_refs[opaque_id] = (
                decision_obj.as_ref(
                    ref_class="CONTENT_OR_PRIOR"
                ).as_dict()
            )

        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        command = CommandEnvelope(
            command_id=_command_id(
                "e2_main_synthesis:"
                + ":".join(sorted(decision_refs))
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
                "e2_main_synthesis:"
                + ":".join(sorted(decision_refs))
            ),
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=objects,
            expected_head=head,
        )

        return E2MainSynthesisSummary(
            campaign_id=self.batch.campaign_id,
            stage_id="E2",
            phase_id="E2-MAIN-SYNTHESIS",
            claim_refs=claim_refs,
            axis_assessment_refs=axis_refs,
            adjudication_decision_refs=decision_refs,
            proposal_disagreement_claim_ids=tuple(
                sorted(disagreements)
            ),
            accepted_commit_seq=accepted.head.commit_seq,
            already_synthesized=False,
        )


__all__ = [
    "E2MainSynthesisSummary",
    "E2MainSynthesisService",
]
