"""Build only the R5.4 normative candidate; never imports or edits runtime code.

Generation is preparation, not authority. Exact files are subsequently checked
by verify_candidate.py and pinned by an external manifest/readback. Running
this tool against an already qualified/published candidate is forbidden.
"""
from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import re
import struct
import subprocess
import unicodedata
import uuid
import zipfile
import io
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
CONTEXT = REPO.parent / "BDB Audit - Context"
CANDIDATE = ROOT / "candidate"
EVIDENCE = ROOT / "evidence"
DATE = "2026-10-06"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_PREFIX = "BDB_SCHEMA_REGISTRY::"
OBJECT_PROFILE = "BDB-OBJECT-DIGEST-1"
PREDECESSOR_SET = "087539f5a08a2441647aae1889ce51330b47740e559b394574da122bd6cfd15b"
LEGACY_SET = "78de98f8163d2f0bf0ab94781b86bd8e5e0345411a4432669d91fdfc42671d56"
SHA = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
TEXT = {"type": "string"}
NONEMPTY = {"type": "string", "minLength": 1}
INTEGER = {"type": "integer", "minimum": 0, "maximum": 9007199254740991}


def checked(value):
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str) or not k.isascii():
                raise ValueError("NON_ASCII_CANONICAL_KEY")
            checked(v)
    elif isinstance(value, list):
        for v in value:
            checked(v)
    elif isinstance(value, str):
        value.encode("utf-8", errors="strict")
    elif value is None or isinstance(value, bool):
        pass
    elif isinstance(value, int):
        if abs(value) > 9007199254740991:
            raise ValueError("UNSAFE_CANONICAL_INTEGER")
    else:
        raise ValueError("NON_CANONICAL_VALUE")


def cjson(value):
    checked(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def object_digest(kind, version, body):
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", kind):
        raise ValueError("INVALID_WIRE_KIND")
    return digest(f"BDB2/{kind}/{version}".encode("ascii") + b"\0" + cjson(body))


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def json_file(path, value):
    write(path, cjson(value) + b"\n")


def markdown(path, value):
    write(path, value.rstrip().encode("utf-8") + b"\n")


def closed(properties, required=None, **extra):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False, **extra}


def array(item, minimum=0, unique=False):
    return {"type": "array", "items": item, "minItems": minimum, **({"uniqueItems": True} if unique else {})}


def local_ref(name):
    return {"$ref": "#/$defs/" + name}


def ref_rule(field, targets, cardinality, cls, **extra):
    return {"field": field, "allowed": targets, "cardinality": cardinality, "ref_class": cls, **extra}


def new_row(kind, version, authority, refs, scalars):
    return {
        "kind": kind, "version": str(version), "canonical_role": "FACT", "lifecycle": "IMMUTABLE",
        "authoritative_for": authority, "producer_authority": "TRUSTED_COORDINATOR_ACCEPTANCE",
        "consumer_roles": ["COORDINATOR", "VALIDATOR", "STORE"],
        "identity_semantics": "BDB-CJSON-1 + BDB-OBJECT-DIGEST-1; exact Registry wire kind/version",
        "schema_ref": f"{SCHEMA_PREFIX}{kind}/{version}", "validation_profile": "NF02_PROVENANCE",
        "required_validation_layers": [f"L{i}" for i in range(1, 7)],
        "reference_contract_mode": "EXPLICIT_COMPLETE", "material_refs": refs,
        "required_scalar_fields": scalars, "ordering_rules": {},
        "first_acceptance_rule": "Registered R5.4 contract and exact schema bytes/digest bound by the governing accepted/pinned SchemaRegistry before first acceptance; every domain predicate must pass.",
    }


def named_id(kind, number):
    # Fixed synthetic UUIDv4 values for design fixtures, not runtime identity issuance.
    return kind + "_" + str(uuid.UUID(f"00000000-0000-4000-8000-{number:012x}"))


def run_git(*args):
    p = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    if p.returncode:
        raise RuntimeError(p.stderr)
    return p.stdout.strip(), p.stderr.strip()


def capture_inputs():
    head, _ = run_git("rev-parse", "HEAD")
    tree, _ = run_git("rev-parse", "HEAD^{tree}")
    branch, _ = run_git("branch", "--show-current")
    main, _ = run_git("rev-parse", "main")
    status, warning = run_git("status", "--short")
    raw = json.loads((REPO / "docs/NF02_RAW_DURABILITY_VERIFICATION_2026_10_02.json").read_bytes())
    pins = raw["tested_inputs"]["source_pins"]
    observed = {name: digest((REPO / name).read_bytes()) for name in pins}
    if pins != observed:
        raise RuntimeError("SOURCE_DRIFT_BEFORE_CANDIDATE")
    context_pins = {p.name: digest(p.read_bytes()) for p in CONTEXT.iterdir() if p.is_file()}
    # All historical snapshots and frozen legacy tracked bytes, not just dirty source.
    tracked, _ = run_git("ls-files", "src", "tests", "build", "legacy", "F0_QUALIFICATION", "F1_QUALIFICATION", "F2_QUALIFICATION")
    protected = {name: digest((REPO / name).read_bytes()) for name in tracked.splitlines() if (REPO / name).is_file()}
    return {"schema": "BDB_R5_4_SOURCE_AND_PREDECESSOR_PIN/1", "date": DATE,
            "head": head, "tree": tree, "branch": branch, "main": main,
            "worktree_status_before": status.splitlines(), "git_status_warning": warning,
            "proposal_raw_digest": digest((REPO / "docs/NF02_NORMATIVE_CONTRACT_DECISION_PROPOSAL.md").read_bytes()),
            "predecessor_context_raw_pins": context_pins, "source_pins": observed, "protected_tracked_pins": protected,
            "predecessor_candidate_set_digest": PREDECESSOR_SET, "predecessor_r5_3_set_digest": LEGACY_SET}


def registry_candidate():
    base = json.loads((CONTEXT / "BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY.json").read_bytes())
    reg = copy.deepcopy(base)
    reg.update({"registry_id": "BDB-AUDIT-V2-ARTIFACT-CONTRACT-REGISTRY-R5-4-1",
                "registry_version": 5, "date": DATE, "status": "R5_4_CANDIDATE_PENDING_EXACT_QUALIFICATION"})
    reg["normative_basis"] = ["BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md",
                              "BDB_AUDIT_V2_ARCHITECTURE_SPEC_R5_4.md", "ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md"]
    reg["predecessor_identity"] = {"registry_id": base["registry_id"],
        "registry_raw_digest": digest((CONTEXT / "BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY.json").read_bytes()),
        "candidate_set_digest": PREDECESSOR_SET}
    reg["validation_layer_profiles"]["NF02_PROVENANCE"] = [f"L{i}" for i in range(1, 7)]
    binding = new_row("assignment_package_binding", 1,
        "sole immutable exact raw package authorization for one exact prior accepted AssignmentManifest; not delivery receipt",
        [ref_rule("assignment_ref", ["assignment_manifest"], "1", "PRIOR_ACCEPTED_ONLY", allowed_versions=["1"]),
         ref_rule("binding_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
         ref_rule("package_raw_ref", ["raw_artifact_ref"], "1", "CONTENT_OBJECT", retained_raw_reuse="EXPLICIT_IDENTICAL_RAW_ALLOWED"),
         ref_rule("package_raw_ref.artifact_contract_ref", ["external_profile_ref"], "1", "PINNED_PROFILE_REF")], ["binding_id"])
    binding["cross_object_rules"] = ["NF02_BINDING_PRIOR_ASSIGNMENT", "NF02_ONE_BINDING_PER_EXACT_ASSIGNMENT",
        "NF02_BINDING_CREATED_ACTIVE_ATTEMPT_ONLY", "NF02_PACKAGE_RAW_DURABLE_DIGEST_LENGTH",
        "NF02_PACKAGE_CONTEXT_DERIVED_FROM_ASSIGNMENT", "NF02_PACKAGE_SEMANTIC_PROFILE_CHECK",
        "NF02_NO_PRIOR_DELIVERY_OR_START", "NF02_BINDING_EXACT_COMMAND_RETRY_ONLY"]
    evidence = new_row("lane_result_admission_evidence", 2,
        "trusted acceptance of exact result raw for exact assignment, its unique prior binding and declared result slot; no evidence truth",
        [ref_rule("assignment_ref", ["assignment_manifest"], "1", "PRIOR_ACCEPTED_ONLY", allowed_versions=["1"]),
         ref_rule("package_binding_ref", ["assignment_package_binding"], "1", "PRIOR_ACCEPTED_ONLY", allowed_versions=["1"]),
         ref_rule("result_slot_contract_ref", ["result_slot_contract_ref"], "1", "PINNED_PROFILE_REF"),
         ref_rule("admission_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
         ref_rule("result_raw_ref", ["raw_artifact_ref"], "1", "CONTENT_OBJECT", retained_raw_reuse="EXPLICIT_IDENTICAL_RAW_ALLOWED"),
         ref_rule("result_raw_ref.artifact_contract_ref", ["external_profile_ref"], "1", "PINNED_PROFILE_REF")], ["admission_evidence_id"])
    evidence["cross_object_rules"] = ["NF02_BINDING_ASSIGNMENT_EXACT_EQUALITY", "NF02_DERIVED_ATTEMPT_SOURCE_PROFILE_EQUALITY",
        "NF02_UNIQUE_PRIOR_BINDING", "NF02_DECLARED_EXACT_SLOT", "NF02_PRIOR_STARTED_TRANSITION",
        "NF02_AUTHENTICATED_STORE_DERIVATION", "NF02_RESULT_RAW_DURABLE_DIGEST_LENGTH", "NF02_RESULT_TRANSPORT_CLAIMS_CHECK"]
    result = new_row("bdb_audit_lane_result", 2,
        "exact normalized external result content/provenance accepted for one declared result slot; no automatic qualification",
        [ref_rule("admission_evidence_ref", ["lane_result_admission_evidence"], "1", "PRIOR_ACCEPTED_ONLY", allowed_versions=["2"]),
         ref_rule("result_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT")], ["lane_result_id", "result_payload"])
    result["ordering_rules"] = {"result_payload.findings": "SEQUENCE_PRESERVE_TRANSPORT_ORDER; distinct external finding_id",
        "result_payload.outputs.*.member_paths": "UTF8_PATH_SORTED_UNIQUE",
        "result_payload.findings[].evidence_member_paths": "UTF8_PATH_SORTED_UNIQUE"}
    result["cross_object_rules"] = ["NF02_RESULT_PRIOR_EVIDENCE", "NF02_RESULT_EXACT_RAW_NORMALIZATION",
        "NF02_RESULT_SINGLE_EXACT_SLOT", "NF02_RESULT_RECEIVED_TO_ACCEPTED", "NF02_NO_MATERIAL_TYPED_REFS_IN_PAYLOAD"]
    schema_reg = new_row("schema_registry", 2, "exact registered semantic key to exact executable schema raw bytes under one pinned ArtifactContractRegistry",
        [ref_rule("artifact_contract_registry_ref", ["artifact_contract_registry"], "1", "PINNED_PROFILE_REF", allowed_versions=["1"]),
         ref_rule("serialization_profile_ref", ["serialization_profile_pin"], "1", "PINNED_PROFILE_REF"),
         ref_rule("validator_profile_ref", ["external_profile_ref"], "1", "PINNED_PROFILE_REF"),
         ref_rule("compatibility_rules_ref", ["external_profile_ref"], "1", "PINNED_PROFILE_REF"),
         ref_rule("bindings[].schema_raw_ref", ["raw_artifact_ref"], "1 per entry; bindings 1..N", "CONTENT_OBJECT", retained_raw_reuse="EXPLICIT_IDENTICAL_RAW_ALLOWED"),
         ref_rule("bindings[].schema_raw_ref.artifact_contract_ref", ["external_profile_ref"], "1 per entry", "PINNED_PROFILE_REF")], ["schema_registry_id", "bindings[].schema_key", "bindings[].status"])
    schema_reg["ordering_rules"] = {"bindings": "UTF8_SCHEMA_KEY_ASCENDING; UNIQUE_KEY", "bindings[].status": "ACTIVE_ONLY"}
    schema_reg["cross_object_rules"] = ["NF02_SCHEMA_KEY_REGISTERED_VERSION", "NF02_SCHEMA_BYTES_EXACT_DIGEST_LENGTH_ID_DIALECT",
        "NF02_SCHEMA_DEPENDENCY_CLOSURE_OFFLINE", "NF02_SCHEMA_EXTERNAL_BOOTSTRAP_ROOT", "NF02_SCHEMA_CONTEXT_NO_LATEST_OR_SELF_UPGRADE"]
    rows = [binding, evidence, result, schema_reg]
    reg["contracts"] = sorted(reg["contracts"] + rows, key=lambda c: (c["kind"], int(c["version"])))
    reg["foundation_inline_reference_contract_kinds"] = sorted(set(reg["foundation_inline_reference_contract_kinds"] + [c["kind"] for c in rows[:3]]))
    reg["foundation_inline_reference_contract_versions"] = [f"{c['kind']}/{c['version']}" for c in rows]
    reg["profiles"]["NF02_R5_4_ACTIVATION_V1"] = {
        "new_campaign_only": True, "in_place_schema_upgrade": "FORBIDDEN",
        "retroactive_package_binding": "FORBIDDEN", "nf02_v1_to_v2_alias": "FORBIDDEN",
        "historical_only_versions": ["schema_registry/1"], "nf02_allowed_versions": ["assignment_package_binding/1", "lane_result_admission_evidence/2", "bdb_audit_lane_result/2", "schema_registry/2"],
        "first_acceptance": "registered key + exact schema bytes/digest + accepted/pinned SchemaRegistry + domain predicates",
        "result_payload_material_refs": "NONE; finite transport-member-addressed payload only",
        "generic_command_bypass": "FORBIDDEN",
        "completion_consumption": "lane_completion.required_output_refs and stage_completion.required_output_refs may resolve bdb_audit_lane_result/2 only after complete original completion predicates; admission evidence alone cannot close a lane"}
    reg["profiles"]["NF02_PROVENANCE"] = {"layers": [f"L{i}" for i in range(1, 7)],
        "truth_qualification": "NOT_ESTABLISHED", "completion_L7": "SEPARATELY_REQUIRED"}
    reg["profiles"]["NF02_COMMAND_PROFILE_V1"] = {
        "BIND_ASSIGNMENT_PACKAGE": {"producer_authority": "TRUSTED_COORDINATOR_ACCEPTANCE", "closure": ["command_envelope/1", "assignment_package_binding/1"], "input": "CURRENT_ACCEPTED_HEAD_WITH_PRIOR_ASSIGNMENT", "raw": "VERIFIED_AND_RETAINED_ATOMICALLY", "event_effect": "ArtifactAccepted with exact binding artifact_ref; no attempt state transition"},
        "INGEST_EXTERNAL_LANE_RESULT": {"producer_authority": "TRUSTED_COORDINATOR_ACCEPTANCE", "closure": ["command_envelope/1", "lane_result_admission_evidence/2"], "input": "PRIOR_ASSIGNMENT_BINDING_AND_STARTED", "raw": "VERIFIED_AND_RETAINED_ATOMICALLY", "event_effect": "RESULT_RECEIVED_IF_LEGAL"},
        "RECORD_FOUNDATION_FACT": {"nf02_result_gate": "EXACT_PRIOR_EVIDENCE_AND_SLOT_AND_FSM; no generic bypass"},
        "AttemptStarted": {"mechanism": "EXISTING_ACCEPTED_TRANSITION_EVENT_AND_COMMAND_ENVELOPE", "binding_ref_class": "PRIOR_ACCEPTED_ONLY", "same_commit_binding": "FORBIDDEN", "producer_authority": "TRUSTED_COORDINATOR_ACCEPTANCE"}}
    return base, reg, rows


def definitions(reg):
    schema_ref = closed({"kind": {"const": "schema"}, "revision_digest": SHA})
    typed = closed({"kind": {"enum": sorted({c["kind"] for c in reg["contracts"]})},
        "logical_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"},
        "revision_digest": SHA, "digest_profile": {"const": OBJECT_PROFILE}, "schema_revision_ref": local_ref("schema_revision_ref")},
        ["kind", "revision_digest", "digest_profile", "schema_revision_ref"])
    profile = closed({"profile_id": {"type": "string", "pattern": r"^[A-Za-z][A-Za-z0-9_:.\-/]{0,127}$"}, "revision_digest": SHA})
    head = closed({"campaign_id": NONEMPTY, "commit_seq": {**INTEGER, "minimum": 1}, "commit_hash": SHA})
    policy_ref = local_ref("typed_ref")
    accepted_cut = closed({"campaign_id": NONEMPTY, "accepted_head_seq": {**INTEGER, "minimum": 1}, "accepted_head_hash": SHA,
                          "governing_policy_ref": policy_ref, "governing_spec_refs": array(local_ref("typed_ref"), 1, True)})
    empty_cut = closed({"kind": {"const": "EMPTY_HISTORY_CUT"}, "history_namespace_ref": local_ref("external_profile_ref"),
                       "governing_policy_ref": policy_ref, "governing_spec_refs": array(local_ref("typed_ref"), 1, True)})
    raw = closed({"raw_digest": SHA, "byte_length": INTEGER, "media_type": NONEMPTY, "artifact_contract_ref": local_ref("external_profile_ref")})
    path = {"type": "string", "minLength": 1, "maxLength": 512, "pattern": "^[A-Za-z0-9][A-Za-z0-9._/-]*$"}
    finding = closed({"finding_id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"},
                      "title": NONEMPTY, "statement": NONEMPTY, "evidence_member_paths": array(local_ref("member_path"), 0, True),
                      "reported_severity": {"enum": ["BLOCKER", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]}})
    outputs = closed({key: closed({"member_paths": array(local_ref("member_path"), 0, True)}) for key in ["report", "evidence", "logs"]}, [])
    payload = closed({"findings": array(local_ref("finding")), "outputs": outputs, "notes": {"type": ["string", "null"]}})
    return {"schema_revision_ref": schema_ref, "typed_ref": typed, "external_profile_ref": profile,
        "raw_ref": raw, "accepted_head_ref": head, "accepted_history_cut": accepted_cut,
        "empty_history_cut": empty_cut, "history_cut": {"oneOf": [local_ref("accepted_history_cut"), local_ref("empty_history_cut")]},
        "member_path": path, "finding": finding, "result_payload": payload}


