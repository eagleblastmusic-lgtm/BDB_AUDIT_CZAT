"""Validation of accepted E3 gap-directed result proposals.

This service is deliberately non-authoritative about coverage.  It verifies that
external E3-GAP results stayed inside the accepted positive ViewManifest and
that every authorized gap target was addressed by at least one completed lane.
It also rejects attempts to relabel post-reveal findings as blind discoveries.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .assignments import _current_cut
from .inbox import _same_ref, _with_ref_class
from .manual_stage import StageBatch, StageResultInbox


_ALLOWED_TARGET_KINDS = {
    "coverage_obligation": "COVERAGE_OBLIGATION",
    "scope_state_record": "SCOPE_GAP",
}
_ALLOWED_STATUSES = {
    "EXPLORED",
    "BLOCKED",
    "NO_MATERIAL_DISCOVERY",
}


@dataclass(frozen=True)
class E3GapValidationSummary:
    campaign_id: str
    authorized_target_digests: tuple[str, ...]
    covered_target_digests: tuple[str, ...]
    result_refs: tuple[dict[str, Any], ...]
    findings_count: int
    next_action: str


class E3GapResultValidationService:
    def __init__(
        self,
        store: TransactionalHistoryStore,
        batch: StageBatch,
        inbox: StageResultInbox | None = None,
    ):
        if (
            batch.stage_id != "E3"
            or batch.phase_id != "E3-GAP"
        ):
            raise ValidationError(
                "E3_GAP_BATCH_REQUIRED",
                f"{batch.stage_id}/{batch.phase_id}",
            )
        self.store = store
        self.batch = batch
        self.inbox = inbox

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
                "E3_GAP_PHASE_NOT_COMPLETE"
            )

    def _authorized_targets(
        self,
        cut: dict[str, Any],
    ) -> dict[str, str]:
        manifest_refs = {
            job.view_manifest_ref.get(
                "revision_digest"
            )
            for job in self.batch.jobs.values()
            if job.view_manifest_ref
        }
        manifest_refs.discard(None)
        if len(manifest_refs) != 1:
            raise ValidationError(
                "E3_GAP_VIEW_BINDING_REQUIRED"
            )
        digest = next(iter(manifest_refs))
        rows = [
            row
            for row in self.store.accepted_records(
                "view_manifest",
                cut,
            )
            if row["ref"]["revision_digest"] == digest
            and row["body"].get("phase_id")
            == "E3-GAP"
        ]
        if len(rows) != 1:
            raise ValidationError(
                "E3_GAP_VIEW_BINDING_REQUIRED"
            )
        manifest = rows[0]

        targets: dict[str, str] = {}
        for ref in manifest["body"].get(
            "allowed_artifact_refs",
            [],
        ):
            if not isinstance(ref, dict):
                continue
            kind = ref.get("kind")
            if kind not in _ALLOWED_TARGET_KINDS:
                continue
            ref_digest = ref.get(
                "revision_digest"
            )
            if not isinstance(
                ref_digest,
                str,
            ):
                continue
            targets[ref_digest] = (
                _ALLOWED_TARGET_KINDS[kind]
            )
        if not targets:
            raise ValidationError(
                "E3_GAP_TARGET_SET_EMPTY"
            )
        return targets

    def _accepted_results(
        self,
        cut: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        result_rows = []
        for slot, job in self.batch.jobs.items():
            matches = [
                row
                for row in self.store.accepted_records(
                    "bdb_audit_lane_result",
                    cut,
                )
                if row["body"].get("stage_id")
                == "E3"
                and row["body"].get("phase_id")
                == "E3-GAP"
                and _same_ref(
                    row["body"].get(
                        "assignment_ref"
                    ),
                    job.assignment_ref,
                )
            ]
            if len(matches) != 1:
                raise ValidationError(
                    "E3_GAP_RESULT_SET_INCOMPLETE",
                    (
                        f"{slot}: expected 1 accepted "
                        f"result, got {len(matches)}"
                    ),
                )
            result_rows.append(matches[0])
        return tuple(result_rows)

    def validate(
        self,
    ) -> E3GapValidationSummary:
        self._require_complete()
        cut, _ = _current_cut(self.store)
        targets = self._authorized_targets(cut)
        results = self._accepted_results(cut)

        covered: set[str] = set()
        findings_count = 0

        for result in results:
            findings = result["body"].get(
                "findings",
                [],
            )
            if not isinstance(findings, list):
                raise ValidationError(
                    "INVALID_FINDING_STRUCTURE",
                    "E3-GAP",
                )
            for finding in findings:
                if not isinstance(finding, dict):
                    raise ValidationError(
                        "INVALID_FINDING_STRUCTURE",
                        "E3-GAP",
                    )
                if finding.get("classification") in {
                    "PRE_REVEAL_DISCOVERY",
                    "BLIND_NOVELTY",
                }:
                    raise ValidationError(
                        "POST_REVEAL_DISCOVERY_MISCLASSIFIED_AS_BLIND"
                    )
            findings_count += len(findings)

            outputs = result["body"].get(
                "outputs",
                {},
            )
            rows = (
                outputs.get(
                    "gap_target_results"
                )
                if isinstance(outputs, dict)
                else None
            )
            if not isinstance(rows, list):
                raise ValidationError(
                    "E3_GAP_TARGET_RESULTS_REQUIRED"
                )
            seen_in_result: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValidationError(
                        "E3_GAP_TARGET_RESULT_INVALID"
                    )
                target_digest = row.get(
                    "target_ref_digest"
                )
                if (
                    not isinstance(
                        target_digest,
                        str,
                    )
                    or target_digest
                    not in targets
                ):
                    raise ValidationError(
                        "E3_GAP_TARGET_OUTSIDE_AUTHORIZED_VIEW",
                        str(target_digest),
                    )
                if target_digest in seen_in_result:
                    raise ValidationError(
                        "E3_GAP_DUPLICATE_TARGET_RESULT",
                        target_digest,
                    )
                seen_in_result.add(
                    target_digest
                )
                if row.get("target_kind") != (
                    targets[target_digest]
                ):
                    raise ValidationError(
                        "E3_GAP_TARGET_KIND_MISMATCH",
                        target_digest,
                    )
                if row.get("status") not in (
                    _ALLOWED_STATUSES
                ):
                    raise ValidationError(
                        "E3_GAP_STATUS_INVALID",
                        target_digest,
                    )
                rationale = row.get(
                    "rationale",
                    "",
                )
                if not isinstance(rationale, str):
                    raise ValidationError(
                        "E3_GAP_RATIONALE_INVALID",
                        target_digest,
                    )
                indexes = row.get(
                    "discovery_indexes",
                    [],
                )
                if (
                    not isinstance(indexes, list)
                    or any(
                        not isinstance(index, int)
                        or isinstance(index, bool)
                        or index < 0
                        or index >= len(findings)
                        for index in indexes
                    )
                    or len(indexes)
                    != len(set(indexes))
                ):
                    raise ValidationError(
                        "E3_GAP_DISCOVERY_INDEX_INVALID",
                        target_digest,
                    )
                if (
                    row.get("status")
                    == "NO_MATERIAL_DISCOVERY"
                    and indexes
                ):
                    raise ValidationError(
                        "E3_GAP_NO_DISCOVERY_STATUS_CONFLICT",
                        target_digest,
                    )
                covered.add(target_digest)

        missing = sorted(
            set(targets) - covered
        )
        if missing:
            raise ValidationError(
                "E3_GAP_TARGET_SET_INCOMPLETE",
                ",".join(missing),
            )

        return E3GapValidationSummary(
            campaign_id=self.batch.campaign_id,
            authorized_target_digests=tuple(
                sorted(targets)
            ),
            covered_target_digests=tuple(
                sorted(covered)
            ),
            result_refs=tuple(
                _with_ref_class(
                    row["ref"],
                    "CONTENT_OR_PRIOR",
                )
                for row in results
            ),
            findings_count=findings_count,
            next_action=(
                "PREPARE_E3_CUMULATIVE_CORPUS_REVEAL"
            ),
        )


__all__ = [
    "E3GapResultValidationService",
    "E3GapValidationSummary",
]
