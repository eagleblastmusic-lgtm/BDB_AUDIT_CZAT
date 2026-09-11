"""Deterministic executable schemas for the reference profile.

R5.3.1 freezes semantic contracts in the Registry; these small executable
schemas make the reference implementation's accepted paths offline and
fail-closed. Cross-object authority/lifecycle rules remain in their domain
validators. Bytes are generated from the pinned Registry in one deterministic
function and are never rebound at runtime.
"""
import hashlib
from functools import lru_cache

from ..core.canonical_json import canonical_bytes
from ..core.registry import ContractRegistry
from .binding import SchemaBindings

FOUNDATION_SCHEMA_PROFILE = "BDB-F2-EXECUTABLE-SCHEMAS-1"

# All kinds reachable by F2's reference implementation. Future registered
# kinds remain unbound until a caller explicitly requests the full profile.
M5_KINDS = (
    "command_envelope", "commit_body", "command_receipt", "history_cut",
    "installation_bootstrap_profile", "trusted_predecessor_selection_decision",
    "bootstrap_admission_decision", "campaign_genesis", "source_generation",
    "legacy_raw_ref", "legacy_mechanical_validation_assessment",
    "source_reconciliation_assessment", "lineage_admission_assessment",
    "legacy_exposure_reconstruction_assessment",
)
F2_KINDS = (
    *M5_KINDS, "stage_spec", "stage_run", "lane_spec", "lane_run", "attempt",
    "executor_spec", "delivery_spec", "projection_policy", "view_manifest",
    "assignment_manifest", "grant_body", "potential_exposure_record",
    "isolation_qualification", "contamination_assessment", "knowledge_state",
    "corpus_manifest", "discovery_record", "source_generation", "source_manifest",
    "source_identity",
    # Context objects that can become effective only on a later accepted
    # history cut.  Binding them here lets the history adapter reject a
    # same-commit semantic upgrade with its domain error instead of accepting
    # an otherwise unbound object or inventing a PR-order exception.
    "policy_revision", "spec_revision", "trust_profile", "schema_registry",
    "artifact_contract_registry",
)

M14_KINDS = (
    "surface_key", "surface_record", "input_disposition_record",
    "scope_state_record", "inventory_revision", "surface_collector_record",
)

M15_KINDS = (
    "invariant_revision", "materiality_assessment", "coverage_obligation",
    "coverage_obligation_key", "coverage_obligation_qualification",
    "obligation_applicability_decision", "approval_decision",
)

M18_KINDS = (
    "hypothesis_revision",
)

M19_KINDS = (
    "experiment_spec", "execution_descriptor", "fault_run_record",
    "cleanup_result", "execution_result", "tool_execution_record",
)

M20_KINDS = (
    "observation", "dependency_independence_assessment",
    "evidence_applicability_assessment", "evidence_qualification_assessment",
    "evidence_invalidation",
)

M21_KINDS = (
    "finding_claim_revision", "finding_axis_assessment",
    "finding_adjudication_decision", "root_cause_revision",
    "contradiction_revision", "contradiction_resolution_decision",
)

F3_KINDS = (*F2_KINDS, *M14_KINDS, *M15_KINDS, *M18_KINDS, *M19_KINDS, *M20_KINDS, *M21_KINDS)


def executable_schema(kind, *, registry=None):
    registry = registry or ContractRegistry()
    row = registry.contract(kind)
    # Typed references remain declared by the exact Registry row. The schema is
    # deliberately structural; semantic validators enforce cross-object rules.
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": row["schema_ref"],
        "title": "BDB Audit v2 " + kind,
        "type": "object",
        "additionalProperties": True,
        "x-bdb-material-refs": row["material_refs"],
    }
    if kind == "command_envelope":
        from .command import command_schema
        schema.update(command_schema())
    from .orchestration import orchestration_schema
    structural = orchestration_schema(kind)
    if structural is not None:
        schema.update(structural)
    from .bootstrap import bootstrap_schema
    structural = bootstrap_schema(kind)
    if structural is not None:
        schema.update(structural)
    from .inventory import inventory_schema
    structural = inventory_schema(kind)
    if structural is not None:
        schema.update(structural)
    from .coverage import coverage_schema
    structural = coverage_schema(kind)
    if structural is not None:
        schema.update(structural)
    from .hypothesis import hypothesis_schema
    structural = hypothesis_schema(kind)
    if structural is not None:
        schema.update(structural)
    from .experiment import experiment_schema
    structural = experiment_schema(kind)
    if structural is not None:
        schema.update(structural)
    from .evidence import evidence_schema
    structural = evidence_schema(kind)
    if structural is not None:
        schema.update(structural)
    from .adjudication import adjudication_schema
    structural = adjudication_schema(kind)
    if structural is not None:
        schema.update(structural)
    return schema


@lru_cache(maxsize=4)
def foundation_schema_bindings(profile=FOUNDATION_SCHEMA_PROFILE, kinds=F2_KINDS):
    if profile != FOUNDATION_SCHEMA_PROFILE:
        raise ValueError("unknown foundation schema profile")
    registry = ContractRegistry()
    rows = []
    seen = set()
    for kind in kinds:
        if kind in seen:
            continue
        seen.add(kind)
        schema = executable_schema(kind, registry=registry)
        raw = canonical_bytes(schema)
        rows.append((kind, "1", raw, hashlib.sha256(raw).hexdigest()))
    return SchemaBindings(rows, registry=registry)


def schema_identity_manifest(kinds=F2_KINDS):
    bindings = foundation_schema_bindings(kinds=tuple(kinds))
    return {"profile": FOUNDATION_SCHEMA_PROFILE, "registry_id": ContractRegistry().document["registry_id"],
            "bindings": bindings.identities, "backend": bindings.backend}