def typed_for(kind, defs):
    return {"allOf": [local_ref("typed_ref"), {"properties": {"kind": {"const": kind}}}]}


# Normative scalar/body fields transcribed from Data sections, never runtime schema dictionaries.
BODY_FIELDS = {
    "source_generation": ("source_generation_id source_identity_ref source_identity_profile_ref materialized_source_manifest_ref representation_refs", "repository_authority_ref snapshot_authority_ref parent_source_generation_ref", "DC8"),
    "source_identity": ("profile_ref authority_mode authorized_repository_or_snapshot_ref materialized_source_manifest_ref completeness_state", "git_commit_object_id git_tree_object_id", "DC8"),
    "source_manifest": ("entries", "", "DC8/ADR6"),
    "legacy_raw_ref": ("legacy_ref_id raw_digest byte_length media_type import_input_history_cut", "legacy_contract_hint original_path", "DC90/DC14.6"),
    "legacy_mechanical_validation_assessment": ("assessment_id legacy_ref assessment_input_history_cut legacy_schema_ref legacy_profile_ref mechanical_validation_policy_ref parsed_legacy_variant_stage_facts integrity_check_results result reason_codes", "", "DC91"),
    "source_reconciliation_assessment": ("assessment_id legacy_ref assessment_input_history_cut target_source_generation_ref identity_profile_ref reconciliation_policy_ref raw_identifiers normalized_identity_body_ref result reason_codes", "", "DC91"),
    "lineage_admission_assessment": ("assessment_id legacy_ref assessment_input_history_cut admission_policy_ref mechanical_validation_assessment_ref source_reconciliation_assessment_ref requested_role validation_level freshness_binding_refs result reason_codes", "predecessor_pin_ref", "DC91"),
    "legacy_exposure_reconstruction_assessment": ("assessment_id legacy_ref assessment_input_history_cut reconstruction_policy_ref declared_scope controlled_exposure_fact_refs known_missing_channel_classes confidence supporting_history_refs blind_origin_claim_scope limitations", "", "DC91"),
    "trusted_predecessor_selection_decision": ("trusted_predecessor_selection_decision_id selection_input_history_cut candidate_legacy_refs source_reconciliation_assessment_ref lineage_admission_assessment_ref selection_policy_ref predecessor_pin_ref decision reason_codes", "selected_legacy_ref", "DC14.6/DC91"),
    "bootstrap_admission_decision": ("bootstrap_admission_decision_id legacy_ref requested_role mechanical_validation_assessment_ref source_reconciliation_assessment_ref lineage_admission_assessment_ref admission_policy_ref admission_input_history_cut result limitations reason_codes", "trusted_predecessor_selection_ref exposure_reconstruction_assessment_ref", "DC14.6/DC91"),
    "campaign_genesis": ("campaign_id input_history_cut bootstrap_admission_decision_ref source_generation_ref application_generation_ref protocol_policy_bundle_ref schema_set_ref owner_operator_authority_ref trust_profile_ref legacy_origin_refs", "", "DC9/DC14.6"),
    "stage_run": ("stage_run_id campaign_ref stage_spec_ref source_generation_ref creation_input_history_cut assigned_history_cut predecessor_stage_completion_refs required_lane_slot_contract_refs", "successor_of_stage_run_ref", "DC14.1"),
    "lane_run": ("lane_run_id stage_run_ref lane_spec_ref source_generation_ref creation_input_history_cut required_result_slots", "successor_of_lane_run_ref", "DC14.1"),
    "attempt": ("attempt_id lane_run_ref attempt_nonce executor_profile_ref delivery_profile_ref assigned_history_cut result_slot_contracts", "retry_of_attempt_ref retry_reason_ref", "DC14.1"),
    "assignment_manifest": ("assignment_manifest_id attempt_ref source_generation_ref assignment_input_history_cut knowledge_state_ref grant_refs view_manifest_refs executor_profile_ref delivery_profile_ref stage_spec_ref lane_spec_ref result_slot_contract_refs", "", "DC14.4"),
    "grant_body": ("grant_id attempt_ref grant_input_history_cut view_manifest_ref delivery_profile_ref forbidden_knowledge_policy_ref channel_class", "previous_knowledge_state_ref capability_profile_ref", "DC14.3"),
    "potential_exposure_record": ("exposure_id attempt_ref grant_ref view_manifest_ref channel_class exposure_input_history_cut", "previous_knowledge_state_ref", "DC14.3"),
    "knowledge_state": ("knowledge_state_id knowledge_state_revision attempt_ref basis_history_cut allowed_view_refs potential_exposure_refs contamination_assessment_refs isolation_qualification_ref", "previous_knowledge_state_ref", "DC23"),
    "isolation_qualification": ("isolation_qualification_id attempt_ref assessment_input_history_cut executor_profile_ref delivery_profile_ref channel_inventory_ref enforcement_receipt_refs filesystem_boundary_evidence_refs network_boundary_evidence_refs tool_boundary_evidence_refs session_boundary_evidence_refs contamination_assessment_refs required_isolation_assurance result scope limitations reason_codes", "", "DC22.2"),
    "contamination_assessment": ("contamination_assessment_id attempt_ref assessment_input_history_cut forbidden_knowledge_policy_ref channel_inventory_ref potential_exposure_refs forbidden_knowledge_match_refs observation_or_channel_evidence_refs result scope limitations reason_codes", "", "DC22.1"),
}
BOOTSTRAP_KINDS = ["command_envelope", "commit_body", "command_receipt", "history_cut", "installation_bootstrap_profile",
    "trusted_predecessor_selection_decision", "bootstrap_admission_decision", "campaign_genesis", "source_generation",
    "source_identity", "source_manifest", "legacy_raw_ref", "legacy_mechanical_validation_assessment", "source_reconciliation_assessment",
    "lineage_admission_assessment", "legacy_exposure_reconstruction_assessment", "artifact_contract_registry", "policy_revision", "spec_revision", "trust_profile"]


def common_schema(key, shape, refs, defs, citation):
    return {"$schema": DIALECT, "$id": key, "$defs": copy.deepcopy(defs),
            "x-bdb-material-refs": copy.deepcopy(refs), "x-bdb-normative-source": citation,
            "x-bdb-cjson-profile": "BDB-CJSON-1", **shape}


