"""Reproduce OD-016/bootstrap precedence conflict and draft its successor.

These are contract-order witnesses, not accepted-instance or qualification proof.
"""

import copy
import heapq

from execution import BASE, OUT, digest, preserve, read, write


def order(nodes, edges):
    incoming = {n: set() for n in nodes}
    for before, after in edges:
        assert before in incoming and after in incoming
        incoming[after].add(before)
    ready = [n for n in nodes if not incoming[n]]
    heapq.heapify(ready)
    result = []
    while ready:
        node = heapq.heappop(ready)
        result.append(node)
        for other in incoming:
            if node in incoming[other]:
                incoming[other].remove(node)
                if not incoming[other]:
                    heapq.heappush(ready, other)
    return result if len(result) == len(nodes) else None


def precedence(profile, nodes):
    groups = profile["ordered_kind_groups"]
    return {(a, b) for i, group in enumerate(groups) for later in groups[i + 1:]
            for a in nodes if a in group for b in nodes if b in later}


def main():
    preserve()
    registry_path = BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json"
    old = read(registry_path)["order_only_precedence_profiles"]["BDB_BOOTSTRAP_PRECEDENCE_V1"]
    new = copy.deepcopy(old)
    new["ordered_kind_groups"] = [g for g in old["ordered_kind_groups"] if g != ["command_envelope"]]
    command_schema = read(OUT / "design/body_grammars/command_envelope__2.json")
    assert "proposed_object_refs" in command_schema["$defs"]["command_payload"]["properties"]
    # OD-016 requires the proposed object closure and artifact events in the
    # inline command payload. Thus each proposed fact precedes the command as
    # a hash/content dependency; no acceptance authority derives from this edge.
    nodes = [g[0] for g in old["ordered_kind_groups"]]
    content = {(n, "command_envelope") for n in nodes if n != "command_envelope"}
    assert order(nodes, content | precedence(old, nodes)) is None
    result = order(nodes, content | precedence(new, nodes))
    assert result is not None and result[-1] == "command_envelope"
    assert order(nodes, content | precedence(new, nodes) | {("command_envelope", "campaign_genesis")}) is None
    write("design/BOOTSTRAP_PRECEDENCE_SUCCESSOR.json", {
        "profile_id": "BDB_BOOTSTRAP_PRECEDENCE_V2", "predecessor_profile_id": "BDB_BOOTSTRAP_PRECEDENCE_V1",
        "source_registry_raw_digest": digest(registry_path), "profile": new,
        "controls": {"inherited_union_cycle_reproduced": True, "successor_contract_order": result,
                     "restored_command_first_cycle_rejected": True},
        "witness_content_edges": sorted(content), "witness_order_only_edges": sorted(precedence(new, nodes)),
        "qualification": False, "accepted_instance_DAG": "NOT_PROVEN",
        "remaining": "Materialize exact Registry/installation pin and normative successor; prove all actual instance bodies, pins, union edges and guards. This witness does not prove full bootstrap feasibility."})
    print("Bootstrap contract-order conflict reproduced; successor order controls PASS; accepted-instance DAG NOT_PROVEN")


if __name__ == "__main__":
    main()
