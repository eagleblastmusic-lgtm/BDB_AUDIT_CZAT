"""Select actual owner bodies before resolving fields or generating schemas.

The previous section-wide regex catalog is historical navigation only.
Selectors below deliberately name a body rather than infer it from a kind name.
"""

from __future__ import annotations

import re
import json
from collections import deque

from execution import BASE, OUT, ROOT, digest, preserve, read, write

HISTORICAL = ROOT / "docs/R5_4_2/R5_4_2_SEMANTIC_CLOSURE_GRAPH_V2.json"


def approved_specific_row(key):
    if key != "residual_risk/1":
        return None
    name = "docs/R5_4_2/R5_4_2_RESIDUAL_RISK_CONTRACT_DECISION_PROPOSAL.md"
    approval = read(ROOT / "docs/R5_4_2/OWNER_R5_4_2_SEMANTIC_CLOSURE_APPROVAL.json")
    entry = next(item for item in approval["approved_artifacts"] if item["file"] == name)
    path = ROOT / name
    assert digest(path) == entry["raw_digest"] and path.stat().st_size == entry["bytes"], "APPROVED_SPECIFIC_ROW_SOURCE_DRIFT"
    text = path.read_text(encoding="utf-8-sig")
    section = text.split("## G. Recommended residual_risk/1 contract", 1)[1].split("## H. Material ref contract", 1)[0]
    blocks = re.findall(r"```json\s*\n(.*?)\n```", section, re.DOTALL)
    assert len(blocks) == 1, "APPROVED_SPECIFIC_ROW_SELECTION_AMBIGUOUS"
    row = json.loads(blocks[0])
    assert row["kind"] + "/" + row["version"] == key
    return {"row": row, "source_file": name, "source_raw_digest": entry["raw_digest"],
            "approval_raw_digest": digest(ROOT / "docs/R5_4_2/OWNER_R5_4_2_SEMANTIC_CLOSURE_APPROVAL.json")}

# Exact block or named sub-body from the complete qualified normative section.
SELECTORS = {
    "approval_decision": 0, "blind_origin_eligibility_assessment": 2,
    "build_manifest": 0, "campaign_conclusion": 4, "candidate_assurance_case": 1,
    "challenger_assignment": 2, "challenger_result": 3, "checkpoint": 0,
    "compatibility_fixture_assessment": 1, "compatibility_gate_result": 2,
    "contradiction_resolution_decision": 1, "contradiction_revision": 0,
    "corpus_manifest": 0, "corpus_member_admission_assessment": (1, "CORPUS_MEMBER_ADMISSION_ASSESSMENT"),
    "coverage_obligation": 1, "coverage_obligation_key": 0,
    "coverage_obligation_qualification": 2, "dependency_independence_assessment": 1,
    "discovery_record": 1, "environment_record": 0, "evidence_applicability_assessment": 1,
    "evidence_invalidation": 0, "evidence_qualification_assessment": 0,
    "execution_descriptor": 0, "execution_result": 1, "experiment_spec": 0,
    "final_assurance_case": 5, "finding_adjudication_decision": 0,
    "finding_axis_assessment": 0, "finding_claim_revision": 0,
    "history_anchor_receipt": 3, "hypothesis_revision": 0, "invariant_revision": 0,
    "lane_completion": 0, "legacy_observation_mapping_assessment": 0,
    "legacy_observation_semantic_equivalence_assessment": (5, "LegacyObservationSemanticEquivalenceAssessment"),
    "materiality_assessment": 1, "model_fidelity_assessment": 1, "negative_evidence_record": 0,
    "obligation_applicability_decision": 5, "run_manifest": 0,
    "release_qualification": 6, "root_cause_revision": 0,
    "scope_state_record": (3, "ScopeStateRecord"), "snapshot_export_record": 0,
    "sound_claim": 0, "source_drift_impact_assessment": 1, "source_drift_record": 0,
    "stage_completion": 0, "stop_evaluation": 1, "stop_input": 0,
    "successor_campaign_genesis": (10, "SuccessorCampaignGenesis"),
    "surface_key": 4, "surface_record": 5, "transition_authorization_proposal": 0,
}