def scalar_or_ref(field, row):
    rule = next((r for r in row["material_refs"] if r["field"] == field), None)
    if field.endswith("_history_cut") or field in {"basis_history_cut", "input_history_cut", "assigned_history_cut"}:
        return local_ref("history_cut")
    if field in {"raw_digest", "command_digest"}:
        return SHA
    if field in {"byte_length", "knowledge_state_revision"}:
        return INTEGER
    if field in {"campaign_ref", "owner_operator_authority_ref"}:
        return NONEMPTY
    if rule:
        target = rule["allowed"][0]
        ext = target in {"external_profile_ref", "serialization_profile_pin", "source_identity_profile_pin", "history_namespace_ref", "result_slot_contract_ref", "predecessor_pin_ref", "application_generation_ref", "protocol_policy_bundle_ref", "repository_or_snapshot_authority_ref"}
        value = local_ref("raw_ref") if target == "raw_artifact_ref" else (local_ref("external_profile_ref") if ext else (typed_for(target, None) if target not in {"registered_immutable_object", "schema_set_ref"} else local_ref("typed_ref")))
        if rule["cardinality"].startswith(("0..N", "1..N", "0..*", "1..*")):
            return array(value, 1 if rule["cardinality"].startswith("1") else 0, True)
        return value
    if field.endswith(("_refs", "_contracts", "_slots")):
        return array(local_ref("external_profile_ref"), 0, True)
    if field in {"reason_codes", "known_missing_channel_classes", "limitations", "integrity_check_results"}:
        return array(NONEMPTY, 0, True)
    if field in {"parsed_legacy_variant_stage_facts", "raw_identifiers"}:
        return {"type": "object"}
    if field == "scope":
        return {"type": "object"}
    if field.endswith("_ref"):
        return local_ref("external_profile_ref")
    return NONEMPTY


def inherited_schemas(reg, defs):
    rows = {(c["kind"], c["version"]): c for c in reg["contracts"]}
    schemas = {}
    for kind, (required, optional, citation) in BODY_FIELDS.items():
        row = rows[(kind, "1")]
        # Complete material-ref fields are present even if section abbreviates scalar display.
        fields = dict.fromkeys((required + " " + optional).split())
        for rule in row["material_refs"]:
            if "." not in rule["field"]:
                fields.setdefault(rule["field"], None)
        props = {field: scalar_or_ref(field, row) for field in fields}
        req = required.split()
        shape = closed(props, req)
        if kind == "source_manifest":
            entry = closed({"repo_relative_posix_path": local_ref("member_path"), "entry_type": {"enum": ["REGULAR_FILE", "SYMLINK", "SUBMODULE", "OTHER_ALLOWED"]},
                "relevant_mode": NONEMPTY, "byte_length": INTEGER, "content_raw_digest": SHA,
                "symlink_target": NONEMPTY, "submodule_object_id": NONEMPTY, "lfs_pointer_state": NONEMPTY},
                ["repo_relative_posix_path", "entry_type", "relevant_mode"])
            entry["allOf"] = [
                {"if": {"properties": {"entry_type": {"const": "REGULAR_FILE"}}}, "then": {"required": ["byte_length", "content_raw_digest"]}},
                {"if": {"properties": {"entry_type": {"const": "SYMLINK"}}}, "then": {"required": ["symlink_target"]}},
                {"if": {"properties": {"entry_type": {"const": "SUBMODULE"}}}, "then": {"required": ["submodule_object_id"]}}]
            props["entries"] = array(entry, 0)
        if kind == "source_generation":
            shape["oneOf"] = [{"required": ["repository_authority_ref"], "not": {"required": ["snapshot_authority_ref"]}},
                              {"required": ["snapshot_authority_ref"], "not": {"required": ["repository_authority_ref"]}}]
        enums = {
            "source_identity": ("authority_mode", ["AUTHORIZED_GIT", "AUTHORIZED_SNAPSHOT"]),
            "legacy_mechanical_validation_assessment": ("result", ["VALID", "INVALID", "INSUFFICIENT_DATA"]),
            "source_reconciliation_assessment": ("result", ["EXACT_MATCH", "CONFLICT", "INSUFFICIENT_DATA"]),
            "lineage_admission_assessment": ("result", ["ADMITTED", "ADMITTED_WITH_LIMIT", "BLOCKED"]),
            "legacy_exposure_reconstruction_assessment": ("confidence", ["EXACT", "STRONG", "PARTIAL", "UNKNOWN"]),
            "trusted_predecessor_selection_decision": ("decision", ["SELECTED", "REJECTED", "CONFLICTED", "INSUFFICIENT_DATA"]),
            "bootstrap_admission_decision": ("result", ["CANONICAL_BOOTSTRAP_ADMITTED", "CANONICAL_BOOTSTRAP_ADMITTED_WITH_EXPOSURE_LIMIT", "BLOCKED_CANONICAL_ADMISSION"]),
            "contamination_assessment": ("result", ["CLEAN", "CONTAMINATED", "UNKNOWN", "NOT_APPLICABLE"]),
            "isolation_qualification": ("result", ["ENFORCED", "DECLARED", "UNKNOWN"]),
        }
        if kind in enums:
            field, values = enums[kind]; props[field] = {"enum": values}
        if kind == "source_identity":
            shape.update({"if": {"properties": {"authority_mode": {"const": "AUTHORIZED_GIT"}}}, "then": {"required": ["git_commit_object_id", "git_tree_object_id"]}})
        if kind == "trusted_predecessor_selection_decision":
            shape.update({"if": {"properties": {"decision": {"const": "SELECTED"}}}, "then": {"required": ["selected_legacy_ref"]}})
        if kind == "bootstrap_admission_decision":
            shape.update({"if": {"properties": {"requested_role": {"const": "CANONICAL_PREDECESSOR"}}}, "then": {"required": ["trusted_predecessor_selection_ref"]}})
        schemas[row["schema_ref"]] = common_schema(row["schema_ref"], shape, row["material_refs"], defs, citation)
    history = rows[("history_cut", "1")]
    schemas[history["schema_ref"]] = common_schema(history["schema_ref"], local_ref("history_cut"), history["material_refs"], defs, "DC15.4; inherited tagged value variants")
    command = rows[("command_envelope", "1")]
    cmd_fields = {"command_id": NONEMPTY, "command_kind": NONEMPTY, "actor_ref": NONEMPTY,
        "expected_parent_head": {"oneOf": [{"const": "EMPTY_HISTORY"}, local_ref("accepted_head_ref")]},
        "governing_policy_ref": typed_for("policy_revision", defs), "governing_spec_refs": array(typed_for("spec_revision", defs), 1, True),
        "idempotency_scope": NONEMPTY, "campaign_ref": NONEMPTY, "proposed_campaign_id": NONEMPTY,
        "history_namespace_ref": local_ref("external_profile_ref"), "bootstrap_profile_ref": typed_for("installation_bootstrap_profile", defs),
        "command_payload_ref": local_ref("typed_ref"), "command_payload": {"type": "object"}}
    cmd = closed(cmd_fields, "command_id command_kind actor_ref expected_parent_head governing_policy_ref governing_spec_refs idempotency_scope".split())
    cmd["allOf"] = [{"oneOf": [{"required": ["command_payload"], "not": {"required": ["command_payload_ref"]}},
                                {"required": ["command_payload_ref"], "not": {"required": ["command_payload"]}}]},
        {"if": {"properties": {"command_kind": {"const": "INITIALIZE_CAMPAIGN_FROM_LEGACY"}}},
         "then": {"required": ["proposed_campaign_id", "history_namespace_ref", "bootstrap_profile_ref"], "properties": {"expected_parent_head": {"const": "EMPTY_HISTORY"}}, "not": {"required": ["campaign_ref"]}},
         "else": {"required": ["campaign_ref"], "not": {"anyOf": [{"required": [f]} for f in ["proposed_campaign_id", "history_namespace_ref", "bootstrap_profile_ref"]]}, "properties": {"expected_parent_head": local_ref("accepted_head_ref")}}}]
    schemas[command["schema_ref"]] = common_schema(command["schema_ref"], cmd, command["material_refs"], defs, "DC15.1; payload domain guards are cross validators")
    commit = rows[("commit_body", "1")]
    props = {"campaign_id": NONEMPTY, "commit_seq": {**INTEGER, "minimum": 1}, "prev_history_ref": cmd_fields["expected_parent_head"],
             "command_ref": typed_for("command_envelope", defs), "command_digest": SHA, "actor_ref": NONEMPTY,
             "expected_parent_head": cmd_fields["expected_parent_head"], "governing_policy_ref": typed_for("policy_revision", defs),
             "governing_spec_refs": cmd_fields["governing_spec_refs"], "ordered_event_bodies": array({"type": "object"}),
             "immutable_object_refs": array(local_ref("typed_ref"), 0, True)}
    schemas[commit["schema_ref"]] = common_schema(commit["schema_ref"], closed(props), commit["material_refs"], defs, "DC15.2; union-Kahn/order predicates outside schema")
    receipt = rows[("command_receipt", "1")]
    props = {"command_id": NONEMPTY, "command_digest": SHA, "command_ref": typed_for("command_envelope", defs),
             "accepted_commit_ref": typed_for("commit_body", defs), "accepted_head": local_ref("accepted_head_ref"),
             "result_object_refs": array(local_ref("typed_ref"), 0, True)}
    schemas[receipt["schema_ref"]] = common_schema(receipt["schema_ref"], closed(props), receipt["material_refs"], defs, "DC15.3; post-acceptance sidecar")
    installation = rows[("installation_bootstrap_profile", "1")]
    props = {"installation_bootstrap_profile_id": NONEMPTY, "allowed_initial_command_kind": {"const": "INITIALIZE_CAMPAIGN_FROM_LEGACY"}}
    for rule in installation["material_refs"]:
        target = rule["allowed"][0]
        props[rule["field"]] = typed_for(target, defs) if target in {"schema_registry", "artifact_contract_registry", "policy_revision", "spec_revision", "trust_profile"} else local_ref("external_profile_ref")
    schemas[installation["schema_ref"]] = common_schema(installation["schema_ref"], closed(props), installation["material_refs"], defs, "DC14.6; exact external LOCAL_PINNED revision, all eight pins")
    return schemas


def context_schemas(reg, defs):
    """Freeze existing deferred schema keys from complete normative profile fields.

    No existing EXPLICIT_COMPLETE Registry row is changed. For deferred profile
    rows, executable schemas state the material-ref inventory that empty rows
    deliberately defer; these inventories are also recorded in the catalog.
    """
    rows = {(c["kind"], c["version"]): c for c in reg["contracts"]}
    scalar_fields = {
        "stage_spec": ("stage_key stage_spec_revision stage_role stage_ordinal purpose predecessor_requirements required_lane_slots optional_lane_slots blind_reveal_phase_model allowed_corpus_roles forbidden_corpus_roles coverage_obligation_policy_ref required_stage_completion_outputs transition_policy_ref stop_e6_relationship", "DC10"),
        "lane_spec": ("lane_key lane_spec_revision stage_spec_revision purpose primary_strategy scope_selectors exploration_policy_ref allowed_view_classes forbidden_knowledge_classes required_isolation_assurance required_outputs executor_capability_requirements budget_effort_profile_ref completion_predicate_ref", "DC11"),
        "executor_spec": ("executor_profile_id executor_profile_revision executor_tool_ref runtime_profile_ref supported_capabilities isolation_capabilities filesystem_boundary_ref network_boundary_ref tool_boundary_ref session_freshness_contract evidence_collection_capabilities known_limitations", "DC12"),
        "delivery_spec": ("delivery_profile_id delivery_profile_revision delivery_channel grant_before_delivery_required view_manifest_required ack_semantics retry_policy_ref idempotency_policy_ref potential_exposure_point redaction_profile_ref resolver_capabilities", "DC13"),
        "view_manifest": ("view_id projection_policy_ref allowed_member_refs metadata_projection resolver_capability_profile_ref forbidden_knowledge_policy_ref", "ARCH positive restricted view; exact profile-bound schema"),
        "projection_policy": ("projection_policy_id allowed_view_classes forbidden_knowledge_classes metadata_policy resolver_policy", "ARCH positive view; no negative-redaction shortcut"),
    }
    arr_fields = {"predecessor_requirements", "required_lane_slots", "optional_lane_slots", "allowed_corpus_roles", "forbidden_corpus_roles", "required_stage_completion_outputs", "scope_selectors", "allowed_view_classes", "forbidden_knowledge_classes", "required_outputs", "executor_capability_requirements", "supported_capabilities", "isolation_capabilities", "evidence_collection_capabilities", "known_limitations", "resolver_capabilities"}
    schemas = {}
    for kind, (field_string, citation) in scalar_fields.items():
        row = rows[(kind, "1")]
        props = {}; refs = []
        for f in field_string.split():
            if f.endswith("_ref"):
                target = "projection_policy" if f == "projection_policy_ref" else "external_profile_ref"
                props[f] = typed_for(target, defs) if target == "projection_policy" else local_ref("external_profile_ref")
                refs.append(ref_rule(f, [target], "1", "PINNED_PROFILE_REF" if target == "external_profile_ref" else "CONTENT_OR_PRIOR"))
            elif f == "allowed_member_refs":
                props[f] = array(local_ref("raw_ref"), 0, True)
                refs.extend([ref_rule(f, ["raw_artifact_ref"], "0..N", "CONTENT_OBJECT", retained_raw_reuse="EXPLICIT_IDENTICAL_RAW_ALLOWED"),
                             ref_rule("allowed_member_refs[].artifact_contract_ref", ["external_profile_ref"], "1 per raw member", "PINNED_PROFILE_REF")])
            elif f in arr_fields:
                props[f] = array(NONEMPTY, 0, True)
            elif f.endswith("_revision") or f == "stage_ordinal":
                props[f] = {**INTEGER, "minimum": 1}
            elif f in {"grant_before_delivery_required", "view_manifest_required"}:
                props[f] = {"const": True}
            elif f == "metadata_projection":
                props[f] = {"type": "object", "additionalProperties": TEXT}
            elif f == "required_isolation_assurance":
                props[f] = {"enum": ["ENFORCED", "DECLARED", "UNKNOWN"]}
            else:
                props[f] = NONEMPTY
        if kind == "executor_spec":
            props["model_profile_ref"] = local_ref("external_profile_ref")
            refs.append(ref_rule("model_profile_ref", ["external_profile_ref"], "0..1", "PINNED_PROFILE_REF"))
        schemas[row["schema_ref"]] = common_schema(row["schema_ref"], closed(props, field_string.split()), refs, defs, citation + "; deferred complete schema-bound inventory")
    return schemas


