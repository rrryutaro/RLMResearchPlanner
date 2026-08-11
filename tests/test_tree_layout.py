from __future__ import annotations

from rlm_research_planner.services.tree_layout import (
    calculate_tree_positions,
    compact_explicit_row_slots,
)


def test_explicit_five_column_rows_compact_to_four_visible_slots() -> None:
    assert compact_explicit_row_slots(
        [0, 1, 3, 4], source_column_count=5, target_column_count=4
    ) == (0.0, 1.0, 2.0, 3.0)
    assert compact_explicit_row_slots(
        [0, 2], source_column_count=4, target_column_count=4
    ) == (0.0, 2.0)
    assert compact_explicit_row_slots(
        [0, 2, 4], source_column_count=5, target_column_count=4
    ) == (0.0, 1.5, 3.0)


def test_tree_layout_places_prerequisites_above_dependents() -> None:
    positions = calculate_tree_positions(
        ["root", "left", "right", "end"],
        [("root", "left"), ("root", "right"), ("left", "end"), ("right", "end")],
        {"root": 1, "left": 2, "right": 3, "end": 4},
    )
    assert positions["root"].depth == 0
    assert positions["left"].depth == positions["right"].depth == 1
    assert positions["end"].depth == 2


def test_tree_layout_keeps_cyclic_nodes_visible() -> None:
    positions = calculate_tree_positions(
        ["a", "b"],
        [("a", "b"), ("b", "a")],
        {"a": 1, "b": 2},
    )
    assert set(positions) == {"a", "b"}
    assert positions["a"].depth == positions["b"].depth
