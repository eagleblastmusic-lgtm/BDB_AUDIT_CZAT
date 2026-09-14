"""Astra/R5.3 external-stage lane profile corrections.

The continuation branch keeps user-facing lane order separate from canonical
reference-set order. StageRun reference arrays are canonicalized according to
the pinned registry. E2 manual packages additionally embed one exact frozen E1
predecessor view in PROMPT.txt; prompt_sha256 therefore binds the semantic view
without a second mutable transport channel.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, CommandEnvelope, HistoryCut
from ..orchestration.compiler import PromptPackageCompiler as CanonicalPromptPackageCompiler
from . import stage_transport
from .e2_semantics import build_e2_predecessor_view, predecessor_view_json
from .stage_transport import StageLaneDefinition


ASTRA_POST_E1_STAGE_LANES: dict[str, tuple[StageLaneDefinition, ...]] = {
    "E2": (
        StageLaneDefinition(
            "E2-CONVERGENCE",
            "Claim convergence, quarantine normalization and evidence cross-review",
            "CONVERGENCE_AND_CROSS_REVIEW",
            "DECLARED",
        ),
        StageLaneDefinition(
            "E2-ADJUDICATION",
            "Four-axis finding adjudication and contradiction review",
            "FOUR_AXIS_ADJUDICATION",
            "DECLARED",
        ),
    ),
    "E3": (
        StageLaneDefinition(
            "E3-X",
            "Security, Authority & Trust blind novelty search",
            "AUTHORITY_TRUST_NOVELTY_SEARCH",
            "ENFORCED",
        ),
        StageLaneDefinition(
            "E3-Y",
            "State, Data, Catalog & Recovery blind novelty search",
            "STATE_CATALOG_RECOVERY_SEARCH",
            "ENFORCED",
        ),
        StageLaneDefinition(
            "E3-Z",
            "Frontend, Concurrency, Resources & Cross-Layer blind novelty search",
            "CROSS_LAYER_CONCURRENCY_SEARCH",
            "ENFORCED",
        ),
    ),
    "E4": (
        StageLaneDefinition(
            "E4-DEEPEN",
            "Deepening, state, recovery and concurrency verification",
            "DEEPEN",
            "DECLARED",
        ),
    ),
    "E5": (
        StageLaneDefinition(
            "E5-CANDIDATE",
            "Candidate assurance synthesis",
            "CANDIDATE_SYNTHESIS",
            "DECLARED",
        ),
        StageLaneDefinition(
            "E5-SKEPTIC",
            "False-positive skeptic",
            "FALSE_POSITIVE_SKEPTIC",
            "DECLARED",
            "FALSE_POSITIVE_SKEPTIC",
        ),
        StageLaneDefinition(
            "E5-HUNTER",
            "False-negative hunter",
            "FALSE_NEGATIVE_HUNTER",
            "DECLARED",
            "FALSE_NEGATIVE_HUNTER",
        ),
    ),
    "E6": (
        StageLaneDefinition(
            "E6-VERIFY",
            "Targeted verification of remaining material gaps",
            "TARGETED_VERIFICATION",
            "DECLARED",
        ),
    ),
}


class AstraPromptPackageCompiler(CanonicalPromptPackageCompiler):
    """Map branch transport metadata onto the pinned canonical prompt templates."""

    def compile(
        self,
        *,
        stage_spec_revision: Any,
        lane_spec_revision: Any,
        executor_revision: Any,
        delivery_revision: Any,
        projection_policy: Any,
        view_manifest: Any,
        history_cut: Any,
        prompt: Any = None,
    ) -> Any:
        normalized = dict(prompt) if isinstance(prompt, dict) else prompt
        if isinstance(normalized, dict) and normalized.get("template") == "manual_stage":
            stage = str(normalized.get("stage", "")).upper()
            slot = str(normalized.get("slot", ""))
            strategy = str(normalized.get("strategy", ""))
            cut_digest = hashlib.sha256(canonical_bytes(history_cut)).hexdigest()
            if stage == "E2":
                normalized = {
                    "template": "e2_cross_review",
                    "slot": slot,
                    "predecessor_cut": cut_digest,
                }
            elif stage == "E3":
                normalized = {
                    "template": "e3_blind",
                    "slot": slot,
                    "holdout_id": f"{slot}:{cut_digest[:16]}",
                }
            elif stage == "E4":
                normalized = {
                    "template": "e4_deepen",
                    "focus_area": slot,
                    "depth_level": strategy or "DEEPEN",
                }
            elif stage == "E5":
                normalized = {
                    "template": "e5_attack",
                    "candidate_id": f"PENDING_CANDIDATE:{cut_digest[:16]}",
                    "challenger_profile": strategy or slot,
                }
            elif stage == "E6":
                normalized = {
                    "template": "e6_adaptive",
                    "stop_evaluation_ref": f"PENDING_STOP:{cut_digest[:16]}",
                    "budget": "POLICY_BOUND",
                }
            else:
                raise ValidationError("POST_E1_STAGE_UNSUPPORTED", stage)
        return super().compile(
            stage_spec_revision=stage_spec_revision,
            lane_spec_revision=lane_spec_revision,
            executor_revision=executor_revision,
            delivery_revision=delivery_revision,
            projection_policy=projection_policy,
            view_manifest=view_manifest,
            history_cut=history_cut,
            prompt=normalized,
        )


_E2_PREDECESSOR_VIEWS: dict[bytes, tuple[dict[str, Any], ...]] = {}
_ORIGINAL_BUILD_PROMPT = stage_transport._build_prompt


def _cut_key(cut: Mapping[str, Any]) -> bytes:
    return hashlib.sha256(canonical_bytes(dict(cut))).digest()


def _e2_common_result_prefix(job: stage_transport.PreparedStageAssignment, source: Any, execution_mode: str, model: str) -> str:
    return f'''{{
  "kind": "bdb_audit_lane_result",
  "version": "1",
  "campaign_id": "{job.assignment_input_history_cut['campaign_id']}",
  "stage_id": "E2",
  "lane_slot": "{{LANE_SLOT}}",
  "executor_profile": "{execution_mode}",
  "executor_model": "{model}",
  "input_package_digest": "<COPY_FROM_INPUT_MANIFEST>",
  "source_commit_sha": "{source.exact_commit_sha}",
  "history_cut": {canonical_bytes(job.assignment_input_history_cut).decode('utf-8')},
  "assignment_ref": {canonical_bytes(job.assignment_ref).decode('utf-8')},
  "attempt_ref": {canonical_bytes(job.attempt_ref).decode('utf-8')},
  "findings": [],
  "findings_count": 0,
  "e2_records": ['''


def _e2_prompt(
    job: stage_transport.PreparedStageAssignment,
    lane_def: StageLaneDefinition,
    source: Any,
    execution_mode: str,
    model: str,
) -> str:
    view = _E2_PREDECESSOR_VIEWS.get(_cut_key(job.assignment_input_history_cut))
    if view is None:
        raise ValidationError("E2_PREDECESSOR_VIEW_NOT_PREPARED", lane_def.slot)
    base = _ORIGINAL_BUILD_PROMPT(job, lane_def, source, execution_mode, model)
    prefix = base.split("## Result", 1)[0].rstrip()
    frozen_view = predecessor_view_json(view)
    common = _e2_common_result_prefix(job, source, execution_mode, model).replace("{LANE_SLOT}", lane_def.slot)

    if lane_def.slot == "E2-CONVERGENCE":
        record_example = '''
    {
      "finding_key": "<COPY_EXACTLY_FROM_VIEW>",
      "statement": "<COPY_EXACTLY_FROM_VIEW>",
      "category": "<SECURITY|RELIABILITY|DATA_INTEGRITY|AVAILABILITY|PRIVACY|RELEASE_ASSURANCE|EVIDENCE_QUALITY|OTHER>",
      "scope_refs": [],
      "violated_invariant_refs": [],
      "discovery_relation_refs": [],
      "limitations": [],
      "finding_scope": {},
      "normalization_group_key": null,
      "root_cause_statement": null,
      "root_cause_relation_role": "CONTRIBUTING",
      "root_cause_scope": {},
      "root_cause_membership_scope": {},
      "predecessor_root_cause_refs": []
    }
'''
        lane_rules = """For every predecessor finding return exactly one e2_records entry. Preserve finding_key and statement byte-for-text exactly. Do not merge findings by statement. normalization_group_key may be shared only when you can justify a common root cause; when it is non-null, root_cause_statement is mandatory. Claims themselves are evidence-free: do not place severity, axis truth, contradiction status or remediation state in the convergence claim metadata."""
    elif lane_def.slot == "E2-ADJUDICATION":
        record_example = '''
    {
      "finding_key": "<COPY_EXACTLY_FROM_VIEW>",
      "statement": "<COPY_EXACTLY_FROM_VIEW>",
      "axes": {
        "MECHANISM": {"epistemic_outcome":"INCONCLUSIVE","scope":{},"evidence_qualification_refs":[],"method_or_characterization_refs":[],"confidence":"UNKNOWN","limitations":[],"reason_codes":[]},
        "REACHABILITY": {"epistemic_outcome":"INCONCLUSIVE","scope":{},"evidence_qualification_refs":[],"method_or_characterization_refs":[],"confidence":"UNKNOWN","limitations":[],"reason_codes":[]},
        "IMPACT": {"epistemic_outcome":"INCONCLUSIVE","scope":{},"evidence_qualification_refs":[],"method_or_characterization_refs":[],"confidence":"UNKNOWN","limitations":[],"reason_codes":[]},
        "SEVERITY": {"severity_value":"INFO","scope":{},"evidence_qualification_refs":[],"method_or_characterization_refs":[],"confidence":"UNKNOWN","limitations":[],"reason_codes":[]}
      },
      "reason_codes": [],
      "claim_position": "INCONCLUSIVE",
      "claim_evidence_qualification_refs": [],
      "contradiction_group_key": null,
      "contradiction_scope": {},
      "failure_assumption_differences": [],
      "environment_input_model_differences": [],
      "required_falsifier": null
    }
'''
        lane_rules = """For every predecessor finding return exactly one e2_records entry. Preserve finding_key and statement exactly. MECHANISM/REACHABILITY/IMPACT use epistemic_outcome; SEVERITY uses severity_value only and never epistemic_outcome. SUPPORTED or REFUTED is legal only when evidence_qualification_refs contains exact refs already listed for that finding in accepted_evidence_qualification_refs of the frozen predecessor view. Otherwise use INCONCLUSIVE. claim_position SUPPORTED/REFUTED follows the same rule. Contradiction grouping requires at least two opposing qualified positions and one explicit required_falsifier shared by the group. Majority vote is never truth authority."""
    else:
        raise ValidationError("E2_LANE_SLOT_UNSUPPORTED", lane_def.slot)

    return f"""{prefix}

