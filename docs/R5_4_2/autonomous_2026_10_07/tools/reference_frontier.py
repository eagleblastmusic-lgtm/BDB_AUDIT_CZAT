"""Fresh own-field reference frontier, retaining historical evidence separately."""

from __future__ import annotations

import copy
import json
from collections import defaultdict

from execution import OUT, ROOT, digest, read, write


def main():
    historical_path = ROOT / "docs/R5_4_2/R5_4_2_SEMANTIC_CLOSURE_GRAPH_V2.json"
    historical = read(historical_path)
    inventory = read(OUT / "OWN_BODY_INVENTORY.json")
    nodes = {n["key"]: n for n in inventory["nodes"]}
    effective = {n["key"]: n for n in historical["nodes"]}
    replacements = historical["V2_version_target_rules"]
    if not isinstance(replacements, dict):
        raise TypeError("Version rules require explicit mapping")
    edges = []
    issues = []
    dropped = []
    actual_fields = set()
    for key, node in nodes.items():
        fields = {f["field"]: f for f in node["body"]["fields"]}
        actual_fields.update(key + "." + name for name in fields)
        grouped = defaultdict(list)
        for edge in effective[key]["V2_effective_canonical_reference_edges"]:
            owner = edge["field"].split(".", 1)[0].removesuffix("[]")
            if owner not in fields:
                dropped.append(copy.deepcopy(edge))
            else:
                grouped[edge["field"]].append(edge)
        refs = {r["field"]: copy.deepcopy(r) for r in node["material_refs"]}
        for r in effective[key].get("proposed_material_ref_completion", []):
            refs[r["field"]] = copy.deepcopy(r)
        for field, field_edges in grouped.items():
            entry = refs.setdefault(field, {"field": field})
            entry["allowed_keys"] = sorted({e["to"] for e in field_edges})
            entry["ref_class"] = field_edges[0]["ref_class"]
            entry["cardinality"] = field_edges[0]["cardinality"]
        for name, field in fields.items():
            if name not in refs and (name.endswith(("_ref", "_refs", "_history_cut", "_cut")) or name in ("as_of_head", "export_as_of_head", "report_as_of_head", "surface_key")):
                candidate = historical["normative_body_reference_field_catalog"].get(key + "." + name)
                if candidate and candidate.get("allowed_keys"):
                    targets = [replacements.get(t, t) for t in candidate["allowed_keys"]]
                    assert set(targets) <= set(nodes), (key, name, targets)
                    refs[name] = {"field": name, "allowed_keys": sorted(targets),
                                  "ref_class": candidate.get("ref_class"),
                                  "cardinality": "0..65536" if field.get("array") or field.get("design_type", "").endswith("[]") else "0..1" if field["optional"] else "1",
                                  "source": "OWN_FIELD_MATCHED_HISTORICAL_DESIGN_TARGET; requires exact semantic review"}
                else:
                    issues.append({"id": key + "." + name, "status": "OPEN", "class": "D",
                                   "problem": "Own reference field lacks exact resolved representation/profile/ref class",
                                   "historical_navigation": candidate})
        for field, entry in refs.items():
            owner = field.split(".", 1)[0].removesuffix("[]")
            if owner not in fields:
                issues.append({"id": key + "." + field, "status": "OPEN", "class": "D",
                               "problem": "Historical proposed material reference is absent from the exact own body; must be explicitly corrected/versioned", "reference": entry})
                continue
            targets = entry.get("allowed_keys", [])
            if not targets:
                issues.append({"id": key + "." + field, "status": "OPEN", "class": "D",
                               "problem": "Material ref needs explicit noncanonical representation or finite canonical targets", "reference": entry})
            for target in targets:
                assert target in nodes, (key, field, target)
                edges.append({"from": key, "to": target, "field": field,
                              "cardinality": entry["cardinality"], "ref_class": entry["ref_class"]})
        node["fresh_material_ref_frontier"] = list(refs.values())
    foreign_fields = sorted(set(historical["normative_body_reference_field_catalog"]) - actual_fields)
    result = {
        "source_graph_raw_digest": digest(historical_path),
        "own_body_inventory_raw_digest": digest(OUT / "OWN_BODY_INVENTORY.json"),
        "nodes": list(nodes.values()), "edges": edges, "reference_frontier": issues,
        "historical_edges_not_owned_by_selected_body": dropped,
        "historical_catalog_nonown_fields": foreign_fields,
        "semantic_fixed_point_reached": False,
        "note": "Finite graph is fresh own-body filtered. Noncanonical/purpose profile and nested material ref design remains an explicit queue; no diagnostic completeness accepted by assertion.",
    }
    write("REFERENCE_FRONTIER.json", result)
    print(json.dumps({"nodes": len(nodes), "own_reference_edges": len(edges), "reference_design_frontier": len(issues),
                      "historical_nonown_catalog_entries": len(foreign_fields), "discarded_nonown_edges": len(dropped)}))


if __name__ == "__main__":
    main()
