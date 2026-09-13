from __future__ import annotations

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.opportunities.analysis import analyze_opportunities
from bdb_audit.opportunities.architecture.improvements import architecture_improvement
from bdb_audit.opportunities.models import OpportunityProposal, ProductContext, UserTaskTrace
from bdb_audit.opportunities.ranking import rank_opportunities
from bdb_audit.opportunities.skeptic import skeptic_review
from bdb_audit.opportunities.task_traces import ingest_task_traces


def _context(runtime: bool = False) -> ProductContext:
    return ProductContext(
        target_id="target-a",
        source_identity={"git_commit_object_id": "a" * 40},
        declared_goals=("reduce operator friction",),
        personas=("operator",),
        runtime_available=runtime,
    )


def test_ru15_no_runtime_means_no_fabricated_walkthrough() -> None:
    context = _context(False)
    assert ingest_task_traces(context, ()) == ()
    with pytest.raises(ValidationError, match="TASK_TRACE_RUNTIME_NOT_AVAILABLE"):
        ingest_task_traces(context, ({
            "trace_id": "t1", "actor": "operator", "steps": ["open"],
            "evidence_refs": ["obs:1"], "observation_mode": "OBSERVED", "runtime_observed": True,
        },))


def test_ru15_observed_trace_requires_runtime_evidence() -> None:
    with pytest.raises(ValidationError, match="TASK_TRACE_OBSERVED_WITHOUT_RUNTIME_EVIDENCE"):
        UserTaskTrace("t1", "target-a", "operator", ("open",), (), "OBSERVED", True)


def test_ru15_opportunity_cannot_be_promoted_to_mandatory_obligation() -> None:
    with pytest.raises(ValidationError, match="OPPORTUNITY_CANNOT_BECOME_MANDATORY"):
        OpportunityProposal(
            "p1", "Improve flow", "UX", ("f1",), ("obs:1",),
            "Fewer steps", "OBSERVED", mandatory_obligation=True,
        )


def test_ru15_inferred_proposal_requires_revision_in_skeptic_review() -> None:
    proposal = architecture_improvement(
        proposal_id="arch1", title="Split component", evidence_refs=(),
        benefit_hypothesis="May reduce coupling", basis="INFERRED",
    )
    review = skeptic_review(proposal)
    assert review.decision == "REVISE"


def test_ru15_target_specific_observed_analysis_can_reach_report_proposal() -> None:
    result = analyze_opportunities({
        "target_id": "target-a",
        "source_identity": {"git_commit_object_id": "a" * 40},
        "declared_goals": ["fast operator flow"],
        "personas": ["operator"],
        "runtime_available": True,
        "task_traces": [{
            "trace_id": "trace1", "actor": "operator", "steps": ["open", "search", "export"],
            "evidence_refs": ["obs:trace1"], "observation_mode": "OBSERVED", "runtime_observed": True,
        }],
        "friction_candidates": [{
            "candidate_id": "fr1", "trace_id": "trace1", "description": "Repeated navigation",
            "basis": "OBSERVED", "evidence_refs": ["obs:trace1"], "severity": "MEDIUM",
        }],
        "proposals": [{
            "proposal_id": "p1", "title": "Reduce repeated navigation", "opportunity_type": "UX",
            "source_candidate_ids": ["fr1"], "benefit_hypothesis": "Fewer repeated steps",
        }],
    })
    proposal_body = result["opportunities"][0]
    assert proposal_body["basis"] == "OBSERVED"
    assert proposal_body["mandatory_obligation"] is False
    proposal = OpportunityProposal(
        proposal_body["proposal_id"], proposal_body["title"], proposal_body["opportunity_type"],
        tuple(proposal_body["source_candidate_ids"]), tuple(proposal_body["evidence_refs"]),
        proposal_body["benefit_hypothesis"], proposal_body["basis"],
    )
    review = skeptic_review(proposal)
    assert review.decision == "ACCEPT_FOR_REPORT"
    ranked = rank_opportunities((proposal,), (review,), {"p1": 4})
    assert ranked[0]["mandatory_obligation"] is False
