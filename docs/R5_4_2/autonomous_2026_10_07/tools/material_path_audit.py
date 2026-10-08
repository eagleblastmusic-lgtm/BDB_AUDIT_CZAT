"""Material references must resolve to fields of the actual closed grammar."""

from __future__ import annotations

from execution import BASE, OUT, preserve, read, write


def variants(value, root, seen=frozenset()):
    if not isinstance(value, dict):
        return []
    result = [value]
    target = value.get("$ref")
    if target and target.startswith("#/") and target not in seen:
        selected = root
        for part in target[2:].split("/"):
            selected = selected[part.replace("~1", "/").replace("~0", "~")]
        result.extend(variants(selected, root, seen | {target}))
    for keyword in ("allOf", "oneOf", "anyOf"):
        for part in value.get(keyword, []):
            result.extend(variants(part, root, seen))
    return result


def resolve(schema, path):
    current = [schema]
    for part in path.split("."):
        field = part.removesuffix("[]")
        children = []
        for value in current:
            for variant in variants(value, schema):
                for container in ([variant] + ([variant["items"]] if isinstance(variant.get("items"), dict) else [])):
                    # Some inherited paths omit [] notation; their array owner
                    # is nevertheless established by the exact schema itself.
                    containers = variants(container, schema)
                    for resolved in containers:
                        child = resolved.get("properties", {}).get(field)
                        if child:
                            if part.endswith("[]"):
                                found_items = [v["items"] for v in variants(child, schema) if isinstance(v.get("items"), dict)]
                                children.extend(found_items)
                            else:
                                children.append(child)
        current = children
        if not current:
            return False
    return bool(current)


def main():
    preserve()
    graph = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    results = []
    issues = []
    for node in graph["nodes"]:
        target = mapping[node["key"]]
        path = OUT / "design/body_grammars" / (target.replace("/", "__") + ".json")
        if not path.exists():
            path = BASE / "candidate/schemas" / (node["key"].replace("/", "__") + ".schema.json")
        schema = read(path)
        for material in node["resolved_own_material_refs"]:
            field = material["field"]
            if node["key"] == "command_envelope/1" and field == "command_payload_ref":
                results.append({"owner": node["key"], "field": field, "result": "SUPERSEDED", "reason": "OD-016 requires inline payload only"})
                continue
            passed = resolve(schema, field)
            result = {"owner": node["key"], "design_key": target, "field": field, "result": "PASS" if passed else "FAIL"}
            results.append(result)
            if not passed:
                issues.append({**result, "reference": material, "status": "OPEN"})
    write("design/MATERIAL_PATH_AUDIT.json", {"results": results, "issues": issues, "claim": "Own-path existence only; target authority/cardinality/temporal predicates remain separately required"})
    print({"material_paths": len(results), "missing_paths": len(issues)})
    for issue in issues:
        print(issue["owner"] + "." + issue["field"])


if __name__ == "__main__":
    main()