def nf02_schemas(reg, defs):
    rows = {(c["kind"], c["version"]): c for c in reg["contracts"]}
    shapes = {
        ("assignment_package_binding", "1"): closed({"binding_id": NONEMPTY, "assignment_ref": typed_for("assignment_manifest", defs),
            "binding_input_history_cut": local_ref("accepted_history_cut"), "package_raw_ref": local_ref("raw_ref")}),
        ("lane_result_admission_evidence", "2"): closed({"admission_evidence_id": NONEMPTY, "assignment_ref": typed_for("assignment_manifest", defs),
            "package_binding_ref": typed_for("assignment_package_binding", defs), "result_slot_contract_ref": local_ref("external_profile_ref"),
            "admission_input_history_cut": local_ref("accepted_history_cut"), "result_raw_ref": local_ref("raw_ref")}),
        ("bdb_audit_lane_result", "2"): closed({"lane_result_id": NONEMPTY, "admission_evidence_ref": typed_for("lane_result_admission_evidence", defs),
            "result_input_history_cut": local_ref("accepted_history_cut"), "result_payload": local_ref("result_payload")}),
        ("schema_registry", "2"): closed({"schema_registry_id": NONEMPTY, "artifact_contract_registry_ref": typed_for("artifact_contract_registry", defs),
            "serialization_profile_ref": local_ref("external_profile_ref"), "validator_profile_ref": local_ref("external_profile_ref"),
            "compatibility_rules_ref": local_ref("external_profile_ref"),
            "bindings": array(closed({"schema_key": {"type": "string", "pattern": "^BDB_SCHEMA_REGISTRY::[a-z][a-z0-9_]{0,63}/[1-9][0-9]{0,8}$"},
                "schema_raw_ref": local_ref("raw_ref"), "status": {"const": "ACTIVE"}}), 1)}),
    }
    schemas = {}
    for key, shape in shapes.items():
        row = rows[key]
        id_field = next(f for f in shape["properties"] if f.endswith("_id"))
        shape["properties"][id_field] = {"type": "string", "pattern": "^" + key[0] + "_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"}
        schemas[row["schema_ref"]] = common_schema(row["schema_ref"], shape, row["material_refs"], defs, "DC192 R5.4 NF02 approved successor contract")
    return schemas


def profile_pin(profile):
    return {"profile_id": profile["profile_id"], "revision_digest": digest(cjson(profile) + b"\n")}


def materialize_profiles(defs):
    profiles = {
        "BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1": {"profile_id": "BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1", "media_type": "application/schema+json", "identity": "RawDigest(exact schema bytes)", "dialect": DIALECT, "offline_only": True, "self_digest_in_body": "FORBIDDEN"},
        "NF02_PACKAGE_SEMANTIC_PROFILE_V1": {"profile_id": "NF02_PACKAGE_SEMANTIC_PROFILE_V1", "identity_type": "PackageSemanticDigest", "algorithm": "SHA256(BDB-CJSON-1({profile_ref,manifest:M,members}))", "manifest_excluded_fields": ["package_semantic_digest"], "excluded_members": ["MANIFEST.json"], "all_other_members_included": True, "member_sort": "UTF8_PATH", "member_fields": ["path", "raw_digest", "byte_length", "media_type"], "object_digest_domain": "NONE; this checksum is not ObjectDigest", "own_raw_digest": "FORBIDDEN"},
        "NF02_COMPATIBILITY_RULES_V1": {"profile_id": "NF02_COMPATIBILITY_RULES_V1", "foundation_revision": "R5.4", "new_campaign_only": True, "in_place_upgrade": "FORBIDDEN", "retroactive_binding": "FORBIDDEN", "nf02_v1_to_v2_alias": "FORBIDDEN", "historical_read": "EXACT_OLD_SCHEMA_AND_EXPLICITLY_LIMITED_ASSURANCE", "successor_trigger": "NO_NEW_SCHEMA_INSTALL_TRIGGER"},
        "BDB_R5_4_VALIDATOR_PROFILE_V1": {"profile_id": "BDB_R5_4_VALIDATOR_PROFILE_V1", "dialect": DIALECT, "backend": {"jsonschema": "4.25.1", "attrs": "26.1.0", "jsonschema-specifications": "2025.9.1", "referencing": "0.37.0", "rpds-py": "2026.6.3"}, "remote_resolution": "FORBIDDEN", "schema_ref_policy": "INLINED_LOCAL_DEFS_ONLY", "unknown_format": "REJECT; schemas use explicit patterns and no implicit format", "canonical": "BDB-CJSON-1; ASCII keys, safe integers, no floats, duplicate-key/lone-surrogate rejection", "validation_layers": [f"L{i}" for i in range(1,8)], "schema_validation_does_not_establish": ["accepted_history", "producer_authority", "raw_durability", "evidence_truth"]},
        "BDB_R5_4_SERIALIZATION_PIN_V1": {"profile_id": "BDB_R5_4_SERIALIZATION_PIN_V1", "canonical_profile": "BDB-CJSON-1", "object_digest_profile": OBJECT_PROFILE, "raw_digest": "SHA256(exact bytes)", "adr_raw_digest": digest((CONTEXT / "ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md").read_bytes()), "algorithms_changed": False},
        "BDB_R5_4_SOURCE_IDENTITY_PIN_V1": {"profile_id": "BDB_R5_4_SOURCE_IDENTITY_PIN_V1", "authority_modes": ["AUTHORIZED_GIT", "AUTHORIZED_SNAPSHOT"], "source_rule": "Exact independently authorized repository/snapshot identity and complete materialized SourceManifest; commit/tree IDs when applicable", "incomplete_lfs_or_submodules": "FAIL_CLOSED", "source_authority_self_bootstrap": "FORBIDDEN"},
        "BDB_R5_4_BOOTSTRAP_NAMESPACE_PIN_V1": {"profile_id": "BDB_R5_4_BOOTSTRAP_NAMESPACE_PIN_V1", "history_namespace_id": named_id("history_namespace", 1), "scope": "RESERVED_CANDIDATE_NAMESPACE; new campaign only", "reuse_nonempty_namespace": "FORBIDDEN", "other_namespace": "requires its own externally authorized exact installation revision before genesis"},
        "NF02_RESULT_NORMALIZER_V2": {"profile_id": "NF02_RESULT_NORMALIZER_V2", "input": "Retained safe result ZIP; exact MANIFEST.json", "canonical_output": ["findings", "outputs", "notes"], "findings_order": "PRESERVE_TRANSPORT_SEQUENCE", "finding_fields": ["finding_id", "title", "statement", "evidence_member_paths", "reported_severity"], "severity_authority": "EXTERNAL_ASSERTION_ONLY; no M/R/I or evidence qualification", "output_names": ["report", "evidence", "logs"], "evidence_member_paths": "SORTED_UNIQUE_EXISTING_ZIP_MEMBERS", "count": "DERIVED", "material_typed_refs": "FORBIDDEN", "metadata": "CHECK_AGAINST_PRIOR_ASSIGNMENT_BINDING_SLOT; retain claims in raw, do not copy authority fields", "notes": "NULL_OR_UNCHANGED_UNICODE_STRING"},
    }
    mime = {".json": "application/json", ".md": "text/markdown", ".txt": "text/plain", ".py": "text/x-python", "default": "application/octet-stream"}
    quota = {"max_archive_bytes": 67108864, "max_members": 1024, "max_member_bytes": 16777216, "max_total_expanded_bytes": 134217728, "max_path_bytes": 512, "actual_expansion_required": True}
    for name, wire in [("NF02_INPUT_PACKAGE_TRANSPORT_V2", "input"), ("NF02_RESULT_TRANSPORT_V2", "result")]:
        profiles[name] = {"profile_id": name, "version": "2", "schema_key": "BDB_PROFILE_SCHEMA::" + name,
            "media_type": "application/zip", "manifest_member": "MANIFEST.json", "path_grammar": "ASCII relative POSIX; no dot/empty segments, backslash, traversal, casefold collision, duplicates or special files",
            "mime_mapping": mime, "quotas": quota, "zip_format": "ZIP_STORED; UTF8 lexical member order; fixed 1980-01-01T00:00:00 timestamps; regular-file mode 0644; no archive/member comment, trailing/concatenated data or encryption", "representation_claim": "byte-identical only under exact qualified builder profile; RawDigest always exact", "checksum_self_reference": "FORBIDDEN", "wire_role": wire}
    profiles["NF02_EXTERNAL_LANE_SLOT_V2"] = {"profile_id": "NF02_EXTERNAL_LANE_SLOT_V2", "version": "2",
        "transport_ref": profile_pin(profiles["NF02_RESULT_TRANSPORT_V2"]), "normalizer_ref": profile_pin(profiles["NF02_RESULT_NORMALIZER_V2"]),
        "assignment_membership_required": True, "result_uniqueness": "ONE_EXACT_ASSIGNMENT_AND_SLOT", "result_kind": "bdb_audit_lane_result", "result_version": "2", "required_payload_fields": ["findings", "outputs", "notes"], "empty_findings": "PERMITTED; not automatic assurance PASS", "terminal_retry": "EXACT_ORIGINAL_BYTES_ONLY"}
    profiles["NF02_PROTOCOL_PROFILE_V2"] = {"profile_id": "NF02_PROTOCOL_PROFILE_V2", "foundation_revision": "R5.4",
        "input_transport_ref": profile_pin(profiles["NF02_INPUT_PACKAGE_TRANSPORT_V2"]),
        "result_transport_ref": profile_pin(profiles["NF02_RESULT_TRANSPORT_V2"]),
        "package_semantic_profile_ref": profile_pin(profiles["NF02_PACKAGE_SEMANTIC_PROFILE_V1"]),
        "result_slot_ref": profile_pin(profiles["NF02_EXTERNAL_LANE_SLOT_V2"]),
        "normalizer_ref": profile_pin(profiles["NF02_RESULT_NORMALIZER_V2"]),
        "binding_before_start_and_delivery": True, "capability": "RUNTIME_ONLY; never canonical authority or serialized token"}
    for name, value in profiles.items():
        json_file(CANDIDATE / "profiles" / (name + ".json"), value)
    return profiles


def transport_schemas(defs):
    member = closed({"path": local_ref("member_path"), "raw_digest": SHA, "byte_length": INTEGER, "media_type": NONEMPTY})
    base = {"assignment_ref": typed_for("assignment_manifest", defs), "attempt_ref": typed_for("attempt", defs),
        "source_generation_ref": typed_for("source_generation", defs), "assignment_input_history_cut": local_ref("accepted_history_cut"),
        "stage_spec_ref": typed_for("stage_spec", defs), "lane_spec_ref": typed_for("lane_spec", defs),
        "executor_profile_ref": typed_for("executor_spec", defs), "delivery_profile_ref": typed_for("delivery_spec", defs),
        "members": array(member, 0, True)}
    package = closed({**base, "transport_profile_ref": local_ref("external_profile_ref"),
        "result_slot_contract_refs": array(local_ref("external_profile_ref"), 1, True),
        "package_semantic_digest": closed({"profile_ref": local_ref("external_profile_ref"), "digest": SHA})})
    result = closed({**base, "transport_profile_ref": local_ref("external_profile_ref"),
        "package_binding_ref": typed_for("assignment_package_binding", defs), "result_slot_contract_ref": local_ref("external_profile_ref"),
        "input_package_digest": closed({"profile_ref": local_ref("external_profile_ref"), "digest": SHA}),
        "result_payload": local_ref("result_payload")})
    return {"BDB_PROFILE_SCHEMA::NF02_INPUT_PACKAGE_TRANSPORT_V2": common_schema("BDB_PROFILE_SCHEMA::NF02_INPUT_PACKAGE_TRANSPORT_V2", package, [], defs, "DC192/package profile; external raw manifest, not a canonical kind"),
            "BDB_PROFILE_SCHEMA::NF02_RESULT_TRANSPORT_V2": common_schema("BDB_PROFILE_SCHEMA::NF02_RESULT_TRANSPORT_V2", result, [], defs, "DC192/normalizer profile; untrusted raw result manifest")}


