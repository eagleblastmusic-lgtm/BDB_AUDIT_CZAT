"""Check draft material-reference cardinalities without claiming qualification.

An element's multiplicity is measured inside its owning object, not across an
entire ancestor array. Conditional availability remains a distinct obligation.
"""

from __future__ import annotations

import re

from execution import BASE, OUT, preserve, read, write
from material_path_audit import variants


def locations(root, path):
    current = [root]
    for part in path.split("."):
        name = part.removesuffix("[]")
        found = []
        for schema in current:
            expanded = variants(schema, root)
            containers = list(expanded)
            for candidate in expanded:
                if isinstance(candidate.get("items"), dict):
                    containers.extend(variants(candidate["items"], root))
            for parent in containers:
                child = parent.get("properties", {}).get(name)
                if child is not None:
                    found.append((parent, child))
        if not found:
            return []
        current = []
        for _, child in found:
            if part.endswith("[]"):
                current.extend(v["items"] for v in variants(child, root) if isinstance(v.get("items"), dict))
            else:
                current.append(child)
    return found


def main():
    preserve()
    graph = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    results, issues, conditional = [], [], []
    for node in graph["nodes"]:
        key = mapping[node["key"]]
        path = OUT / "design/body_grammars" / (key.replace("/", "__") + ".json")
        if not path.exists():
            path = BASE / "candidate/schemas" / (node["key"].replace("/", "__") + ".schema.json")
        root = read(path)
        for item in node["resolved_own_material_refs"]:
            field, cardinality = item["field"], item["cardinality"]
            if node["key"] == "command_envelope/1" and field == "command_payload_ref":
                continue
            selected = locations(root, field)
            entry = {"owner": node["key"], "design_key": key, "field": field, "declared": cardinality}
            errors = []
            numeric = re.match(r"^(\d+)(?:\.\.(\d+))?(?=$|;|\s)", cardinality)
            if not selected:
                errors.append("MATERIAL_PATH_MISSING")
            elif numeric and ";" not in cardinality and " per " not in cardinality and " if " not in cardinality:
                minimum = int(numeric[1])
                maximum = int(numeric[2] or numeric[1])
                for parent, child in selected:
                    expanded = variants(child, root)
                    arrays = [v for v in expanded if v.get("type") == "array"]
                    if arrays:
                        for value in arrays:
                            if value.get("minItems", 0) != minimum or value.get("maxItems") != maximum:
                                errors.append({"problem": "ARRAY_CARDINALITY_MISMATCH", "actual_min": value.get("minItems", 0), "actual_max": value.get("maxItems")})
                    elif minimum == 1 and ";" not in cardinality and " if " not in cardinality:
                        if field.split(".")[-1].removesuffix("[]") not in parent.get("required", []):
                            errors.append("PRIOR_REQUIRED_REFERENCE_IS_OPTIONAL_IN_OWNING_BRANCH")
            if cardinality not in ("1", "0..1", "0..65536", "1..65536", "2..65536", "1..256"):
                conditional.append({**entry, "status": "REQUIRES_EXPLICIT_CONDITION_OR_SEMANTIC_PREDICATE"})
            entry["result"] = "FAIL" if errors else "LOCAL_MULTIPLICITY_CONSISTENT"
            entry["issues"] = errors
            results.append(entry)
            if errors:
                issues.append(entry)
    write("design/CARDINALITY_AUDIT.json", {"results": results, "issues": issues, "conditional_obligations": conditional,
          "qualification": False, "semantic_conditions_verified": False})
    print({"checked": len(results), "local_multiplicity_issues": len(issues), "conditional_obligations": len(conditional)})
    for issue in issues:
        print(issue["owner"] + "." + issue["field"] + ": " + str(issue["issues"]))


if __name__ == "__main__":
    main()