def fields_from_block(text: str) -> list[dict]:
    result = []
    for raw in text.splitlines():
        line = raw.strip().rstrip(",")
        if not line or line.startswith(("SurfaceKey =", "SurfaceKeyBody:", "}")):
            continue
        line = line.split("#", 1)[0].strip()
        match = re.match(r"([a-z][a-z0-9_/]*)(\[\])?(.*)$", line)
        assert match, "Unparsed normative body line: " + line
        name, array, tail = match.groups()
        if "/" in name:
            # Explicit new spelling is a delegated versioning decision, not an alias.
            name = name.replace("/", "_")
        result.append({"field": name, "array": bool(array), "optional": "optional" in tail,
                       "source_declaration": raw.strip(), "inline_enum": tail.split("=", 1)[1].strip().split(" | ") if "=" in tail else None})
    assert result and len({f["field"] for f in result}) == len(result)
    return result


def select(node, graph):
    key, kind = node["key"], node["kind"]
    schema_path = BASE / "candidate/schemas" / (key.replace("/", "__") + ".schema.json")
    if kind == "trust_profile":
        # OD-040: the frozen /1 declaration record cannot express Data 9.1.
        # Select the exact owning subsection, never its neighboring campaign.
        source = node["normative_semantic_source"]
        section = source["complete_section_text"].split("## 9.1. TrustProfile contract", 1)[1].split("## 9.2.", 1)[0]
        block = re.findall(r"```text\n(.*?)```", section, re.S)[0]
        fields = fields_from_block(block)
        assert [f["field"] for f in fields] == ["trust_profile_id", "trust_profile_revision", "coordinator_authority_ref",
            "vault_protection_class", "executor_write_boundary", "history_anchor_mode", "external_anchor_profile_ref",
            "guarantees", "explicit_non_guarantees", "recovery_pin_policy_ref"]
        return {"selector": "EXACT_NORMATIVE_BODY", "section": source["section"], "subsection": "9.1",
                "file": source["file"], "source_raw_digest": source["raw_digest"], "fields": fields,
                "successor_delta": "OD-040: actual trust/authority/anchor/recovery fields; historical /1 immutable"}
    if node["currently_bound"]:
        schema = read(schema_path)
        if "const" in schema:
            properties = {name: {"const": value} for name, value in schema["const"].items()}
            required = set(properties)
        elif "$ref" in schema:
            target = schema["$defs"][schema["$ref"].rsplit("/", 1)[1]]
            variants = [schema["$defs"][v["$ref"].rsplit("/", 1)[1]] for v in target["oneOf"]]
            properties = {name: value for variant in variants for name, value in variant["properties"].items()}
            required = set.intersection(*(set(v["required"]) for v in variants))
        else:
            properties = schema["properties"]
            required = set(schema["required"])
        return {"selector": "EXACT_QUALIFIED_EXECUTABLE_BODY", "file": schema_path.relative_to(ROOT).as_posix(),
                "raw_digest": digest(schema_path), "fields": [{"field": name, "optional": name not in required, "schema": value} for name, value in properties.items()]}
    proposal = node.get("proposed_contract") or graph["schema_deferred_body_completion_decisions"].get(key)
    if proposal and proposal.get("body"):
        return {"selector": "EXPLICIT_PROPOSAL_BODY", "fields": [{"field": line.split(":", 1)[0].rstrip("?"), "optional": "?" in line.split(":", 1)[0], "design_type": line.split(":", 1)[1]} for line in proposal["body"]]}
    if key == "residual_risk/1":
        text = (ROOT / "docs/R5_4_2/R5_4_2_RESIDUAL_RISK_CONTRACT_DECISION_PROPOSAL.md").read_text(encoding="utf-8-sig")
        block = next(b for b in re.findall(r"```text\n(.*?)```", text, re.S) if b.startswith("risk_id\nsubject_ref\n"))
        return {"selector": "OWNER_APPROVED_RESIDUAL_RISK_BODY", "fields": fields_from_block(block)}
    if kind == "successor_campaign_selection_decision":
        # Data §14.5 states these six fields in prose. No neighboring RunManifest body.
        return {"selector": "DATA_14_5_EXACT_PROSE_BODY", "fields": fields_from_block("predecessor_conclusion_ref\ncandidate_successor_campaign_refs[]\nselected_successor_campaign_ref\nresolution_basis_refs[]\ngoverning_policy_ref\ninput_history_cut")}
    source = node["normative_semantic_source"]
    selector = SELECTORS[kind]
    blocks = re.findall(r"```(?:text|json)?\n(.*?)```", source["complete_section_text"], re.S)
    index = selector[0] if isinstance(selector, tuple) else selector
    block = blocks[index]
    if isinstance(selector, tuple):
        start = block.index(selector[1] + ":") + len(selector[1]) + 1
        block = re.split(r"\n[A-Za-z][A-Za-z_]+:\n", block[start:])[0]
    if kind == "coverage_obligation_key":
        block = block.split("{", 1)[1].split("}", 1)[0]
    return {"selector": "EXACT_NORMATIVE_BODY", "section": source["section"], "block": index,
            "file": source["file"], "source_raw_digest": source["raw_digest"], "fields": fields_from_block(block)}