def schema_filename(key):
    return "schemas/" + key.split("::",1)[1].replace("/", "__") + ".schema.json"


def schema_ref(raw):
    return {"kind": "schema", "revision_digest": digest(raw)}


def typed_object(kind, version, body, schemas, logical_id=None):
    raw_schema = cjson(schemas[f"{SCHEMA_PREFIX}{kind}/{version}"]) + b"\n"
    ref = {"kind": kind, "revision_digest": object_digest(kind, version, body), "digest_profile": OBJECT_PROFILE,
           "schema_revision_ref": schema_ref(raw_schema)}
    if logical_id:
        ref["logical_id"] = logical_id
    return {"kind": kind, "version": str(version), "body": body, "ref": ref}


def pinned_initial_objects(reg, profiles, defs, schemas):
    # These are frozen initial policy/spec/trust subsets, not replacement semantics
    # for arbitrary historical /1 bodies. const schemas admit these exact initial revisions.
    initial = {
        "policy_revision": {"policy_id": named_id("policy_revision", 1), "revision": 1, "profile": "NF02_R5_4_POLICY_V1",
            "campaign_migration": "NEW_CAMPAIGN_ONLY", "conflict_rule": "REJECT_AND_NO_CANONICAL_MUTATION",
            "raw_retention": "EXACT_IMMUTABLE_PACKAGE_RESULT_AND_REQUIRED_EVIDENCE_CLOSURE", "truth": "ADMISSION_DOES_NOT_QUALIFY_FINDINGS_OR_EVIDENCE"},
        "spec_revision": {"spec_id": named_id("spec_revision", 1), "revision": 1, "profile": "NF02_R5_4_TRANSITION_PROFILE_V1",
            "protocol_profile_ref": profile_pin(profiles["NF02_PROTOCOL_PROFILE_V2"]),
            "initialization": "INITIALIZE_CAMPAIGN_FROM_LEGACY; EMPTY_HISTORY; one union-Kahn; BDB_BOOTSTRAP_PRECEDENCE_V1 exact scope only",
            "attempt_transitions": [["CREATED","STARTED"],["CREATED","CANCELLED"],["CREATED","SUPERSEDED"],
                ["STARTED","RESULT_RECEIVED"],["STARTED","FAILED"],["STARTED","BLOCKED"],["STARTED","CANCELLED"],["STARTED","SUPERSEDED"],
                ["RESULT_RECEIVED","RESULT_ACCEPTED"],["RESULT_RECEIVED","FAILED"],["RESULT_RECEIVED","BLOCKED"],["RESULT_RECEIVED","SUPERSEDED"]],
            "start_guard": "unique prior accepted binding, exact prior assignment and durable raw; separate later commit before delivery",
            "artifact_acceptance_transition_effects": {
                "assignment_package_binding/1": "ArtifactAccepted; remains CREATED; no delivery fact",
                "lane_result_admission_evidence/2": "ArtifactAccepted; STARTED to RESULT_RECEIVED iff all NF02 predicates pass",
                "bdb_audit_lane_result/2": "ArtifactAccepted; RESULT_RECEIVED to RESULT_ACCEPTED iff exact prior evidence and slot predicates pass"},
            "campaign_stage_lane_fsm": "Unchanged complete Data sections 14.1-14.2; no skip or added states",
            "delivery_guard": "Revalidate accepted authorization and terminal/source context under serialized boundary; release retained exact bytes only"},
        "trust_profile": {"trust_profile_id": named_id("trust_profile",1), "mode": "LOCAL_PINNED",
            "actors": "independently authenticated prior/installation-authorized actors; identity/command/profile metadata alone is not authorization",
            "installation": "explicit authorized exact pin after hash-bound governance qualification",
            "schema_root": "external exact executable schema raw pin before registry validation; no self-authorization",
            "capability": "unforgeable runtime primitive outside canonical body; raw accepted facts persist across legitimate key rotation",
            "sources": "independent repository/snapshot authority; no source self-bootstrap",
            "rollback_assurance": "process crashes do not qualify host/storage rollback; original anchor requirements retained"},
        "artifact_contract_registry": reg,
    }
    rows = {(c["kind"],c["version"]):c for c in reg["contracts"]}
    for kind, body in initial.items():
        row = rows[(kind,"1")]
        material_refs = row["material_refs"]
        if kind == "spec_revision":
            material_refs = material_refs + [ref_rule("protocol_profile_ref", ["external_profile_ref"], "1", "PINNED_PROFILE_REF")]
        schemas[row["schema_ref"]] = common_schema(row["schema_ref"], {"type":"object","const":body}, material_refs, defs,
            "DC192: exact initial R5.4 installation subset only; other revisions remain unbound/not accepted under this SchemaRegistry")
    return initial


def freeze_schemas_and_roots(reg, profiles, defs, schemas, initial):
    catalog = []
    for key, schema in sorted(schemas.items()):
        raw = cjson(schema) + b"\n"
        filename = schema_filename(key)
        write(CANDIDATE / filename, raw)
        catalog.append({"schema_key": key, "file": filename, "raw_digest": digest(raw), "byte_length": len(raw),
                        "$id": key, "dialect": DIALECT, "dependency_closure": [], "local_definitions_inlined": True,
                        "validator_profile_ref": profile_pin(profiles["BDB_R5_4_VALIDATOR_PROFILE_V1"]),
                        "scope": "CANONICAL_WIRE" if key.startswith(SCHEMA_PREFIX) else "EXTERNAL_TRANSPORT"})
    json_file(CANDIDATE / "SCHEMA_ARTIFACT_CATALOG_R5_4.json", {"schema":"BDB_R5_4_SCHEMA_ARTIFACT_CATALOG/1", "artifacts":catalog})
    roots = {kind: typed_object(kind, 1, body, schemas, body.get({"policy_revision":"policy_id","spec_revision":"spec_id","trust_profile":"trust_profile_id"}.get(kind,"none"))) for kind,body in initial.items()}
    body = {"schema_registry_id": named_id("schema_registry",1), "artifact_contract_registry_ref": roots["artifact_contract_registry"]["ref"],
        "serialization_profile_ref": profile_pin(profiles["BDB_R5_4_SERIALIZATION_PIN_V1"]),
        "validator_profile_ref": profile_pin(profiles["BDB_R5_4_VALIDATOR_PROFILE_V1"]),
        "compatibility_rules_ref": profile_pin(profiles["NF02_COMPATIBILITY_RULES_V1"]),
        "bindings": [{"schema_key":c["schema_key"],"schema_raw_ref":{"raw_digest":c["raw_digest"],"byte_length":c["byte_length"],"media_type":"application/schema+json","artifact_contract_ref":profile_pin(profiles["BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1"])},"status":"ACTIVE"} for c in catalog if c["scope"]=="CANONICAL_WIRE"]}
    roots["schema_registry"] = typed_object("schema_registry",2,body,schemas,body["schema_registry_id"])
    initial_pins = {
        "initial_schema_registry_ref": roots["schema_registry"]["ref"], "initial_artifact_contract_registry_ref": roots["artifact_contract_registry"]["ref"],
        "initial_serialization_profile_ref": profile_pin(profiles["BDB_R5_4_SERIALIZATION_PIN_V1"]),
        "initial_governing_policy_ref": roots["policy_revision"]["ref"], "initial_transition_profile_ref": roots["spec_revision"]["ref"],
        "initial_trust_profile_ref": roots["trust_profile"]["ref"], "initial_source_identity_profile_ref": profile_pin(profiles["BDB_R5_4_SOURCE_IDENTITY_PIN_V1"]),
        "allowed_history_namespace_ref": profile_pin(profiles["BDB_R5_4_BOOTSTRAP_NAMESPACE_PIN_V1"]),
    }
    profiles["BDB_R5_4_PROTOCOL_POLICY_BUNDLE_V1"] = {
        "profile_id": "BDB_R5_4_PROTOCOL_POLICY_BUNDLE_V1", "foundation_revision": "R5.4",
        "initial_pins": initial_pins, "governing_spec_set": [roots["spec_revision"]["ref"]],
        "protocol_profile_ref": profile_pin(profiles["NF02_PROTOCOL_PROFILE_V2"]),
        "migration_boundary": "NEW_CAMPAIGN_ONLY"}
    json_file(CANDIDATE / "profiles/BDB_R5_4_PROTOCOL_POLICY_BUNDLE_V1.json", profiles["BDB_R5_4_PROTOCOL_POLICY_BUNDLE_V1"])
    installation_body = {"installation_bootstrap_profile_id": named_id("installation_bootstrap_profile",1),
        "allowed_initial_command_kind":"INITIALIZE_CAMPAIGN_FROM_LEGACY", **initial_pins}
    roots["installation_bootstrap_profile"] = typed_object("installation_bootstrap_profile",1,installation_body,schemas,installation_body["installation_bootstrap_profile_id"])
    for kind,obj in roots.items():
        json_file(CANDIDATE / "objects" / (kind+"__"+obj["version"]+".json"),obj)
    root_catalog = next(c for c in catalog if c["schema_key"]==SCHEMA_PREFIX+"schema_registry/2")
    pin_bundle = {"schema":"BDB_R5_4_INSTALLATION_PIN_BUNDLE/1", "foundation_revision":"R5.4", "activation_status":"CANDIDATE_PREPARED_NOT_INSTALLED",
        "required_qualification":"hash-bound authorized governance qualification before activation; preparation is not trust installation",
        "installation_bootstrap_profile_ref":roots["installation_bootstrap_profile"]["ref"], "initial_pins":initial_pins,
        "protocol_policy_bundle_ref":profile_pin(profiles["BDB_R5_4_PROTOCOL_POLICY_BUNDLE_V1"]),
        "external_schema_root":{"schema_key":root_catalog["schema_key"],"file":root_catalog["file"],"raw_digest":root_catalog["raw_digest"],"byte_length":root_catalog["byte_length"],"dialect":DIALECT},
        "bootstrap_executable_schema_keys":[SCHEMA_PREFIX+k+("/2" if k=="schema_registry" else "/1") for k in BOOTSTRAP_KINDS+["schema_registry"]],
        "old_campaigns":"retain old exact sets; no install side effects or generic in-place upgrade",
        "initial_governing_spec_set":[roots["spec_revision"]["ref"]], "runtime_authority":"none until externally qualified/pinned installation and legal campaign initialization"}
    json_file(CANDIDATE / "INSTALLATION_PIN_BUNDLE_R5_4.json",pin_bundle)
    return catalog, roots, pin_bundle


def zip_bytes(members, timestamp=(1980,1,1,0,0,0)):
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_STORED) as z:
        for name,raw in sorted(members.items(),key=lambda p:p[0].encode("utf-8")):
            info=zipfile.ZipInfo(name,date_time=timestamp);info.compress_type=zipfile.ZIP_STORED
            info.create_system=3;info.external_attr=(0o100644<<16);z.writestr(info,raw)
    return out.getvalue()


def member_records(members, profiles):
    mapping=profiles["NF02_INPUT_PACKAGE_TRANSPORT_V2"]["mime_mapping"]
    return [{"path":n,"raw_digest":digest(b),"byte_length":len(b),"media_type":mapping.get(pathlib.PurePosixPath(n).suffix.lower(),mapping["default"])} for n,b in sorted(members.items(),key=lambda p:p[0].encode("utf-8")) if n!="MANIFEST.json"]


def fixtures(reg, profiles, schemas, roots):
    from fixture_builder import materialize
    return materialize(sys.modules[__name__], reg, profiles, schemas, roots)


