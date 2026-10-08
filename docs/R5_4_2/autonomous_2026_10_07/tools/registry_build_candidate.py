"""Prepare the complete successor Registry build input; never freeze or activate."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from bootstrap_registry_integration import integration
from execution import BASE, OUT, ROOT, canonical, digest, preserve, read, write
from semantic_inventory import approved_specific_row


def construct():
    old = read(BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json")
    result = integration(old, read(OUT / "design/BOOTSTRAP_PRECEDENCE_SUCCESSOR.json"))
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    nodes = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")["nodes"]
    reviewed = {node["source_key"]: node for node in read(OUT / "design/SEMANTIC_OBLIGATION_QUEUE.json")["nodes"]}
    profiles = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    wire_profiles = {name: profile.get("wire_profile_id", name) for name, profile in profiles.items()}
    rows = []
    pending = []
    for node in nodes:
        key = node["key"]
        target_key = mapping[key]
        kind, version = target_key.split("/")
        specific = approved_specific_row(key)
        if specific != node.get("approved_specific_registry_row"):
            raise ValueError("APPROVED_SPECIFIC_ROW_PARITY_DRIFT: " + key)
        source = (specific or {}).get("row") or node.get("qualified_registry_row") or node["historical_proposal"]
        row = {field: copy.deepcopy(source[field]) for field in (
            "authoritative_for", "lifecycle", "identity_semantics", "ordering_rules") if field in source}
        role = reviewed[key]["canonical_role"]
        producer = reviewed[key]["producer_authority"]
        producer_conditions = None
        conditional_producer = "TRUSTED_COORDINATOR_ACCEPTANCE after independently verified producer/context/raw derivation; caller flags/tokens are not canonical evidence"
        if producer == conditional_producer:
            producer_conditions = producer
            producer = "TRUSTED_COORDINATOR_ACCEPTANCE"
        profile = reviewed[key]["validation_profile"]
        layers = source.get("required_validation_layers", source.get("validation_layers"))
        if not layers:
            raise ValueError("UNDECLARED_VALIDATION_LAYERS: " + key)
        if profile.startswith("FULL_PATH_SEMANTIC_V1"):
            profile = "FULL_PATH_SEMANTIC_V1"
            if layers != ["L1", "L2", "L3", "L4", "L5", "L6", "L7"]:
                # Conflicting placeholder composition is a materialization
                # obligation, never permission to add or remove a layer.
                pending.append({"key": target_key, "field": "validation_profile",
                                "declared_layers": layers, "problem": "FULL_PATH_LABEL_HAS_DIFFERENT_EXACT_LAYER_COMPOSITION"})
        if profile not in result["validation_layer_profiles"]:
            result["validation_layer_profiles"][profile] = copy.deepcopy(layers)
        elif result["validation_layer_profiles"][profile] != layers:
            pending.append({"key": target_key, "field": "validation_profile",
                            "declared_layers": layers, "profile_layers": result["validation_layer_profiles"][profile],
                            "problem": "PROFILE_LAYER_PARITY_REQUIRES_EXACT_SOURCE_REVIEW"})
        row.update({"kind": kind, "version": version, "schema_ref": "BDB_SCHEMA_REGISTRY::" + target_key,
                    "canonical_role": role, "producer_authority": producer,
                    "validation_profile": profile, "required_validation_layers": layers,
                    "consumer_roles": source.get("consumer_roles", source.get("consumers", [])),
                    "reference_contract_mode": "EXPLICIT_COMPLETE", "material_refs": []})
        if producer_conditions is not None:
            row["producer_authority_requirements"] = producer_conditions
        if "identity_semantics" not in row:
            row["identity_semantics"] = source["identity"]
        if "authoritative_for" not in row:
            pending.append({"key": target_key, "field": "authoritative_for", "source": "Exact approved per-kind prose must supply this description before freezing"})
        for reference in node["resolved_own_material_refs"]:
            item = copy.deepcopy(reference)
            if item["ref_class"] not in result["reference_class_semantics"]:
                raise ValueError("UNDECLARED_REFERENCE_CLASS: " + target_key)
            item["allowed_keys"] = [mapping[key] for key in reference.get("allowed_keys", [])]
            item["profile_contracts"] = [wire_profiles[name] for name in reference.get("profile_contracts", [])]
            item["allowed"] = sorted({target.split("/")[0] for target in item["allowed_keys"]})
            if not item["allowed"]:
                item["allowed"] = [item["representation"]]
            row["material_refs"].append(item)
        rows.append(row)
    result["contracts"] = sorted(rows, key=lambda row: row["schema_ref"].encode("utf-8"))
    keys = [row["schema_ref"] for row in result["contracts"]]
    if len(keys) != len(set(keys)) or set(keys) != {"BDB_SCHEMA_REGISTRY::" + value for value in mapping.values()}:
        raise ValueError("SUCCESSOR_REGISTRY_KEY_PARITY")
    result["registry_id"] = "BDB-AUDIT-V2-ARTIFACT-CONTRACT-REGISTRY-R5-4-2"
    result["registry_version"] = old["registry_version"] + 1
    result["status"] = "R5_4_2_BUILD_TIME_CANDIDATE_NOT_FROZEN_OR_QUALIFIED"
    result["reference_class_semantics"]["PINNED_INSTALLATION_REF"] += (
        " OD027 additionally permits independently authenticated pre-campaign build context only for "
        "BuildManifest.application_source_generation_ref/stage_lane_policy_refs, CampaignGenesis.application_generation_ref "
        "and BUILD_PROVENANCE_RECEIPT_V2 manifest/environment/verification refs. Exact independently verified retained build inputs "
        "and output proof are mandatory; caller content and synthetic pre-genesis acceptance cannot supply this authority.")
    result["predecessor_identity"] = {
        "registry_id": old["registry_id"], "registry_raw_digest": digest(BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json"),
        "candidate_manifest_raw_digest": digest(BASE / "R5_4_1_CANDIDATE_MANIFEST.json"),
        "qualification_record_raw_digest": digest(BASE / "AUTHOR_BASELINE_QUALIFICATION_R5_4_1.json")}
    return result, pending


def main():
    preserve()
    sources = [OUT / "OWN_REFERENCE_RESOLUTIONS.json", OUT / "design/VERSION_IMPACT_PLAN.json",
               OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json", OUT / "design/SEMANTIC_OBLIGATION_QUEUE.json",
               OUT / "design/BOOTSTRAP_PRECEDENCE_SUCCESSOR.json",
               BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json",
               ROOT / "docs/R5_4_2/OWNER_DELEGATED_DECISION_REGISTER.md",
               ROOT / "docs/R5_4_2/OWNER_R5_4_2_SEMANTIC_CLOSURE_APPROVAL.json",
               ROOT / "docs/R5_4_2/R5_4_2_RESIDUAL_RISK_CONTRACT_DECISION_PROPOSAL.md",
               Path(__file__), OUT / "tools/semantic_inventory.py", OUT / "tools/bootstrap_registry_integration.py", OUT / "tools/execution.py"]
    before = {source.relative_to(ROOT).as_posix(): digest(source) for source in sources}
    registry, pending = construct()
    raw = canonical(registry) + b"\n"
    identity = hashlib.sha256(raw).hexdigest()
    name = "registry_build_candidate/" + identity + "/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4_2.json"
    path = OUT / name
    if path.exists() and path.read_bytes() != raw:
        raise ValueError("EXISTING_REGISTRY_BUILD_DRIFT")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(raw)
    if digest(path) != identity or read(path) != registry:
        raise ValueError("REGISTRY_BUILD_READBACK_DRIFT")
    preserve()
    after = {source.relative_to(ROOT).as_posix(): digest(source) for source in sources}
    if before != after:
        raise ValueError("REGISTRY_BUILD_INPUT_DRIFT_DURING_EXECUTION")
    write("REGISTRY_BUILD_CANDIDATE_READBACK.json", {
        "file": name, "raw_digest": identity, "byte_length": len(raw), "parsed_readback": "PASS",
        "registered_keys": len(registry["contracts"]), "pending_fields": pending,
        "sources": [{"file": name, "raw_digest": raw_digest} for name, raw_digest in before.items()],
        "input_drift": [],
        "frozen": False, "qualification": False, "Q1": "NOT_STARTED", "NF02": "OPEN",
        "scope": "Complete finite Registry build input; normative parity, mandatory predicates, installed profile pin parity and qualification remain required before freezing."})
    print(json.dumps({"registry_build_readback": "PASS", "registered_keys": len(registry["contracts"]),
                      "raw_digest": identity, "pending_fields": len(pending), "qualification": False}))


if __name__ == "__main__":
    main()