def main():
    preserve()
    old = read(HISTORICAL)
    nodes = {}
    issues = []
    for node in old["nodes"]:
        body = select(node, old)
        if node["key"] == "grant_body/1":
            for field in body["fields"]:
                if field["field"] == "previous_knowledge_state_ref":
                    field["optional"] = False
                    field["source"] = "OWNER-DELEGATED DESIGN DECISION OD-025; Data 14.3 initial null sentinel"
            body["successor_delta"] = "OD-025: required null initial sentinel or exact prior knowledge reference"
        if node["key"] == "policy_revision/1":
            body["fields"].append({"field": "full_path_context_parameters_ref", "optional": False,
                                   "design_type": "ExternalProfileRef", "source": "OWNER-DELEGATED DESIGN DECISION OD-021"})
            body["successor_delta"] = "OD-021: exact full-path purpose dispatch binding; original /1 bytes remain immutable"
        if node["key"] == "spec_revision/1":
            body["fields"] = [f for f in body["fields"] if f["field"] not in ("attempt_transitions", "campaign_stage_lane_fsm")]
            body["fields"].append({"field": "transition_contract_ref", "optional": False,
                                   "design_type": "ExternalProfileRef", "source": "OWNER-DELEGATED DESIGN DECISION OD-022"})
            body["successor_delta"] = "OD-022: exact complete foundation transition table instead of vague text/duplicated attempt list"
        names = {f["field"] for f in body["fields"]}
        refs = [r for r in ((node.get("proposed_contract") or {}).get("material_refs") or (node.get("qualified_registry_row") or {}).get("material_refs", []))]
        for ref in refs:
            owner = ref["field"].split(".", 1)[0].removesuffix("[]")
            if owner not in names:
                issues.append({"id": node["key"] + ":REF_NOT_IN_OWNER_BODY:" + ref["field"], "status": "OPEN", "class": "D", "problem": "Material ref is not a field of the selected own body", "ref": ref})
        nodes[node["key"]] = {"key": node["key"], "kind": node["kind"], "version": node["version"], "body": body,
                              "historical_proposal": node.get("proposed_contract"), "material_refs": refs,
                              "qualified_registry_row": node.get("qualified_registry_row"),
                              "source_section": node.get("normative_semantic_source"),
                              "schema_generation_ready": False, "remaining_design_questions": ["Complete own-field types, material reference parity, profile grammar and version impact"]}
        specific = approved_specific_row(node["key"])
        if specific is not None:
            nodes[node["key"]]["approved_specific_registry_row"] = specific
    queue = deque(sorted(nodes))
    seen = set()
    traversal = []
    adjacency = {key: sorted({e["to"] for e in old["edges"] if e["from"] == key}) for key in nodes}
    while queue:
        key = queue.popleft()
        if key in seen:
            continue
        seen.add(key)
        targets = adjacency[key]
        for target in targets:
            assert target in nodes, "Missing semantic node " + target
            if target not in seen:
                queue.append(target)
        traversal.append({"expanded": key, "targets": targets})
    write("OWN_BODY_INVENTORY.json", {"source_graph_raw_digest": digest(HISTORICAL), "nodes": list(nodes.values()),
          "reachability_traversal": traversal, "graph_queue": list(queue), "issues": issues,
          "semantic_fixed_point_reached": False, "note": "Empty graph queue alone is not semantic completeness. All nodes deliberately remain not generation-ready until per-field audit."})
    register_path = OUT / "ISSUE_REGISTER.json"
    register = read(register_path) if register_path.exists() else {"issues": []}
    existing = {i["id"] for i in register["issues"]}
    discovered = issues + [{"id": i["id"], "status": "OPEN", "class": i["class"], "problem": i["reason"], "target": i["target"]} for i in old["unresolved"]]
    register["issues"].extend(i for i in discovered if i["id"] not in existing)
    write("ISSUE_REGISTER.json", register)
    print({"own_bodies_selected": len(nodes), "ref_ownership_issues": len(issues), "predicate_families_pending": len(old["unresolved"]), "semantic_fixed_point_reached": False})


if __name__ == "__main__":
    main()
