"""Finite explicit successor propagation; original keys remain forensic readers."""

from __future__ import annotations

from collections import defaultdict, deque

from execution import BASE, OUT, preserve, read, write


# These are parameterized installation data contracts, not campaign facts whose
# target semantics can be changed by a same-commit parent. Candidate row/schema
# parity still independently checks them; this list does not waive qualification.
DATA_ROOTS = {
    "artifact_contract_registry", "schema_registry", "installation_bootstrap_profile",
    "trust_profile", "source_manifest",
}

# Fresh nested-domain review found open object bags in three already-bound
# schemas, and SpecRevision embeds the old exact NF02 wire-version table.
EXPLICIT_CHANGED_BOUND = {
    "source_manifest": "OD-030 canonical source paths admit dot-prefixed names and original Unicode while rejecting dot/traversal/empty components; historical /1 unchanged",
    "legacy_mechanical_validation_assessment": "Close parsed legacy facts; raw original remains forensic authority",
    "source_reconciliation_assessment": "Close incoming identifier assertion representation; none establish source authority",
    "view_manifest": "Close metadata projection and retain exact RawRef member domain",
    "spec_revision": "Version exact transition artifact-kind/version table after target successor propagation",
    "policy_revision": "Old exact const policy is NF02-only; successor explicitly governs complete qualified full-path predicates and profiles",
    "stage_spec": "Freeze explicit purpose-constrained profile/reference contract instead of previously deferred material refs",
    "lane_spec": "Freeze exact completion/effort/exploration profile purposes and propagated result contracts",
    "executor_spec": "Freeze exact runtime/tool/environment/isolation profile purposes and material reference obligations",
    "delivery_spec": "Freeze retained-byte retry/idempotency and exact positive-view/redaction profile material references",
    "source_identity": "Explicit exact source-bound category/language/runtime surface-normalizer profile context; no silent key reinterpretation",
}


def main():
    preserve()
    registry = read(BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json")
    historical_versions = defaultdict(list)
    for row in registry["contracts"]:
        historical_versions[row["kind"]].append(int(row["version"]))
    graph = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")
    nodes = {n["key"]: n for n in graph["nodes"]}
    incoming = defaultdict(list)
    for edge in graph["edges"]:
        incoming[edge["to"]].append((edge["from"], edge["field"]))
    changed = {}
    queue = deque()
    for key, node in nodes.items():
        kind = node["kind"]
        if kind not in historical_versions:
            changed[key] = {"reason": "NEW_CANONICAL_SEMANTIC_KIND", "successor_key": key}
            queue.append(key)
        elif node["body"]["selector"] != "EXACT_QUALIFIED_EXECUTABLE_BODY" or kind in EXPLICIT_CHANGED_BOUND:
            successor = kind + "/" + str(max(historical_versions[kind]) + 1)
            changed[key] = {"reason": EXPLICIT_CHANGED_BOUND.get(kind, "CLOSED_BODY_OR_MATERIAL_REFERENCE_CONTRACT_NOT_PREVIOUSLY_EXECUTABLE"), "successor_key": successor}
            queue.append(key)
    expansions = []
    while queue:
        target = queue.popleft()
        affected = []
        for parent, field in incoming[target]:
            if parent in changed or nodes[parent]["kind"] in DATA_ROOTS:
                continue
            kind = nodes[parent]["kind"]
            changed[parent] = {
                "reason": "EXACT_REFERENCE_TARGET_SUCCESSOR", "target": target, "field": field,
                "successor_key": kind + "/" + str(max(historical_versions[kind]) + 1),
            }
            affected.append(parent)
            queue.append(parent)
        expansions.append({"expanded": target, "new_successors": affected})
    mapping = {key: changed.get(key, {}).get("successor_key", key) for key in nodes}
    assert len(set(mapping.values())) == len(nodes)
    stable = [key for key in nodes if key not in changed]
    write("design/VERSION_IMPACT_PLAN.json", {
        "status": "DESIGN_PROPAGATION_NOT_FROZEN", "mapping": mapping, "decisions": changed,
        "traversal": expansions, "queue": list(queue), "unchanged_contract_keys": stable,
        "historical_reader_rule": "Original exact bytes/schema contexts are retained; no alias or automatic old campaign upgrade",
        "data_root_rule": "Same contract version only if field semantics/body grammar remain identical; changed literal trust-root data is a new exact immutable revision and never an unqualified campaign write",
        "mandatory_remaining_audit": [
            "Compare stable keys own material refs and nested semantic domain to original qualified schema",
            "Audit generic wrapper embedded object/event target domains; extend successor propagation when their accepted finite wire set changes",
            "Audit all profile version/identity changes and pinned bootstrap references",
        ],
    })
    print({"active_keys": len(mapping), "new_kinds": sum(n["kind"] not in historical_versions for n in nodes.values()),
           "successor_kind_versions": sum(k != v for k, v in mapping.items()), "stable_contract_keys": len(stable), "propagation_queue": len(queue)})
    print("Stable: " + ", ".join(stable))


if __name__ == "__main__":
    main()