def vectors(bodies, known, rows):
    base=json.loads((CONTEXT/"BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json").read_bytes())
    proposal=(REPO/"docs/NF02_NORMATIVE_CONTRACT_DECISION_PROPOSAL.md").read_text(encoding="utf-8")
    names=[]
    for name in re.findall(r"^\| (NF02_[A-Z0-9_]+) \|",proposal,re.M):
        if name not in names:names.append(name)
    mutations={
        "NF02_SCHEMA_UNREGISTERED_KIND_REJECT":("accept_binding","REMOVE_GOVERNING_REGISTRY_ROW"),
        "NF02_SCHEMA_BYTES_NOT_BOUND_REJECT":("accept_binding","REMOVE_SCHEMA_BINDING"),
        "NF02_SCHEMA_WRONG_DIGEST_REJECT":("accept_binding","FLIP_BOUND_SCHEMA_BYTE"),
        "NF02_SCHEMA_EXACT_BINDING_ACCEPT":("accept_binding","NONE"),
        "NF02_PACKAGE_BINDING_ACCEPT":("accept_binding","NONE"),
        "NF02_PACKAGE_BINDING_SECOND_CONFLICT_REJECT":("accept_binding","EXISTING_BINDING_DIFFERENT_RAW"),
        "NF02_PACKAGE_BINDING_EXACT_RETRY":("retry_binding","EXACT_COMMAND_AND_BODY_AFTER_AMBIGUOUS_ACK"),
        "NF02_PACKAGE_RAW_SUBSTITUTION_REJECT":("deliver_or_bind","REPLACE_WITH_REPACKED_PACKAGE_RAW"),
        "NF02_PACKAGE_SEMANTIC_MISMATCH_REJECT":("accept_evidence","CHANGE_RESULT_PACKAGE_SEMANTIC_ASSERTION"),
        "NF02_PACKAGE_WRONG_ASSIGNMENT_REJECT":("accept_binding","CHANGE_PACKAGE_ASSIGNMENT_EXACT_REF"),
        "NF02_PACKAGE_WRONG_ATTEMPT_REJECT":("accept_binding","CHANGE_PACKAGE_ATTEMPT_EXACT_REF"),
        "NF02_PACKAGE_WRONG_SOURCE_REJECT":("accept_binding","CHANGE_PACKAGE_SOURCE_EXACT_REF"),
        "NF02_RESULT_WITHOUT_PACKAGE_BINDING_REJECT":("accept_evidence","REMOVE_PRIOR_ACCEPTED_BINDING"),
        "NF02_RESULT_WRONG_PACKAGE_BINDING_REJECT":("accept_evidence","CHANGE_EXACT_BINDING_REF"),
        "NF02_PACKAGE_BINDING_AFTER_DELIVERY_REJECT":("accept_binding","SET_PRIOR_DELIVERY_OR_STARTED"),
        "NF02_BINDING_SAME_COMMIT_ASSIGNMENT_REJECT":("accept_binding","ASSIGNMENT_IN_CURRENT_CLOSURE_NOT_PRIOR"),
        "NF02_START_WITHOUT_PRIOR_BINDING_REJECT":("start_attempt","MISSING_OR_SAME_COMMIT_BINDING"),
        "NF02_DELIVERY_BEFORE_BINDING_REJECT":("deliver","REMOVE_PRIOR_BINDING_OR_STARTED"),
        "NF02_PACKAGE_SELF_HASH_REJECT":("accept_binding","INSERT_OWN_FINAL_RAW_HASH_OR_FORWARD_BINDING_REF"),
        "NF02_PACKAGE_REPACK_IDENTITY_SEPARATION":("deliver_or_bind","REPLACE_WITH_REPACKED_PACKAGE_RAW"),
        "NF02_SCHEMA_ROOT_SELF_AUTHORIZATION_REJECT":("initialize_or_accept","CALLER_SUPPLIED_UNPINNED_ROOT_OR_SAME_COMMIT_UPGRADE"),
        "NF02_ROLE_OR_ALIAS_REJECT":("resolve_contract","UNKNOWN_ROLE_ALIAS_VERSION_OR_REFERENCE_CLASS"),
        "NF02_CAPABILITY_FORGERY_REJECT":("accept_evidence","CALLER_SELECTED_INGEST_COMMAND_WITHOUT_AUTHENTICATED_PRODUCER"),
        "NF02_SECRET_ROTATION_HISTORY_REPLAY":("replay_then_write","ROTATE_RUNTIME_SECRET_REPLAY_FACTS_THEN_UNAUTHORIZED_WRITE"),
        "NF02_EVIDENCE_SAME_COMMIT_RESULT_REJECT":("accept_result","EVIDENCE_IN_CURRENT_CLOSURE_NOT_PRIOR"),
        "NF02_RESULT_PAYLOAD_MUTATION_REJECT":("accept_result","CHANGE_FINDING_STATEMENT_AFTER_EVIDENCE"),
        "NF02_RESULT_SLOT_CONFLICT_REJECT":("accept_result","CLOSED_SLOT_WITH_DIFFERENT_RAW_OR_WRONG_SLOT"),
        "NF02_PACKAGE_RESULT_RAW_MISSING_OR_CORRUPT_REJECT":("consume_authority","REMOVE_OR_FLIP_PACKAGE_RESULT_SCHEMA_OR_CANONICAL_BYTES"),
        "NF02_CONCURRENT_BINDING_CAS":("accept_binding_race","TWO_DIFFERENT_CANDIDATES_SAME_PARENT"),
        "NF02_RAW_HISTORY_CRASH_ATOMICITY":("binding_evidence_result_persistence","KILL_PROCESS_AT_EACH_PERSISTENCE_BOUNDARY"),
        "NF02_OLD_CAMPAIGN_WRITE_REJECT":("accept_binding_or_result","OLD_R5_3_CONTEXT_OR_RETROACTIVE_V1_ALIAS"),
        "NF02_PACKAGE_ZIP_JSON_ADVERSARIAL_REJECT":("parse_and_accept","UNSAFE_ZIP_OR_DUPLICATE_JSON_KEYS"),
    }
    if set(names)!=set(mutations):raise RuntimeError("PROPOSAL_VECTOR_INVENTORY_MISMATCH")
    variants={
        "NF02_SCHEMA_UNREGISTERED_KIND_REJECT":["new kind absent","unregistered ObjectDigest domain despite executable schema"],
        "NF02_PACKAGE_RAW_SUBSTITUTION_REJECT":["candidate raw differs","mutable workspace differs but retained bytes remain authoritative positive control"],
        "NF02_PACKAGE_SEMANTIC_MISMATCH_REJECT":["wrong checksum","wrong semantic profile"],
        "NF02_PACKAGE_WRONG_ASSIGNMENT_REJECT":["different assignment","same logical ID different revision","wrong schema identity"],
        "NF02_PACKAGE_WRONG_SOURCE_REJECT":["different generation","different tree","different independent authority"],
        "NF02_PACKAGE_BINDING_AFTER_DELIVERY_REJECT":["old prior STARTED","delivery callback already observed","zero prebinding disclosure positive control"],
        "NF02_BINDING_SAME_COMMIT_ASSIGNMENT_REJECT":["same-commit assignment","content present but unaccepted"],
        "NF02_START_WITHOUT_PRIOR_BINDING_REJECT":["missing binding","same-commit binding"],
        "NF02_SCHEMA_ROOT_SELF_AUTHORIZATION_REJECT":["caller root","same-commit context upgrade","latest installed set on old campaign"],
        "NF02_ROLE_OR_ALIAS_REJECT":["PROVENANCE","PROPOSAL","wire alias","version fallback","unknown ref class"],
        "NF02_CAPABILITY_FORGERY_REJECT":["command-name impersonation","trusted=true","forged token","copied other-assignment token","stale/replayed token"],
        "NF02_RESULT_SLOT_CONFLICT_REJECT":["closed slot different raw","wrong slot","omitted required slot"],
        "NF02_PACKAGE_RESULT_RAW_MISSING_OR_CORRUPT_REJECT":[a+" "+b+" before "+c for a in ["package","result","schema","canonical reference target"] for b in ["missing","corrupt"] for c in ["start","evidence","result","completion","reopen"]],
        "NF02_CONCURRENT_BINDING_CAS":["thread CAS","process CAS","exact loser idempotent","different loser conflict"],
        "NF02_RAW_HISTORY_CRASH_ATOMICITY":[a+" at "+b for a in ["binding","evidence","result"] for b in ["raw staging","accepted raw ref","immutable object","event","commit","head","receipt"]],
        "NF02_OLD_CAMPAIGN_WRITE_REJECT":["old campaign","retro binding","v1-to-v2 alias"],
        "NF02_PACKAGE_ZIP_JSON_ADVERSARIAL_REJECT":["duplicate keys","duplicate members","traversal","case collision","normalized collision","expansion bomb","quota exhaustion","symlink","truncated ZIP","concatenated/trailing ZIP","forbidden context property"],
    }
    fixture_raw=(CANDIDATE/"fixtures/NF02_OBJECT_FIXTURE_R5_4.json").read_bytes()
    from adversarial_builder import materialize as adversarial_inputs
    scenarios = adversarial_inputs(sys.modules[__name__], bodies, known,
        [(name, *mutations[name], variants.get(name, [mutations[name][1]])) for name in names])
    additions=[]
    positive={"NF02_SCHEMA_EXACT_BINDING_ACCEPT","NF02_PACKAGE_BINDING_ACCEPT"}
    mixed={"NF02_PACKAGE_BINDING_EXACT_RETRY","NF02_SECRET_ROTATION_HISTORY_REPLAY","NF02_CONCURRENT_BINDING_CAS","NF02_RAW_HISTORY_CRASH_ATOMICITY"}
    for name in names:
        operation,mutation=mutations[name]
        expected={"result":"ACCEPT","canonical_effects":"ONE_BINDING; exact known-answer identity"} if name in positive else {"result":"REJECT","canonical_state_mutation":"NONE"}
        if name=="NF02_PACKAGE_BINDING_EXACT_RETRY":expected={"result":"EXACT_RETRY","canonical_state_mutation":"NONE","receipt":"ORIGINAL","raw_reverified":True}
        if name=="NF02_SECRET_ROTATION_HISTORY_REPLAY":expected={"result":"REPLAY_ACCEPT_UNAUTHORIZED_WRITE_REJECT","canonical_state_mutation":"NONE","serialized_capability":"ABSENT"}
        if name=="NF02_CONCURRENT_BINDING_CAS":expected={"result":"ONE_WINNER_CONFLICTING_LOSER_REJECT","winner_effects":1,"loser_canonical_state_mutation":"NONE"}
        if name=="NF02_RAW_HISTORY_CRASH_ATOMICITY":expected={"result":"COMPLETE_DURABLE_CLOSURE_OR_NO_CANONICAL_MUTATION","partial_authority":"FORBIDDEN","preauthorization_disclosure":0}
        if name=="NF02_PACKAGE_REPACK_IDENTITY_SEPARATION":expected.update({"semantic_digest":"SAME","raw_digest":"DIFFERENT","replacement_authorization":"FORBIDDEN"})
        if name=="NF02_DELIVERY_BEFORE_BINDING_REJECT":expected["executor_disclosure_callbacks"]=0
        v={"id":name,"domain":"nf02_r5_4_normative_contract","title":name.replace("_"," "),
            "input":{"operation":operation,"fixture_ref":{"file":"fixtures/NF02_OBJECT_FIXTURE_R5_4.json","raw_digest":digest(fixture_raw),"byte_length":len(fixture_raw)},
                "mutation":mutation,"initial_context":{"foundation_revision":"R5.4","prior_assignment":True,"attempt_state":"CREATED" if operation in {"accept_binding","start_attempt"} else "STARTED", "prior_binding":operation not in {"accept_binding"},"prior_evidence":operation=="accept_result","actor_authenticated":True},
                "scenario_ref":scenarios[name],
                "variants":variants.get(name,[mutation]),"known_answer_ref":"fixtures/NF02_KNOWN_ANSWERS_R5_4.json",
                "canonical_snapshot_fields":["accepted_head","commits","events","accepted_objects","command_receipts","binding_selector","slot_selector","accepted_raw_refs"]},
            "expected":expected,"why":"Approved R5.4 contract; independently executable acceptance/disclosure/fault tests are required later. This vector is a design expectation, never runtime PASS."}
        additions.append(v)
    gv={"date":DATE,"purpose":"R5.4 successor normative design vectors; inherited expectations preserved exactly, new fixture bytes and known answers frozen; not runtime qualification evidence",
        "status":"R5_4_CANDIDATE_PENDING_EXACT_QUALIFICATION","vector_set_id":"BDB-AUDIT-V2-FOUNDATION-GOLDEN-VECTORS-R5-4-1",
        "predecessor_vector_raw_digest":digest((CONTEXT/"BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json").read_bytes()),
        "inherited_vector_count":len(base["vectors"]),"nf02_vector_count":len(additions),"vectors":base["vectors"]+additions,
        "inherited_current_label_scope":"R5N47 and similar R5.3 label vectors are predecessor assertions, not R5.4 current-set aliases",
        "runtime_execution_status":"NOT_RUN_N5_N11_NOT_IMPLEMENTED"}
    json_file(CANDIDATE/"BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json",gv)
    return gv


