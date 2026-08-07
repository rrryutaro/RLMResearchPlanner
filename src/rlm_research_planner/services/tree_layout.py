from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class TreePosition:
    column: int
    depth: int


def compact_explicit_row_slots(
    columns: Iterable[int],
    *,
    source_column_count: int,
    target_column_count: int,
) -> tuple[float, ...]:
    """Compress empty grid columns without changing left-to-right order."""

    ordered = tuple(sorted(columns))
    if not ordered:
        return ()
    if target_column_count <= 1:
        return (0.0,) * len(ordered)
    if len(ordered) >= target_column_count:
        return tuple(float(index) for index in range(len(ordered)))

    source_span = max(1, source_column_count - 1)
    target_span = float(target_column_count - 1)
    raw = tuple(column / source_span * target_span for column in ordered)
    if all(right - left >= 1.0 for left, right in zip(raw, raw[1:])):
        return raw

    row_span = float(len(ordered) - 1)
    centered_start = sum(raw) / len(raw) - row_span / 2.0
    start = max(0.0, min(target_span - row_span, centered_start))
    return tuple(start + index for index in range(len(ordered)))


def calculate_tree_positions(
    research_ids: Iterable[str],
    prerequisite_edges: Iterable[tuple[str, str]],
    display_order: Mapping[str, int],
) -> dict[str, TreePosition]:
    """Place prerequisites above their dependent research nodes.

    Edges are ``(prerequisite_id, research_id)``. Nodes involved in invalid
    cycles are kept visible on the final row instead of making the UI fail.
    """

    nodes = tuple(dict.fromkeys(research_ids))
    node_set = set(nodes)
    parents = {research_id: set() for research_id in nodes}
    children = {research_id: set() for research_id in nodes}
    for prerequisite_id, research_id in prerequisite_edges:
        if prerequisite_id not in node_set or research_id not in node_set:
            continue
        if prerequisite_id == research_id:
            continue
        parents[research_id].add(prerequisite_id)
        children[prerequisite_id].add(research_id)

    indegree = {research_id: len(values) for research_id, values in parents.items()}
    depth = {research_id: 0 for research_id in nodes}
    ready = sorted(
        (research_id for research_id in nodes if indegree[research_id] == 0),
        key=lambda research_id: (display_order.get(research_id, 0), research_id),
    )
    visited: set[str] = set()
    while ready:
        research_id = ready.pop(0)
        visited.add(research_id)
        for child_id in sorted(
            children[research_id],
            key=lambda value: (display_order.get(value, 0), value),
        ):
            depth[child_id] = max(depth[child_id], depth[research_id] + 1)
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                ready.append(child_id)
                ready.sort(key=lambda value: (display_order.get(value, 0), value))

    if len(visited) != len(nodes):
        last_depth = max(depth.values(), default=-1) + 1
        for research_id in nodes:
            if research_id not in visited:
                depth[research_id] = last_depth

    rows: dict[int, list[str]] = {}
    for research_id in nodes:
        rows.setdefault(depth[research_id], []).append(research_id)
    for row in rows.values():
        row.sort(key=lambda value: (display_order.get(value, 0), value))

    return {
        research_id: TreePosition(column=column, depth=row_depth)
        for row_depth, row in rows.items()
        for column, research_id in enumerate(row)
    }