## Frozen E1 predecessor view

The JSON below is the exact semantic predecessor view for this E2 assignment. It is embedded in PROMPT.txt and therefore bound by prompt_sha256 and package_digest. Do not add, drop, rename, combine, or rewrite its findings.

```json
{frozen_view}
```

## E2 semantic rules

{lane_rules}

If a reference is not already present as an accepted typed reference in the frozen view, do not invent it. Missing qualified evidence means INCONCLUSIVE, not SUPPORTED. Return one ZIP with root MANIFEST.json and copy package_digest from the input MANIFEST exactly.

## Result contract

```json
{common}{record_example}  ]
}}
```
"""


def _astra_build_prompt(
    job: stage_transport.PreparedStageAssignment,
    lane_def: StageLaneDefinition,
    source: Any,
    execution_mode: str,
    model: str,
) -> str:
    if job.stage_id == "E2":
        return _e2_prompt(job, lane_def, source, execution_mode, model)
    return _ORIGINAL_BUILD_PROMPT(job, lane_def, source, execution_mode, model)


class AstraStageAssignmentService(stage_transport.StageAssignmentService):
    """Stage assignment service with registry-canonical StageRun ref arrays."""

    def prepare(
        self,
        stage_id: str,
        *,
        executor_profile: str,
        model: str,
        slots: Sequence[str],
        delivery_profile: str = "ZIP_PROMPT_CLIPBOARD",
    ):
        prepared, accepted_cut = super().prepare(
            stage_id,
            executor_profile=executor_profile,
            model=model,
            slots=slots,
            delivery_profile=delivery_profile,
        )
        if stage_id.upper() == "E2":
            cuts = {canonical_bytes(row.assignment_input_history_cut) for row in prepared.values()}
            if len(cuts) != 1:
                raise ValidationError("ASSIGNMENT_CUT_DIVERGENCE", "E2")
            frozen_cut = next(iter(prepared.values())).assignment_input_history_cut
            _E2_PREDECESSOR_VIEWS[_cut_key(frozen_cut)] = build_e2_predecessor_view(self.store, frozen_cut)
        return prepared, accepted_cut

    def _stage_run(
        self,
        stage: str,
        cut: dict[str, Any],
        stage_spec: dict[str, Any],
        source: dict[str, Any],
        prior_commit: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        matching = [
            row
            for row in self.store.accepted_records("stage_run", cut)
            if stage_transport._same_ref(row["body"].get("stage_spec_ref"), stage_spec["ref"])
        ]
        if len(matching) > 1:
            raise ValidationError("MULTIPLE_STAGE_RUNS_FOR_STAGE", stage)
        if matching:
            return matching[0], cut

        predecessor = {
            "E2": "E1",
            "E3": "E2",
            "E4": "E3",
            "E5": "E4",
            "E6": "E5",
        }.get(stage)
        predecessor_refs: list[dict[str, Any]] = []
        if predecessor:
            stage_specs = self.store.accepted_records("stage_spec", cut)
            by_digest = {
                row["ref"]["revision_digest"]: row["body"].get("stage_key")
                for row in stage_specs
            }
            candidates = []
            for row in self.store.accepted_records("stage_completion", cut):
                spec_ref = row["body"].get("stage_spec_ref", {})
                if by_digest.get(spec_ref.get("revision_digest")) == predecessor:
                    candidates.append(row)
            if not candidates:
                raise ValidationError("PREDECESSOR_STAGE_NOT_COMPLETED", predecessor)
            predecessor_refs = canonical_reference_set([
                stage_transport._ref(candidates[-1], "PRIOR_ACCEPTED_ONLY")
            ])

        required_slot_refs = canonical_reference_set([
            stage_transport._external_ref(
                "result_slot_contract_ref",
                f"{stage}:{slot}",
                "HISTORY_CONTEXT_BINDING",
            )
            for slot in stage_transport.stage_slots(stage)
        ])
        stage_run = CanonicalObject(
            "stage_run",
            {
                "stage_run_id": f"stage_run_{stage}_{hashlib.sha256(canonical_bytes(cut)).hexdigest()[:16]}",
                "campaign_ref": cut["campaign_id"],
                "stage_spec_ref": stage_transport._ref(stage_spec, "HISTORY_CONTEXT_BINDING"),
                "source_generation_ref": stage_transport._ref(source, "PRIOR_ACCEPTED_ONLY"),
                "creation_input_history_cut": cut,
                "assigned_history_cut": cut,
                "predecessor_stage_completion_refs": predecessor_refs,
                "required_lane_slot_contract_refs": required_slot_refs,
            },
        )
        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        command = CommandEnvelope(
            command_id=stage_transport._command_id(f"stage_run:{stage}:{head.commit_hash}"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit["governing_policy_ref"],
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ())),
            idempotency_scope=f"stage_run:{stage}:{stage_run.digest}",
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=[stage_run],
            expected_head=head,
        )
        new_cut = HistoryCut.accepted(
            accepted.head,
            accepted.commit.governing_policy_ref,
            accepted.commit.governing_spec_refs,
        ).as_dict()
        record = self.store.resolve_accepted(stage_run.as_ref().as_dict(), new_cut)
        return record, new_cut


def apply_astra_stage_profiles() -> None:
    """Install branch-local lane, assignment, compiler, and E2 prompt profiles."""
    stage_transport.POST_E1_STAGE_LANES.update(ASTRA_POST_E1_STAGE_LANES)
    setattr(stage_transport, "StageAssignmentService", AstraStageAssignmentService)
    setattr(stage_transport, "PromptPackageCompiler", AstraPromptPackageCompiler)
    setattr(stage_transport, "_build_prompt", _astra_build_prompt)


__all__ = [
    "ASTRA_POST_E1_STAGE_LANES",
    "AstraPromptPackageCompiler",
    "AstraStageAssignmentService",
    "apply_astra_stage_profiles",
]
