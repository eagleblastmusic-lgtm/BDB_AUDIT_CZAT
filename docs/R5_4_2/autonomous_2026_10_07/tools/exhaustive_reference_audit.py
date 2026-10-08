"""Discover references from actual body grammars, not only a supplied edge list."""

from __future__ import annotations

import json

from execution import BASE, OUT, digest, preserve, read, write


TERMINALS = {
    "typed_ref": "TypedRef", "raw_ref": "RawRef", "external_profile_ref": "ExternalProfileRef",
    "history_cut": "HistoryCut", "accepted_history_cut": "HistoryCut", "empty_history_cut": "HistoryCut",
    "accepted_head_ref": "AcceptedHead", "accepted_event_ref": "AcceptedEventRef",
}


def normalized(path):
    return path.replace("[]", "")


def references(schema):
    found = {}
    external = []

    def walk(value, path, stack=()):
        if not isinstance(value, dict):
            return
        target = value.get("$ref")
        if target:
            if target.startswith("#/$defs/"):
                name = target.split("/")[-1]
                if name in TERMINALS and path:
                    found.setdefault(path, set()).add(TERMINALS[name])
                    return
                if name in stack:
                    raise ValueError((path, "UNRESOLVED_RECURSIVE_BODY", name))
                walk(schema["$defs"][name], path, (*stack, name))
            elif target.startswith("BDB_SCHEMA_REGISTRY::"):
                external.append({"path": path, "schema_key": target})
            else:
                raise ValueError((path, "UNBOUND_SCHEMA_REFERENCE", target))
            return
        for keyword in ("oneOf", "anyOf", "allOf"):
            for branch in value.get(keyword, []):
                walk(branch, path, stack)
        for field, child in value.get("properties", {}).items():
            walk(child, path + "." + field if path else field, stack)
        if "items" in value:
            walk(value["items"], path + "[]", stack)

    # Unused $defs are not own body references. Inherited const roots contain
    # data rather than schema paths and are separately reviewed as pinned roots.
    walk({k: v for k, v in schema.items() if k != "$defs"}, "")
    return found, external


def main():
    preserve()
    graph = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    discovered = []
    pending = []
    for node in graph["nodes"]:
        old_key = node["key"]
        new_key = mapping[old_key]
        source = (OUT / "design/body_grammars" / (new_key.replace("/", "__") + ".json")
                  if new_key != old_key or node["body"]["selector"] != "EXACT_QUALIFIED_EXECUTABLE_BODY"
                  else BASE / "candidate/schemas" / (old_key.replace("/", "__") + ".schema.json"))
        actual, external = references(read(source))
        declared = {normalized(item["field"]): item for item in node["resolved_own_material_refs"]}
        for path, types in sorted(actual.items()):
            entry = declared.get(normalized(path))
            # A parent declared tagged union may fully enumerate its nested refs,
            # but the parent alone is not assumed to declare arbitrary children.
            row = {"owner": old_key, "successor": new_key, "field": path, "representations": sorted(types),
                   "declared": entry is not None, "source_raw_digest": digest(source)}
            discovered.append(row)
            if entry is None:
                pending.append({**row, "status": "OPEN", "problem": "ACTUAL_BODY_REFERENCE_NOT_IN_EXPLICIT_MATERIAL_REF_CONTRACT"})
        for dependency in external:
            assert dependency["schema_key"] in {"BDB_SCHEMA_REGISTRY::" + key for key in mapping.values()}, dependency
    write("design/EXHAUSTIVE_REFERENCE_AUDIT.json", {
        "discovered": discovered, "pending": pending, "actual_body_reference_paths": len(discovered),
        "missing_reference_declarations": len(pending), "fixed_point_reached": False,
        "claim": "Independent discovery from actual draft/inherited bodies. Path presence alone is not schema/temporal/producer qualification.",
    })
    print(json.dumps({"actual_body_reference_paths": len(discovered), "missing_reference_declarations": len(pending), "fixed_point_reached": False}))
    for row in pending:
        print(row["owner"] + "." + row["field"] + ":" + ",".join(row["representations"]))


if __name__ == "__main__":
    main()