def section(text, heading, replacement):
    pattern=r"^"+re.escape(heading)+r"\n.*?(?=^# |\Z)"
    out,n=re.subn(pattern,replacement.rstrip()+"\n\n---\n\n",text,count=1,flags=re.M|re.S)
    if n!=1:raise RuntimeError("MISSING_NORMATIVE_SECTION: "+heading)
    return out


def materialize_corpus(reg, rows, catalog, roots, gv):
    proposal=(REPO/"docs/NF02_NORMATIVE_CONTRACT_DECISION_PROPOSAL.md").read_text(encoding="utf-8")
    # The proposal delta is now part of the successor source, not an external lookup.
    delta=proposal[proposal.index("### D.2. Proposed ArtifactContractRegistry rows"):proposal.index("## F. Alternatives considered")]
    delta=delta.replace("Proposed ArtifactContractRegistry rows","R5.4 canonical Registry contracts")
    delta=delta.replace("Poniższe są complete proposed rows, nie wpisy zastosowane do R5.3.","Poniższe są normatywne complete rows tej R5.4 candidate; nie modyfikują R5.3.")
    delta=delta.replace("propose `schema_registry/2`","define `schema_registry/2`").replace("Propose `schema_registry/2`","Define `schema_registry/2`")
    delta=delta.replace("proponowaną decyzją R5.4","właścicielsko zatwierdzoną decyzją R5.4")
    migration=proposal[proposal.index("## H. Migration semantics"):proposal.index("## I. Proposed normative files")]
    vec=proposal[proposal.index("## J. Golden / adversarial vectors"):proposal.index("## K. Ordered implementation plan")]
    plan=proposal[proposal.index("### N1 — approve normative delta"):proposal.index("## L. Owner decisions required")]
    header=("# BDB Audit v2 — R5.4 successor normative candidate\n\n"
        "Status: PENDING_EXACT_CANDIDATE_QUALIFICATION; not installed, not independent freeze, no runtime qualification.\n\n"
        f"Date: {DATE}. Predecessor R5.3.1 candidate set `{PREDECESSOR_SET}`; predecessor R5.3 set `{LEGACY_SET}`.\n\n"
        "This is a separate versioned successor. Owner approved the R5.4/NF02 design and new-campaign boundary. "
        "Predecessor references/status/reviews inside inherited history are provenance, not current qualification or runtime authority. "
        "The current normative file set is exactly the R5.4 manifest; prior source bytes remain untouched. "
        "Registered semantics, exact executable bindings, authenticated prior authority and every domain predicate are jointly required.\n\n")
    source_data=(CONTEXT/"BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md").read_text(encoding="utf-8-sig")
    data=source_data
    data=section(data,"# 95. Schema Registry", """# 95. Schema Registry — R5.4

`schema_registry/1` remains historical. New R5.4 campaigns pin exactly `schema_registry/2`, defined in §192 and the successor Registry. Each binding maps a registered semantic key to exact executable schema RawRef (bytes, SHA256, length, media type, exact artifact profile). Schema ID alone is insufficient; schema revision identity is RawDigest(exact executable bytes), distinct from ObjectDigest(schema_registry,2,body). A schema reference's `kind=schema` is a reference representation, not a registered ObjectDigest wire kind.

The campaign's accepted/pinned schema set never follows latest installed files. Missing mandatory entry or mutated bytes is fail-closed before first acceptance. This candidate binds a finite bootstrap/NF02 subset: all other registered keys remain unbound and acceptance is forbidden. No unspecified future subsystem schema is fabricated. Exact root schema bytes are externally pinned before validating SchemaRegistry; registry/profile may not self-authorize. §192 governs construction/install/readback and no in-place migration.
""")
    data=section(data,"# 96. Versioning", """# 96. Versioning — R5.4

Optional additive schema field can be compatible only under its explicit contract. Changing required fields, predicates or meaning is breaking; the NF02 new kinds are assignment_package_binding/1, lane_result_admission_evidence/2, bdb_audit_lane_result/2 and schema_registry/2. AssignmentManifest/1 body and digest semantics remain unchanged. NF02 /1 result/evidence extensions are not legalized or aliased.

Canonical serialization/RawDigest/ObjectDigest remain ADR-006. Governing policy/spec/profile refs resolve from exact prior input cut (or authorized installation pins at EMPTY_HISTORY). Same-commit semantic self-upgrade remains forbidden. Existing runs/campaigns cannot auto-upgrade; for this revision, all new semantics require a new campaign/namespace with exact R5.4 installation pins. Old campaigns are historical/read-only with explicit limited assurance. No retro binding or new schema-install successor trigger. See §192 migration.
""")
    # Current schema/vector identities; preserve historical hash/governance sections.
    data=data.replace("BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json","BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json")
    data=data.replace('"kind": "invariant",','"kind": "invariant_revision",').replace('"invariant_<uuidv4-lowercase>"','"invariant_revision_<uuidv4-lowercase>"')
    # Preserve author-only authorization requirements; generalize record version without asserting approval.
    data=data.replace("ordered setowi **8 normative Markdown docs + ArtifactContractRegistry + Golden Vectors**", "ordered setowi **8 normative Markdown docs + ArtifactContractRegistry + Golden Vectors** z exact successor manifestu; machine activation artifacts są przypięte oddzielnym machine-set digestem tego samego manifestu")
    data=data.replace("author_verdict = R5_3_AUTHOR_FINAL_REAUDIT_PASS", "author_verdict = R5_4_N1_N4_AUTHOR_SELF_AUDIT_PASS  # successor governance record/2 only")
    data += "\n# 192. R5.4 NF02 normative successor contract\n\n"+delta+"\n"+migration
    data += """\n### 192.1. Executable schema and external profile representation

Canonical domain bodies exclude own kind/version/digest/acceptance provenance, carried in the external immutable-object envelope. TypedRef is closed: kind, optional logical_id, revision_digest, digest_profile=BDB-OBJECT-DIGEST-1, schema_revision_ref={kind:schema,revision_digest:RawDigest(executable schema bytes)}. Target kind/version and schema digest must resolve consistently to the Registry key; `schema` is not an ObjectDigest domain. ExternalProfileRef is {profile_id,revision_digest:RawDigest(exact profile JSON bytes)}. RawRef is {raw_digest,byte_length,media_type,artifact_contract_ref:ExternalProfileRef}. Reference-class annotations are Registry metadata, not fields admitted into closed identity-bearing refs.

HistoryCut keeps inherited value encoding: accepted cut fields campaign_id, accepted_head_seq, accepted_head_hash, governing_policy_ref, governing_spec_refs; initialization tagged EMPTY_HISTORY_CUT additionally identifies exact history_namespace_ref and has no accepted head/hash. Governing spec set at bootstrap remains the single exact initial_transition_profile_ref. No synthetic H0. Registered wire version/schema ref identifies domain schemas independently of body metadata.

Finite NF02 result payload is findings[], outputs{}, notes:string|null. Each finding has external finding_id, title, statement, evidence_member_paths[], reported_severity (BLOCKER/HIGH/MEDIUM/LOW/INFO/UNKNOWN). These are external claims, not M/R/I, finding adjudication or evidence qualification. Duplicate finding IDs reject. Order and Unicode text are preserved; no silent normalization. outputs may have only report/evidence/logs, each {member_paths:[]}; member paths are UTF-8 sorted unique and resolve inside retained result ZIP. No embedded material TypedRefs. notes is required even if null; findings/outputs remain required when empty. Changing this finite profile later requires an explicit breaking profile/schema revision.

External transport manifests are closed exact schemas in the schema catalog. Package manifest carries prior assignment and exact derived attempt/source/stage/lane/executor/delivery/input cut and declared slot refs, actual member records, transport profile and tagged semantic checksum. It never includes final package RawDigest, future binding or STARTED ref. Result manifest additionally names exact prior package binding and result slot, checked package semantic assertion and finite payload. Expected identities come from accepted binding/assignment and governing pins, never the manifest. Media types use the fixed pinned extension mapping, not host sniffing. ZIP members, quotas, metadata, raw digest and checksum restrictions are defined in frozen transport profiles and §192.

Executable schema validation is only L3: pure schema/hash self-audit does not prove history membership, actor authorization, durable storage, FSM/disclosure, evidence truth, LaneCompletion or StageCompletion. These require cross-object/runtime checks in N5-N11. Unknown/unbound mandatory schema, extra ref, secret token or alias rejects without canonical state mutation. Const schemas for the initial policy/spec/trust/ArtifactContractRegistry admit only those exact installation revisions, not arbitrary future /1 bodies. Broader schema binding must not change frozen semantics and still obey new-campaign boundary.

Binding/evidence/result acceptance uses the existing ArtifactAccepted envelope with exact artifact_ref. The pinned transition profile defines its NF02 effects: B/1 leaves Attempt CREATED; E/2 permits STARTED to RESULT_RECEIVED only after all admission predicates; R/2 permits RESULT_RECEIVED to RESULT_ACCEPTED only after its predicates. No new event alias or state is added. AttemptStarted remains the existing separate accepted transition. Initial spec_revision/1 executable schema explicitly marks protocol_profile_ref as PINNED_PROFILE_REF; deferred predecessor rows gain their exact body ref inventory from these frozen schemas, not a process-local lookup.

### 192.2. Successor governance and exact bytes

The normative set remains eight Markdown sources plus successor Registry and Golden Vectors. Unchanged Methodology/Migration/ADR bytes are carried exactly and identified as inherited normative inputs in the successor manifest; their historical status/header refers only to predecessor provenance. The machine set includes schema bytes, catalog, canonical initial objects, external profiles, bootstrap bundle and vector fixtures. Candidate identity is {normative_set_digest,machine_set_digest}, bound by exact external manifest RawDigest; each set uses the established sorted [{file,bytes,sha256}] canonical JSON SHA256 preimage. Manifest, self-audit/readback, source pins and governance evidence are external to both sets to avoid self-reference.

Design approval does not establish hash-bound candidate qualification or waive independent review. AuthorBaselineQualificationRecord/2 may derive AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE=YES only after zero-mismatch readback, exact final self-audit and explicit authorized owner acceptance of author-only implementation risk for the exact manifest and both sets. It retains independent_assurance=false and foundation_spec_baseline_frozen=false. The /1 historical record/token remains unchanged. Independent freeze uses the existing foundation_baseline_freeze_decision/1 only after a genuine independent READY review of exact manifest/machine closure. Prepared pending templates are neither valid qualification records nor canonical facts. No independent PASS or risk waiver is inferred from owner approval of these three design choices.

The external AuthorBaselineQualificationRecord/2 has required qualification ID, created_at, governance_actor_ref, owner_assurance_decision=IMPLEMENTATION_MAY_PROCEED_UNDER_AUTHOR_ONLY_ASSURANCE, candidate_manifest_schema=BDB_AUDIT_V2_R5_4_PACKAGE_MANIFEST/1, candidate_manifest_storage_id, candidate_manifest_raw_digest, normative_candidate_set_digest, machine_candidate_set_digest, final_reaudit_register_storage_id/raw_digest, readback_storage_provider, readback_verified_file_count (all normative plus machine entries), readback_verified_normative_count, readback_verified_machine_count, readback_mismatch_count=0 and readback_entries[] (group, file, stable_storage_id, expected_raw_digest, observed_raw_digest, result=PASS). Counts/inventories must equal the exact manifest; author_verdict=R5_4_AUTHOR_NORMATIVE_FINAL_SELF_AUDIT_PASS is limited to the exact normative/machine candidate. independent_assurance=false and foundation_spec_baseline_frozen=false are required. effective_derived_state.AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE=YES can be populated only after these checks and the explicit owner risk decision. This is an external successor governance format, not a registered canonical kind or a capability. Author assurance never asserts runtime PASS. The independent freeze record retains /1 fields; its exact candidate_manifest_raw_digest transitively binds both sets, and the independent review must cover this full manifest closure. A pending template with null actor/risk/review/verdict/state is not a valid decision.

Prepared installation bundle is CANDIDATE_PREPARED_NOT_INSTALLED. Runtime activation requires external hash-bound governance qualification, independently authenticated installation actor/trust root, exact schema-root verification and legal genesis. Installation must not write/upgrade old campaigns. The fixed candidate namespace is reserved, not an operating campaign; any other namespace requires its own exact externally authorized installation revision before first genesis. Current remediation runtime is not authority and must change later; N1-N4 do not implement or qualify it.
"""
    markdown(CANDIDATE/"BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md",header+data)
    architecture=(CONTEXT/"BDB_AUDIT_V2_ARCHITECTURE_SPEC.md").read_text(encoding="utf-8-sig")
    architecture += "\n# 61. R5.4 NF02 exact package and schema authority\n\n"+delta+"\n"+migration
    architecture += "\nThe prepared exact schemas/SchemaRegistry/installation objects are candidate assets, not a loaded mutable authority. All old campaign schemas stay pinned. The E1/manual/shared packaging and inbox adapters must later implement this pipeline; code generation dictionaries/extensions/overlays cannot establish legality. Result evidence stores enduring facts, not HMAC tokens. Exact payload provenance does not automatically qualify findings. Full reference/union-DAG/atomicity/isolation and later application lifecycle gates are preserved.\n"
    markdown(CANDIDATE/"BDB_AUDIT_V2_ARCHITECTURE_SPEC_R5_4.md",header+architecture)
    test=(CONTEXT/"BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN.md").read_text(encoding="utf-8-sig")
    test=test.replace("BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json","BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json")
    test += "\n# R5.4 NF02 successor qualification section\n\n"+vec+"\n"+plan
    test += "\nN1-N4 self-audit checks exact candidate schemas, digests, references, inventory, provenance, grammar, known-answer bytes, readback and governance status only. No production acceptance, durability, crash, race, disclosure or application gate obtains PASS from design vectors. All 117 inherited vectors remain exact predecessor expectations; current-label vectors are scoped to predecessor history. Every new mandatory adversarial variant must later execute in production/direct Store/packaged runtime with snapshots and zero mutation/disclosure conditions. Unknown runner IDs or skipped mandatory tests are not PASS.\n"
    markdown(CANDIDATE/"BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN_R5_4.md",header+test)
    roadmap=(CONTEXT/"BDB_AUDIT_V2_IMPLEMENTATION_ROADMAP.md").read_text(encoding="utf-8-sig")
    roadmap += "\n# R5.4 NF02 normative activation and implementation boundary\n\n"+plan
    roadmap += "\nCurrent task completes candidate preparation N1-N4 only. N5-N11 are deferred without implied execution authority. Candidate ready for qualification is not hash-bound author-qualified baseline, independent freeze, installed schema activation, NF02 closure or application/release qualification. No evidence is reused solely because HEAD is unchanged.\n"
    markdown(CANDIDATE/"BDB_AUDIT_V2_IMPLEMENTATION_ROADMAP_R5_4.md",header+roadmap)
    for name in ["BDB_Audit_vNext_Szczegolowy_Plan_Rozwoju.md", "BDB_AUDIT_V1_TO_V2_MIGRATION_AND_COMPATIBILITY.md", "ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md"]:
        write(CANDIDATE/name,(CONTEXT/name).read_bytes())
    readme=header+"""## Current corpus and authority

This directory is the complete R5.4 successor normative/machine candidate. Exact files and identities are in ../evidence/BDB_AUDIT_V2_R5_4_MANIFEST_SHA256.json. Parent manifest/readback/qualification are external to the candidate preimage. Data and Architecture successor sections define approved NF02 semantics; Registry/Golden pin machine contracts. Runtime may not infer authority from this directory or from latest installed bytes.

The eight Markdown normative inputs are Methodology (exact inherited), Migration (exact inherited, NF02 boundary explicitly in successor Data), ADR-006 (exact inherited), Data_R5_4, Architecture_R5_4, TestPlan_R5_4, Roadmap_R5_4 and this README. Historical labels/old current-file references in inherited chapters are predecessor context; current R5.4 artifacts are the explicitly named successor files and manifest. No legacy observed behavior or runtime extension is a normative oracle.

Four registered additions are assignment_package_binding/1, lane_result_admission_evidence/2, bdb_audit_lane_result/2 and schema_registry/2. Existing role/ref domains and bootstrap order-only scope are preserved; NF02_PROVENANCE adds L1-L6. All other mandatory gates remain required. No PROVENANCE/PROPOSAL role, DeliveryReceipt, canonical capability, in-place schema upgrade or retrospective /1 alias. The residual_risk source overlay is not legalized in this scope.

Schemas are frozen exact JSON files with LF transport, RawDigest and byte length, $id, draft2020-12 and offline dependency closure in SCHEMA_ARTIFACT_CATALOG_R5_4.json. Only catalog-bound wire keys may be accepted after trusted activation. Future unbound registered families remain fail-closed. schema_registry/2 identifies its binding body by registered ObjectDigest; its own schema bytes are externally pinned before validation. Installation/bootstrap object/1 keeps all eight pins and qualified legacy first-history protocol. Prepared bundle does not create a campaign or change runtime.

Source, predecessor and design approval evidence are outside this candidate. Author-only qualification requires a new explicit risk decision for exact bytes; independent freeze requires genuine independent review. Neither is created by changing this README flag. AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE=PENDING_EXTERNAL_QUALIFICATION_RECORD; FOUNDATION_SPEC_BASELINE_FROZEN=false; INDEPENDENT_ASSURANCE=false. N5-N11 runtime execution status=NOT_RUN. NF02 remains unclosed.

## Review entry points

- BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md §§95-96,192.
- BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json, exact additions and profiles.
- BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json; inherited plus every new NF02 ID/variant.
- schemas/, profiles/, objects/, fixtures/; catalog and INSTALLATION_PIN_BUNDLE_R5_4.json.
- BDB_AUDIT_V2_ARCHITECTURE_SPEC_R5_4.md §61, TestPlan and Roadmap successor gates.
- ../tools/verify_candidate.py (artifact self-audit only), ../evidence/ manifest/readback/self-audit/qualification preparation.
"""
    markdown(CANDIDATE/"README_BDB_AUDIT_V2_DOCUMENTATION_R5_4.md",readme)
    execution=(CONTEXT/"BDB_AUDIT_V2_IMPLEMENTATION_EXECUTION_PLAN_R5_3_CORR2.md").read_text(encoding="utf-8-sig")
    execution += "\n# R5.4 N1-N11 successor task packet (subordinate scheduling)\n\n"+plan
    markdown(ROOT/"BDB_AUDIT_V2_IMPLEMENTATION_EXECUTION_PLAN_R5_4.md",header+execution)


