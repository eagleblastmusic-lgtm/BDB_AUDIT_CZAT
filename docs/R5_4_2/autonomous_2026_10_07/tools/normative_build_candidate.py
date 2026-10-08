"""Materialize the ten-source normative build draft for exact review.

This preserves predecessor text/bytes and explicitly scopes successor deltas.
It cannot freeze contracts, close parity or issue any qualification record.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from execution import BASE, OUT, ROOT, canonical, digest, preserve, read, write


DATA = "BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md"
GOLDEN = "BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json"
REGISTRY = "BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json"
INHERITED = {"ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md",
             "BDB_AUDIT_V1_TO_V2_MIGRATION_AND_COMPATIBILITY.md",
             "BDB_Audit_vNext_Szczegolowy_Plan_Rozwoju.md"}


def successor_name(name):
    return name.replace("_R5_4.", "_R5_4_2.")


def exact_report_file(report, relative_to):
    path = relative_to / report["file"]
    if not path.resolve().is_relative_to(ROOT.resolve()) or path.is_symlink():
        raise ValueError("NORMATIVE_BUILD_SOURCE_ESCAPE")
    if digest(path) != report["raw_digest"]:
        raise ValueError("NORMATIVE_BUILD_SOURCE_RAW_DRIFT")
    return path


def active_reference_contracts(references, mapping, catalog):
    result = copy.deepcopy(references)
    for reference in result:
        allowed = reference.get("allowed_keys", [])
        if any(key not in mapping for key in allowed):
            raise ValueError("NORMATIVE_REFERENCE_TARGET_NOT_IN_ACTIVE_CLOSURE")
        reference["allowed_keys"] = sorted(mapping[key] for key in allowed)
        profiles = reference.get("profile_contracts", [])
        if any(name not in catalog for name in profiles):
            raise ValueError("NORMATIVE_REFERENCE_PROFILE_NOT_DECLARED")
        if "profile_contracts" in reference:
            reference["profile_contracts"] = sorted(catalog[name].get("wire_profile_id", name) for name in profiles)
    return result


def data_appendix(mapping, schemas, own, catalog):
    by_key = {entry["$id"].removeprefix("BDB_SCHEMA_REGISTRY::"): entry
              for entry in schemas["entries"] if entry["file"].startswith("schemas/")}
    if set(by_key) != set(mapping.values()) or len(mapping) != len(set(mapping.values())):
        raise ValueError("NORMATIVE_SCHEMA_CLOSURE_MISMATCH")
    if {node["key"] for node in own["nodes"]} != set(mapping):
        raise ValueError("NORMATIVE_SOURCE_CLOSURE_MISMATCH")
    result = ["\n# R5.4.2 explicit versioned successor contract draft\n",
              "This appendix is a build-time normative candidate for review, not frozen or installed authority. "
              "The preceding complete R5.4.1 text is retained predecessor provenance. Its exact source semantics "
              "are carried into the active successor keys below except for the explicitly approved versioned "
              "owner decisions and representation amendments included here. Historical status, version labels, "
              "design counts and earlier conflict reports in quoted source material are historical provenance. "
              "They do not describe current qualification. Unresolved material source/body/profile/predicate "
              "conflicts prohibit freeze; no convenient precedence or schema PASS resolves them.\n",
              "Changed old kind/version keys are historical only. There is no runtime alias, latest-installed "
              "fallback or in-place campaign upgrade. Existing campaigns retain exact original contracts. "
              "Only a separately qualified installation and legally initialized new campaign may consume these "
              "successor contracts. The eight installation material pins and independent root authorization "
              "remain mandatory. External Q1/audit/readback/owner decisions and activation/output receipts "
              "remain outside the candidate-set preimages.\n",
              "The complete separately approved residual-risk contract's specific Registry row selects "
              "EPISTEMIC L3–L6; condensed generic proposal labels do not replace this exact row. "
              "All stronger consumer/finalization predicates and required L7 remain mandatory.\n",
              "## Exact version impact and machine body contract\n",
              "The following finite one-to-one map selects active wire versions. Each executable body schema "
              "is identified by exact RawDigest, byte length, dialect and full offline dependency closure. "
              "JSON Schema covers structural constraints only. Accepted membership, prior cut, source/campaign "
              "equality, producer authority, purpose dispatch, knowledge/isolation, FSM, independent evidence, "
              "revision selection, no omission, durability and completion require their complete semantic "
              "predicates; no generated default or incomplete fixture establishes them.\n"]
    nodes = {node["key"]: node for node in own["nodes"]}
    for source, target in sorted(mapping.items()):
        entry = by_key[target]
        contract = {"predecessor_key": source, "active_key": target,
                    "schema_id": entry["$id"], "schema_file": entry["file"],
                    "schema_raw_digest": entry["raw_digest"], "byte_length": entry["byte_length"],
                    "dialect": entry["dialect"], "dependency_closure": entry["dependency_closure"],
                    "material_references": active_reference_contracts(nodes[source]["resolved_own_material_refs"], mapping, catalog)}
        result.extend(["\n### Active contract " + target + "\n", "```json\n" + canonical(contract).decode("utf-8") + "\n```\n"])
    result.append("\n## Complete finite external-profile contract catalog\n")
    schema_by_id = {entry["$id"]: entry for entry in schemas["entries"]}
    for name, contract in sorted(catalog.items()):
        wire = contract.get("wire_profile_id", name)
        entry = schema_by_id["BDB_EXTERNAL_PROFILE_SCHEMA::" + wire]
        active = copy.deepcopy(contract)
        active["analysis_key_provenance_only"] = name
        active["wire_profile_id"] = wire
        active["grammar"] = read(ROOT / schemas["directory"] / entry["file"])
        active["executable_profile_schema"] = entry
        active["dependencies"] = sorted(catalog[dependency].get("wire_profile_id", dependency)
                                        for dependency in contract["dependencies"])
        if "payload_grammar" in contract:
            payload = schema_by_id["BDB_RAW_PAYLOAD_SCHEMA::" + wire]
            active["payload_grammar"] = read(ROOT / schemas["directory"] / payload["file"])
            active["executable_payload_schema"] = payload
        result.extend(["\n### Profile " + wire + "\n",
                       "```json\n" + canonical(active).decode("utf-8") + "\n```\n"])
    return "\n".join(result)


def construct():
    manifest = read(BASE / "R5_4_1_CANDIDATE_MANIFEST.json")
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    schemas = read(OUT / "BUILD_TIME_CANDIDATE_READBACK.json")
    from build_time_candidates import verify_readback
    verify_readback(ROOT / schemas["directory"], schemas["entries"])
    registry_report = read(OUT / "REGISTRY_BUILD_CANDIDATE_READBACK.json")
    golden_report = read(OUT / "GOLDEN_BUILD_CANDIDATE_READBACK.json")
    registry_path = exact_report_file(registry_report, OUT)
    golden_path = exact_report_file(golden_report, ROOT)
    if registry_report["pending_fields"]:
        raise ValueError("NORMATIVE_REGISTRY_ROW_PENDING")
    approval = read(ROOT / "docs/R5_4_2/OWNER_R5_4_2_SEMANTIC_CLOSURE_APPROVAL.json")
    approved_sources = []
    for entry in approval["approved_artifacts"]:
        path = ROOT / entry["file"]
        if digest(path) != entry["raw_digest"] or path.stat().st_size != entry["bytes"]:
            raise ValueError("NORMATIVE_APPROVED_SOURCE_DRIFT")
        if (path.suffix == ".md" and "CONTRACT" in path.name) or path.name == "R5_4_2_OWNER_DECISION_PACKAGE.md":
            approved_sources.append(path)
    files, inherited = {}, []
    for entry in manifest["normative_candidate_files"]:
        path = BASE / "candidate" / entry["file"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"] or len(raw) != entry["bytes"]:
            raise ValueError("NORMATIVE_PREDECESSOR_SOURCE_DRIFT")
        name = successor_name(entry["file"])
        if entry["file"] in INHERITED:
            files[name] = raw
            inherited.append(name)
        elif entry["file"] == REGISTRY:
            files[name] = registry_path.read_bytes()
        elif entry["file"] == GOLDEN:
            files[name] = golden_path.read_bytes()
        else:
            prefix = ("# R5.4.2 build-time successor — pending complete parity and fresh Q1\n\n"
                      "The complete predecessor text below is preserved as provenance. "
                      "The explicit versioned successor appendix and exact Registry/Golden build inputs "
                      "describe the proposed next contract. This file supplies no installed authority, "
                      "independent freeze, runtime qualification, release approval or NF02 closure.\n\n"
                      "# Preserved R5.4.1 predecessor text\n\n")
            body = prefix + raw.decode("utf-8-sig")
            if entry["file"] == DATA:
                body += data_appendix(mapping, schemas, read(OUT / "OWN_REFERENCE_RESOLUTIONS.json"),
                                      read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json"))
                for source in approved_sources:
                    body += "\n# Complete approved source: " + source.name + "\n\n" + source.read_text(encoding="utf-8-sig")
                for source in [ROOT / "docs/R5_4_2/OWNER_DELEGATED_DECISION_REGISTER.md",
                               OUT / "design/COMMON_BODY_GRAMMARS.md", OUT / "design/PURPOSE_PREDICATE_CONTRACTS.md",
                               OUT / "design/COMMAND_EVENT_CONTRACT.md"]:
                    body += "\n# Explicit successor decision input: " + source.name + "\n\n" + source.read_text(encoding="utf-8-sig")
            else:
                body += ("\n# Explicit R5.4.2 successor integration\n\n"
                         "Active kind/version, body/reference/profile semantics and all explicit owner amendments "
                         "are enumerated in BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4_2.md and the exact "
                         "successor Registry. Historical V1 initialization precedence is preserved only for "
                         "historical campaigns; OD024 requires the scoped BDB_BOOTSTRAP_PRECEDENCE_V2 union-DAG "
                         "for new qualified successor initialization. All changed versions require exact "
                         "successor schemas and campaign context; no implicit alias or actor self-authorization. "
                         "Original mandatory reference, source, authority, isolation, knowledge, evidence, "
                         "no-omission, concurrency, crash, compatibility, standalone and completion checks remain "
                         "mandatory. The new structural vectors do not execute canonical acceptance designs. "
                         "Q1, Q2 and N5–N11 remain distinct gates. Do not derive PASS or NF02 closure from "
                         "this build draft or predecessor preparation metadata.\n")
            files[name] = body.encode("utf-8")
    if len(files) != 10 or sum(name.endswith(".md") for name in files) != 8:
        raise ValueError("NORMATIVE_TEN_SOURCE_MEMBERSHIP_CONFLICT")
    return files, inherited


def main():
    preserve()
    paths = [Path(__file__), OUT / "tools/execution.py", OUT / "tools/build_time_candidates.py",
             OUT / "BUILD_TIME_CANDIDATE_READBACK.json", OUT / "REGISTRY_BUILD_CANDIDATE_READBACK.json",
             OUT / "GOLDEN_BUILD_CANDIDATE_READBACK.json", OUT / "design/VERSION_IMPACT_PLAN.json",
             OUT / "OWN_REFERENCE_RESOLUTIONS.json", OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json",
             ROOT / "docs/R5_4_2/OWNER_R5_4_2_SEMANTIC_CLOSURE_APPROVAL.json",
             ROOT / "docs/R5_4_2/OWNER_DELEGATED_DECISION_REGISTER.md",
             OUT / "design/COMMON_BODY_GRAMMARS.md", OUT / "design/PURPOSE_PREDICATE_CONTRACTS.md",
             OUT / "design/COMMAND_EVENT_CONTRACT.md", BASE / "R5_4_1_CANDIDATE_MANIFEST.json"]
    paths.extend(BASE / "candidate" / entry["file"] for entry in read(paths[-1])["normative_candidate_files"])
    paths.extend(ROOT / entry["file"] for entry in read(paths[9])["approved_artifacts"])
    paths.extend([exact_report_file(read(paths[4]), OUT), exact_report_file(read(paths[5]), ROOT)])
    before = {path.relative_to(ROOT).as_posix(): digest(path) for path in paths}
    files, inherited = construct()
    entries = [{"file": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
               for name, raw in sorted(files.items())]
    set_digest = hashlib.sha256(canonical(entries)).hexdigest()
    directory = OUT / "normative_build_candidate" / set_digest
    for name, raw in files.items():
        path = directory / name
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("EXISTING_NORMATIVE_BUILD_DRIFT")
        directory.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(raw)
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    if actual != set(files):
        raise ValueError("NORMATIVE_BUILD_MEMBERSHIP_DRIFT")
    for entry in entries:
        path = directory / entry["file"]
        if digest(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ValueError("NORMATIVE_BUILD_READBACK_DRIFT")
    after = {path.relative_to(ROOT).as_posix(): digest(path) for path in paths}
    if before != after:
        raise ValueError("NORMATIVE_BUILD_INPUT_DRIFT")
    from build_time_candidates import verify_readback
    schema_report = read(OUT / "BUILD_TIME_CANDIDATE_READBACK.json")
    verify_readback(ROOT / schema_report["directory"], schema_report["entries"])
    preserve()
    write("NORMATIVE_BUILD_CANDIDATE_READBACK.json", {
        "status": "TEN_SOURCE_NORMATIVE_BUILD_DRAFT_READ_BACK_NOT_FROZEN_NOT_QUALIFIED",
        "directory": directory.relative_to(ROOT).as_posix(), "normative_build_set_digest": set_digest,
        "entries": entries, "inherited_exact_files": inherited, "sources": before, "input_drift": [],
        "mismatch_count": 0, "semantic_parity_pending_nodes": 131, "full_successor_candidate_materialized": False,
        "qualification": False, "frozen": False, "Q1": "NOT_STARTED", "Q2": "NOT_STARTED", "NF02": "OPEN"})
    print(json.dumps({"normative_build_readback": "PASS", "files": len(entries), "inherited_exact_files": len(inherited),
                      "semantic_parity_pending": 131, "qualification": False}))


if __name__ == "__main__":
    main()
