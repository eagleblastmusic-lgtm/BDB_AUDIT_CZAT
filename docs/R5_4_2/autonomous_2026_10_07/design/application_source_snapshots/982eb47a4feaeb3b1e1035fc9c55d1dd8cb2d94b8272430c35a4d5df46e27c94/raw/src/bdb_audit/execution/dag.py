"""Execution DAG validation and cycle detection (M19)."""
from collections import defaultdict
from typing import Sequence

from ..core.errors import ValidationError


def parse_edges(edges: Sequence[str | tuple[str, str]]) -> list[tuple[str, str]]:
    parsed = []
    for e in edges:
        if isinstance(e, str) and "->" in e:
            src, dst = e.split("->", 1)
            parsed.append((src.strip(), dst.strip()))
        elif isinstance(e, (tuple, list)) and len(e) == 2:
            parsed.append((str(e[0]).strip(), str(e[1]).strip()))
        else:
            raise ValidationError("INVALID_EDGE_FORMAT", str(e))
    return parsed


def validate_execution_dag(edges: Sequence[str | tuple[str, str]]) -> dict:
    """Validate execution DAG acyclicity and ordering.

    R5.3.1 / FR-04:
    - Result never receives a backlink from a record that itself points to result.
    - Graph must be strictly acyclic. Cycles raise CONTENT_REFERENCE_CYCLE.
    """
    parsed = parse_edges(edges)
    adj: dict[str, list[str]] = defaultdict(list)
    nodes = set()

    for src, dst in parsed:
        adj[src].append(dst)
        nodes.add(src)
        nodes.add(dst)

    # Detect cycles using standard DFS (white/gray/black coloring)
    visited = {}  # node: 0 (unvisited), 1 (visiting), 2 (visited)
    for n in nodes:
        visited[n] = 0

    def dfs(node: str) -> bool:
        visited[node] = 1
        for neighbor in adj[node]:
            if visited[neighbor] == 1:
                return True  # Cycle detected
            if visited[neighbor] == 0:
                if dfs(neighbor):
                    return True
        visited[node] = 2
        return False

    for n in nodes:
        if visited[n] == 0:
            if dfs(n):
                raise ValidationError("CONTENT_REFERENCE_CYCLE", "Execution DAG contains a reference cycle")

    return {
        "acyclic": True,
        "result": "ACCEPT",
        "nodes": sorted(nodes),
        "edge_count": len(parsed),
    }
