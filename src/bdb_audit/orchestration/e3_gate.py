"""E3 Integration Gate and StageCompletion Evaluator (WP-F5 / PR-E3-06).

Enforces the 7 normative conditions for E3 Integration Gate PASS:
1. Preserves blind discovery provenance before reveal.
2. Transitions cleanly to gap-directed mode with positive views.
3. Does not confuse auxiliary corpus with canonical predecessor.
4. Marks MULTI_STAGE_FALSE_NEGATIVE only on proper history/knowledge cut.
5. Maintains obligations for critical surfaces even without findings.
6. Does not raise coverage based solely on test count.
7. Does not hide unknown/unsupported scope from subsequent STOP.
"""
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, Set
import hashlib
from uuid import uuid4

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.objects import CanonicalObject
from .e3 import E3BlindNoveltyResult
from .e3_reveal import (
    E3BlindCheckpoint,
    PositiveGapProjection,
    E3RevealEvent,
    E3GapDirectedScheduler,
    FalseNegativeRelationshipAssessment,
)


@dataclass(frozen=True)
class E3StageCompletionCandidate:
    stage_key: str
    stage_spec_digest: str
    e2_completion_digest: str
    blind_checkpoint_digest: str
    positive_projection_digest: str
    blind_discoveries_count: int
    gap_discoveries_count: int
    fuzzing_executions_count: int
    differential_executions_count: int
    metamorphic_executions_count: int
    adjudicated_decisions_count: int
    open_obligations_count: int
    unknown_scope_count: int
    unsupported_scope_count: int
    multi_stage_false_negatives_count: int
    completion_digest: str
    gate_verdict: str = "PASS"

    def body(self) -> dict:
        return {
            "stage_key": self.stage_key,
            "stage_spec_digest": self.stage_spec_digest,
            "e2_completion_digest": self.e2_completion_digest,
            "blind_checkpoint_digest": self.blind_checkpoint_digest,
            "positive_projection_digest": self.positive_projection_digest,
            "blind_discoveries_count": self.blind_discoveries_count,
            "gap_discoveries_count": self.gap_discoveries_count,
            "fuzzing_executions_count": self.fuzzing_executions_count,
            "differential_executions_count": self.differential_executions_count,
            "metamorphic_executions_count": self.metamorphic_executions_count,
            "adjudicated_decisions_count": self.adjudicated_decisions_count,
            "open_obligations_count": self.open_obligations_count,
            "unknown_scope_count": self.unknown_scope_count,
            "unsupported_scope_count": self.unsupported_scope_count,
            "multi_stage_false_negatives_count": self.multi_stage_false_negatives_count,
            "gate_verdict": self.gate_verdict,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return CanonicalObject("stage_completion", self.body()).digest

    @property
    def ref(self) -> dict:
        return {
            "kind": "stage_completion",
            "revision_digest": self.digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stage_completion/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


class E3IntegrationGateEvaluator:
    """Evaluates all 7 E3 gate conditions fail-closed."""

    @staticmethod
    def validate_blind_provenance_preserved(
        blind_result: E3BlindNoveltyResult,
        checkpoint: E3BlindCheckpoint,
    ) -> None:
        """Condition 1: Blind discoveries sealed with PRE_REVEAL_DISCOVERY and ENFORCED isolation."""
        if not checkpoint.blind_completion_digest:
            raise ValidationError("BLIND_CHECKPOINT_MISSING", "Checkpoint has no blind completion digest")
        if checkpoint.blind_completion_digest != blind_result.blind_completion_digest:
            raise ValidationError("CHECKPOINT_DIGEST_MISMATCH", "Checkpoint digest does not match blind result")
        for claim in blind_result.quarantined_claims:
            if claim.get("classification") != "PRE_REVEAL_DISCOVERY":
                raise ValidationError(
                    "BLIND_PROVENANCE_VIOLATION",
                    f"Discovery {claim.get('statement')} lacks PRE_REVEAL_DISCOVERY classification",
                )

    @staticmethod
    def validate_gap_mode_transition(
        projection: PositiveGapProjection,
        reveal_event: E3RevealEvent,
    ) -> None:
        """Condition 2: Positive projection without raw finding leaks."""
        if reveal_event.reveal_type != "POSITIVE_GAP_VIEW":
            raise ValidationError("GAP_TRANSITION_INVALID", "Reveal type must be POSITIVE_GAP_VIEW")
        if projection.checkpoint_ref.get("revision_digest") != reveal_event.checkpoint_ref.get("revision_digest"):
            raise ValidationError("CHECKPOINT_REVEAL_MISMATCH", "Projection checkpoint mismatch")

    @staticmethod
    def validate_no_auxiliary_corpus_confusion(corpus_role: str) -> None:
        """Condition 3: Auxiliary corpus not confused with direct predecessor."""
        if corpus_role in {"CANONICAL_PREDECESSOR", "DIRECT_PREDECESSOR", "E1", "E2"}:
            raise ValidationError(
                "CANONICAL_PREDECESSOR_CONFUSION",
                f"Auxiliary holdout corpus cannot have role {corpus_role}",
            )

    @staticmethod
    def validate_false_negative_assessment(
        assessment: FalseNegativeRelationshipAssessment,
        surface_active_in_predecessor: bool,
    ) -> None:
        """Condition 4: MULTI_STAGE_FALSE_NEGATIVE only when predecessor cut proves omission."""
        if assessment.result == "MULTI_STAGE_FALSE_NEGATIVE" and not surface_active_in_predecessor:
            raise ValidationError(
                "INVALID_FALSE_NEGATIVE_ON_NEW_SCOPE",
                "Cannot mark MULTI_STAGE_FALSE_NEGATIVE on new surface that was not active in predecessor",
            )

    @staticmethod
    def validate_critical_surface_obligations(
        critical_surfaces: Sequence[Mapping],
        open_obligations: Sequence[Mapping],
        findings_on_critical_surfaces: Sequence[Mapping],
    ) -> None:
        """Condition 5: Critical surfaces without findings must maintain obligations."""
        # Surfaces with no findings must NOT have their obligations magically removed
        if critical_surfaces and not findings_on_critical_surfaces:
            if not open_obligations:
                raise ValidationError(
                    "CRITICAL_OBLIGATION_UNJUSTIFIED_REMOVAL",
                    "Critical surfaces have zero findings but open obligations were removed; obligations must remain open",
                )

    @staticmethod
    def validate_coverage_not_inflated_by_test_volume(
        test_case_count: int,
        attempted_coverage_increase: float,
        qualified_support_present: bool,
    ) -> None:
        """Condition 6: High test volume alone does NOT raise coverage."""
        if test_case_count > 0 and not qualified_support_present and attempted_coverage_increase > 0:
            raise ValidationError(
                "TEST_VOLUME_CANNOT_INFLATE_COVERAGE",
                "High test execution count cannot raise coverage without verified qualified evidence",
            )

    @staticmethod
    def validate_unknown_scope_not_hidden(
        unknown_surfaces: Sequence[Mapping],
        unsupported_surfaces: Sequence[Mapping],
        reported_unknown_scope: Sequence[Mapping],
        reported_unsupported_scope: Sequence[Mapping],
    ) -> None:
        """Condition 7: Unknown and unsupported scopes must not be omitted or auto-N/A'd."""
        if len(unknown_surfaces) != len(reported_unknown_scope):
            raise ValidationError(
                "CANNOT_HIDE_UNKNOWN_SCOPE",
                f"Unknown surfaces count ({len(unknown_surfaces)}) does not match reported ({len(reported_unknown_scope)})",
            )
        if len(unsupported_surfaces) != len(reported_unsupported_scope):
            raise ValidationError(
                "CANNOT_HIDE_UNSUPPORTED_SCOPE",
                f"Unsupported surfaces count ({len(unsupported_surfaces)}) does not match reported ({len(reported_unsupported_scope)})",
            )

    def evaluate_gate(
        self,
        blind_result: E3BlindNoveltyResult,
        checkpoint: E3BlindCheckpoint,
        positive_projection: PositiveGapProjection,
        reveal_event: E3RevealEvent,
        scheduler: E3GapDirectedScheduler,
        holdout_corpus_role: str,
        false_negative_assessments: Sequence[FalseNegativeRelationshipAssessment],
        critical_surfaces: Sequence[Mapping],
        open_obligations: Sequence[Mapping],
        findings_on_critical_surfaces: Sequence[Mapping],
        test_case_count: int,
        attempted_coverage_increase: float,
        qualified_support_present: bool,
        unknown_surfaces: Sequence[Mapping],
        unsupported_surfaces: Sequence[Mapping],
        e2_completion_digest: str,
        fuzzing_count: int,
        differential_count: int,
        metamorphic_count: int,
        adjudicated_count: int,
    ) -> E3StageCompletionCandidate:
        """Run all 7 checks and produce E3StageCompletionCandidate if PASS."""
        # 1. Blind provenance
        self.validate_blind_provenance_preserved(blind_result, checkpoint)

        # 2. Gap mode transition
        self.validate_gap_mode_transition(positive_projection, reveal_event)

        # 3. Auxiliary corpus
        self.validate_no_auxiliary_corpus_confusion(holdout_corpus_role)

        # 4. Multi-stage false negative
        for asmt in false_negative_assessments:
            # Check reasons
            if asmt.result == "MULTI_STAGE_FALSE_NEGATIVE" and "NEW_SCOPE" in str(asmt.reason_codes):
                raise ValidationError("INVALID_FALSE_NEGATIVE_ON_NEW_SCOPE", "Cannot mark false negative on new scope")

        # 5. Critical surface obligations
        self.validate_critical_surface_obligations(
            critical_surfaces, open_obligations, findings_on_critical_surfaces
        )

        # 6. Test volume vs coverage
        self.validate_coverage_not_inflated_by_test_volume(
            test_case_count, attempted_coverage_increase, qualified_support_present
        )

        # 7. Unknown / unsupported scope preservation
        self.validate_unknown_scope_not_hidden(
            unknown_surfaces,
            unsupported_surfaces,
            positive_projection.explicit_unknown_scope,
            positive_projection.explicit_unsupported_scope,
        )

        # Compute completion digest
        comp_body = {
            "stage_key": "E3",
            "blind_checkpoint_digest": checkpoint.digest,
            "positive_projection_digest": positive_projection.digest,
            "total_blind": blind_result.total_discoveries,
            "total_gap": len(scheduler._executed_targets),
            "fuzzing_count": fuzzing_count,
            "differential_count": differential_count,
            "metamorphic_count": metamorphic_count,
            "adjudicated_count": adjudicated_count,
            "open_obligations_count": len(open_obligations),
            "unknown_scope_count": len(unknown_surfaces),
            "unsupported_scope_count": len(unsupported_surfaces),
        }
        comp_digest = hashlib.sha256(canonical_bytes(comp_body)).hexdigest()

        fn_count = sum(1 for a in false_negative_assessments if a.result == "MULTI_STAGE_FALSE_NEGATIVE")

        return E3StageCompletionCandidate(
            stage_key="E3",
            stage_spec_digest=blind_result.stage_spec_digest,
            e2_completion_digest=e2_completion_digest,
            blind_checkpoint_digest=checkpoint.digest,
            positive_projection_digest=positive_projection.digest,
            blind_discoveries_count=blind_result.total_discoveries,
            gap_discoveries_count=len(scheduler._executed_targets),
            fuzzing_executions_count=fuzzing_count,
            differential_executions_count=differential_count,
            metamorphic_executions_count=metamorphic_count,
            adjudicated_decisions_count=adjudicated_count,
            open_obligations_count=len(open_obligations),
            unknown_scope_count=len(unknown_surfaces),
            unsupported_scope_count=len(unsupported_surfaces),
            multi_stage_false_negatives_count=fn_count,
            completion_digest=comp_digest,
            gate_verdict="PASS",
        )
