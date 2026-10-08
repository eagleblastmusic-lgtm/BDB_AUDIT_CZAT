"""Explicit finite event wire targets from normative Data §16."""

from __future__ import annotations

from execution import OUT, preserve, read, write
from purpose_contracts import array, const, enum, object_schema, ref, typed


NAMED_TARGETS = dict(line.split() for line in """
CampaignGenesisAccepted campaign_genesis
SuccessorCampaignGenesisAccepted successor_campaign_genesis
SuccessorCampaignSelectionDecisionAccepted successor_campaign_selection_decision
StageRunCreated stage_run
LaneRunCreated lane_run
AttemptCreated attempt
CheckpointSealed checkpoint
GrantAccepted grant_body
PotentialExposureRecorded potential_exposure_record
ContaminationAssessmentAccepted contamination_assessment
IsolationQualificationAccepted isolation_qualification
KnowledgeStateAdvanced knowledge_state
AssignmentManifestAccepted assignment_manifest
DiscoveryRecorded discovery_record
HypothesisAccepted hypothesis_revision
ExperimentPreregistered experiment_spec
ExecutionDescriptorAccepted execution_descriptor
FaultRunRecordAccepted fault_run_record
ExecutionResultAccepted execution_result
ObservationAccepted observation
EvidenceQualificationAccepted evidence_qualification_assessment
EvidenceApplicabilityAssessmentAccepted evidence_applicability_assessment
EvidenceInvalidated evidence_invalidation
InventoryRevisionAccepted inventory_revision
MaterialityAssessmentAccepted materiality_assessment
CoverageObligationCreated coverage_obligation
CoverageObligationApplicabilityAccepted obligation_applicability_decision
CoverageObligationQualified coverage_obligation_qualification
ApprovalDecisionAccepted approval_decision
FindingClaimRevisionAccepted finding_claim_revision
FindingAxisAssessmentAccepted finding_axis_assessment
FindingAdjudicationAccepted finding_adjudication_decision
RootCauseRevisionAccepted root_cause_revision
ContradictionRevisionAccepted contradiction_revision
ContradictionResolutionAccepted contradiction_resolution_decision
LaneCompletionAccepted lane_completion
StageCompletionAccepted stage_completion
CandidateAssuranceCaseAccepted candidate_assurance_case
ChallengerAssignmentAccepted challenger_assignment
ChallengerResultAccepted challenger_result
StopEvaluationAccepted stop_evaluation
CampaignConclusionAccepted campaign_conclusion
ReleaseQualificationAccepted release_qualification
LegacyRawRefAccepted legacy_raw_ref
LegacyMechanicalValidationAssessmentAccepted legacy_mechanical_validation_assessment
SourceReconciliationAssessmentAccepted source_reconciliation_assessment
LineageAdmissionAssessmentAccepted lineage_admission_assessment
LegacyExposureReconstructionAssessmentAccepted legacy_exposure_reconstruction_assessment
LegacyObservationSemanticEquivalenceAssessmentAccepted legacy_observation_semantic_equivalence_assessment
LegacyObservationMappingAssessmentAccepted legacy_observation_mapping_assessment
BootstrapAdmissionAccepted bootstrap_admission_decision
CompatibilityFixtureAssessmentAccepted compatibility_fixture_assessment
CompatibilityGateResultAccepted compatibility_gate_result
""".strip().splitlines())

ROOT_KINDS = "artifact_contract_registry schema_registry installation_bootstrap_profile trust_profile policy_revision spec_revision".split()
FORBIDDEN_GENERIC_KINDS = ROOT_KINDS + "command_envelope commit_body command_receipt".split()
COMMAND_KINDS = "INITIALIZE_CAMPAIGN_FROM_LEGACY ACCEPT_ARTIFACTS TRANSITION INGEST_EXTERNAL_LANE_RESULT".split()


def finite_typed(kinds):
    return {"allOf": [ref("typed_ref"), {"properties": {"kind": enum(sorted(kinds))}}]}


def add_definitions(defs, keys):
    kinds = {key.split("::", 1)[1].split("/")[0] for key in keys}
    assert set(NAMED_TARGETS.values()) <= kinds
    variants = [object_schema({"event_type": const(name), "artifact_ref": typed(kind)}) for name, kind in sorted(NAMED_TARGETS.items())]
    variants.append(object_schema({"event_type": const("ArtifactAccepted"), "artifact_ref": finite_typed(kinds - set(FORBIDDEN_GENERIC_KINDS))}))
    variants.append(object_schema({"event_type": const("InstallationRootPinned"), "artifact_ref": finite_typed(ROOT_KINDS)}))
    variants.append(object_schema({"event_type": const("GateEvaluated"), "target_ref": ref("typed_ref"), "result_ref": ref("typed_ref")}))
    variants.append(object_schema({"event_type": const("AttemptStarted"), "attempt_ref": typed("attempt"), "assignment_ref": typed("assignment_manifest"), "package_binding_ref": typed("assignment_package_binding")}))
    for aggregate, kind in {"CAMPAIGN": "campaign_genesis", "STAGE_RUN": "stage_run", "LANE_RUN": "lane_run", "ATTEMPT": "attempt"}.items():
        variants.append(object_schema({"event_type": const("StateTransitionAccepted"), "aggregate_kind": const(aggregate), "aggregate_ref": typed(kind), "from_state": ref("code"), "to_state": ref("code"), "basis_refs": array(ref("typed_ref"), 1)}))
    defs["event_body"] = {"oneOf": variants}
    defs["command_payload"] = object_schema({"proposed_object_refs": array(finite_typed(kinds - {"command_envelope", "commit_body", "command_receipt"})), "events": array(ref("event_body"), 1)})
    # Events and object closure are ordered sequences, not set-normalized arrays.
    for name in ("proposed_object_refs", "events"):
        defs["command_payload"]["properties"][name].pop("uniqueItems")


def main():
    preserve()
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    keys = {k.split("/")[0]: k for k in mapping.values()}
    write("design/EVENT_TARGET_TABLE.json", {"named_targets": {event: keys[kind] for event, kind in NAMED_TARGETS.items()},
          "special_events": ["ArtifactAccepted", "InstallationRootPinned", "GateEvaluated", "AttemptStarted", "StateTransitionAccepted"],
          "command_kinds": COMMAND_KINDS, "status": "DESIGN_ONLY; temporal/producer/FSM checks mandatory"})
    print({"named_event_targets": len(NAMED_TARGETS), "special_event_forms": 5})


if __name__ == "__main__":
    main()