def finalize_manifest(source_pin, gv, catalog, rows):
    normative=["BDB_Audit_vNext_Szczegolowy_Plan_Rozwoju.md", "BDB_AUDIT_V1_TO_V2_MIGRATION_AND_COMPATIBILITY.md",
        "ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md", "BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md",
        "BDB_AUDIT_V2_ARCHITECTURE_SPEC_R5_4.md", "BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN_R5_4.md",
        "BDB_AUDIT_V2_IMPLEMENTATION_ROADMAP_R5_4.md", "README_BDB_AUDIT_V2_DOCUMENTATION_R5_4.md",
        "BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json", "BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json"]
    def entry(p,role):
        raw=p.read_bytes()
        return {"file":p.relative_to(CANDIDATE).as_posix(),"bytes":len(raw),"sha256":digest(raw),"role":role}
    normative_entries=[entry(CANDIDATE/n,"normative_candidate") for n in normative]
    bundle_path = CANDIDATE / "INSTALLATION_PIN_BUNDLE_R5_4.json"
    bundle = json.loads(bundle_path.read_bytes())
    bundle["governing_normative_candidate_set_sha256"] = digest(cjson(sorted(
        [{k: e[k] for k in ["file", "bytes", "sha256"]} for e in normative_entries], key=lambda e: e["file"])))
    bundle["approved_design_proposal_raw_digest"] = source_pin["proposal_raw_digest"]
    json_file(bundle_path, bundle)
    machine_entries=[entry(p,"machine_activation_or_vector_fixture") for p in sorted(CANDIDATE.rglob("*")) if p.is_file() and p.relative_to(CANDIDATE).as_posix() not in normative]
    def set_digest(entries):
        preimage=sorted([{k:e[k] for k in ["file","bytes","sha256"]} for e in entries],key=lambda e:e["file"])
        return digest(cjson(preimage))
    manifest={"schema":"BDB_AUDIT_V2_R5_4_PACKAGE_MANIFEST/1","date":DATE,
        "candidate_status":"R5_4_NORMATIVE_CANDIDATE_PENDING_QUALIFICATION","author_qualified_implementation_baseline":"PENDING_EXTERNAL_QUALIFICATION_RECORD",
        "foundation_spec_baseline_frozen":False,"independent_assurance":False,"manifest_self_hash":"EXTERNAL",
        "normative_candidate_files":sorted(normative_entries,key=lambda e:e["file"]),"machine_candidate_files":sorted(machine_entries,key=lambda e:e["file"]),
        "normative_candidate_set_digest_preimage":"SHA256(BDB-CJSON-1(sorted by file of [{file,bytes,sha256}]))",
        "normative_candidate_set_sha256":set_digest(normative_entries),"machine_candidate_set_sha256":set_digest(machine_entries),
        "predecessor_normative_candidate_set_digest":PREDECESSOR_SET,"predecessor_r5_3_candidate_set_digest":LEGACY_SET,
        "predecessor_manifest_raw_digest":source_pin["predecessor_context_raw_pins"]["BDB_AUDIT_V2_R5_3_1_MANIFEST_SHA256.json"],
        "predecessor_author_qualification_raw_digest":source_pin["predecessor_context_raw_pins"]["BDB_AUDIT_V2_AUTHOR_BASELINE_QUALIFICATION_R5_3_1.json"],
        "approved_proposal_raw_digest":source_pin["proposal_raw_digest"],"scope":"N1-N4 candidate preparation only; no installed runtime authority or N5-N11 implementation"}
    json_file(EVIDENCE/"BDB_AUDIT_V2_R5_4_MANIFEST_SHA256.json",manifest)
    json_file(EVIDENCE/"R5_4_REGISTRY_DELTA.json",{"base_registry_raw_digest":source_pin["predecessor_context_raw_pins"]["BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY.json"],
        "additions":rows,"changed_existing_contract_rows":[],"new_profiles":["NF02_PROVENANCE","NF02_R5_4_ACTIVATION_V1","NF02_COMMAND_PROFILE_V1"],
        "unchanged_role_and_reference_domains":True,"old_registry_raw_bytes_preserved":True,
        "completion_version_consumption":"explicit new profile rule; original complete completion rows retained"})
    json_file(EVIDENCE/"R5_4_GOLDEN_VECTOR_INVENTORY.json",{"inherited_count":gv["inherited_vector_count"],"nf02_count":gv["nf02_vector_count"],"total":len(gv["vectors"]),
        "vectors":[{"id":v["id"],"domain":v["domain"],"origin":"R5.3.1_EXACT_INHERITED" if i<gv["inherited_vector_count"] else "R5.4_NF02", "expected":v["expected"],"runtime_status":"NOT_RUN"} for i,v in enumerate(gv["vectors"])],"runtime_qualification":"NOT_CLAIMED"})
    return manifest


def main():
    if (EVIDENCE/"AUTHOR_BASELINE_QUALIFICATION_R5_4.json").exists() or (EVIDENCE/"FOUNDATION_BASELINE_FREEZE_DECISION_R5_4.json").exists():
        raise RuntimeError("QUALIFIED_CANDIDATE_REGENERATION_FORBIDDEN")
    existing=EVIDENCE/"R5_4_SOURCE_PREDECESSOR_PINS.json"
    source_pin=json.loads(existing.read_bytes()) if existing.exists() else capture_inputs()
    json_file(existing,source_pin)
    base,reg,rows=registry_candidate()
    json_file(CANDIDATE/"BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json",reg)
    defs=definitions(reg)
    profiles=materialize_profiles(defs)
    schemas=inherited_schemas(reg,defs)
    schemas.update(nf02_schemas(reg,defs));schemas.update(transport_schemas(defs));schemas.update(context_schemas(reg,defs))
    initial=pinned_initial_objects(reg,profiles,defs,schemas)
    catalog,roots,bundle=freeze_schemas_and_roots(reg,profiles,defs,schemas,initial)
    bodies,known=fixtures(reg,profiles,schemas,roots)
    gv=vectors(bodies,known,rows)
    materialize_corpus(reg,rows,catalog,roots,gv)
    manifest=finalize_manifest(source_pin,gv,catalog,rows)
    print(json.dumps({"status":"CANDIDATE_BYTES_MATERIALIZED_NOT_QUALIFIED","normative_files":len(manifest["normative_candidate_files"]),
        "machine_files":len(manifest["machine_candidate_files"]),"schema_count":len(catalog),"wire_schema_count":sum(c["scope"]=="CANONICAL_WIRE" for c in catalog),
        "nf02_vectors":gv["nf02_vector_count"],"candidate_set_digest":manifest["normative_candidate_set_sha256"],"machine_set_digest":manifest["machine_candidate_set_sha256"]},indent=2))


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
