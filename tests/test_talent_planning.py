from __future__ import annotations

from pathlib import Path

import pytest

from rlm_research_planner.domain.models import TalentPlanStep
from rlm_research_planner.services.talent_planning import (
    TALENT_DIRECTIVE_DOCUMENT_TYPE,
    TalentCatalog,
    TalentCatalogError,
    talent_directive_from_payload,
    talent_directive_payload,
)


def _catalog() -> TalentCatalog:
    path = Path(__file__).resolve().parents[1] / "data" / "talents" / "catalog.json"
    return TalentCatalog.load(path)


def test_talent_catalog_has_complete_tree_and_valid_presets() -> None:
    catalog = _catalog()

    assert len(catalog.talents) == 47
    assert len(catalog.presets) == 6
    assert "army_general" in catalog.presets
    assert catalog.default_available_points == 278
    assert catalog.points_for_player_level(1) == 0
    assert catalog.points_for_player_level(60) == 278
    assert all(catalog.plan_for_preset(preset_id) for preset_id in catalog.preset_order)


def test_talent_layout_keeps_military_and_economy_in_stable_lanes() -> None:
    catalog = _catalog()
    columns = catalog.layout_columns()
    military = [
        columns[item.id]
        for item in catalog.talents.values()
        if item.branch == "military"
    ]
    economy = [
        columns[item.id]
        for item in catalog.talents.values()
        if item.branch == "economy"
    ]

    assert max(military) < min(economy)
    assert min(economy) - max(military) >= 1
    assert columns["squad_offense_i"] == pytest.approx(1)
    assert columns["food_production_i"] == pytest.approx(2)
    assert columns["cavalry_offense_i"] == pytest.approx(1)
    assert columns["stone_production_i"] == pytest.approx(2)
    assert columns["trap_building_i"] < columns["cavalry_offense_i"]
    assert columns["stone_production_i"] < columns["construction_speed_i"]

    expected_rows = (
        ("squad_offense_i", "food_production_i"),
        ("trap_building_i", "cavalry_offense_i", "stone_production_i", "construction_speed_i"),
        ("training_speed_i", "ranged_offense_i", "timber_production_i", "research_i"),
        ("siege_engine_offense_i", "infantry_offense_i", "ore_production_i", "gold_production_i"),
        ("trap_offense_i", "squad_defense_i", "food_production_ii", "max_load_i"),
        ("squad_health_i", "stone_production_ii", "gathering_i"),
        ("siege_engine_offense_ii", "ranged_offense_ii", "ore_production_ii", "timber_production_ii"),
        ("trap_building_ii", "infantry_offense_ii", "construction_speed_ii", "gold_production_ii"),
        ("trap_offense_ii", "cavalry_offense_ii", "research_ii"),
        ("training_speed_ii", "infantry_offense_iii", "gathering_ii", "max_load_ii"),
        ("siege_engine_offense_iii", "cavalry_offense_iii", "food_production_iii"),
        ("trap_offense_iii", "ranged_offense_iii", "timber_production_iii", "ore_production_iii"),
        ("squad_defense_ii", "squad_health_ii", "stone_production_iii", "gold_production_iii"),
    )
    for row_number, talent_ids in enumerate(expected_rows, start=1):
        actual = tuple(
            talent.id
            for talent in sorted(
                (
                    item
                    for item in catalog.talents.values()
                    if item.row == row_number
                ),
                key=lambda item: columns[item.id],
            )
        )
        assert actual == talent_ids
        expected_columns = {
            1: (1, 2),
            6: (1, 2, 3),
            9: (0, 1, 2),
            11: (0, 1, 2),
        }.get(row_number, tuple(range(len(talent_ids))))
        assert tuple(columns[talent_id] for talent_id in talent_ids) == expected_columns


def test_preset_expansion_inserts_prerequisites_before_targets() -> None:
    catalog = _catalog()
    plan = catalog.plan_for_preset("growth_speed")
    positions = {
        (step.talent_id, step.target_level): index for index, step in enumerate(plan)
    }

    assert positions[("stone_production_i", 2)] < positions[("construction_speed_i", 10)]
    assert positions[("construction_speed_i", 10)] < positions[("research_i", 10)]
    assert positions[("construction_speed_ii", 20)] < positions[("research_ii", 20)]


def test_allocation_never_spends_more_points_than_available() -> None:
    catalog = _catalog()
    allocation = catalog.allocate(catalog.plan_for_preset("infantry_war"), 25)

    assert allocation.used_points == 25
    assert allocation.remaining_points == 0
    assert allocation.required_points > allocation.used_points
    assert any(step.allocated_level < step.target_level for step in allocation.steps)


def test_required_points_are_converted_to_minimum_player_level() -> None:
    catalog = _catalog()

    assert catalog.player_level_requirement(0).player_level == 1
    assert catalog.player_level_requirement(1).player_level == 2
    assert catalog.player_level_requirement(278).player_level == 60
    assert catalog.player_level_requirement(288, bonus_points=10).player_level == 60
    over = catalog.player_level_requirement(289, bonus_points=10)
    assert over.player_level is None
    assert over.shortage_at_max_level == 1


def test_priority_moves_selected_goal_first_but_keeps_its_prerequisites() -> None:
    catalog = _catalog()
    original = catalog.presets["growth_speed"].targets
    allocation = catalog.allocate(original, 8, "research_i")
    ids = [step.talent_id for step in allocation.steps]

    assert ids.index("construction_speed_i") < ids.index("research_i")
    assert ids.index("research_i") < ids.index("construction_speed_ii")


def test_general_army_preset_prioritizes_shared_army_stats() -> None:
    catalog = _catalog()
    targets = catalog.presets["army_general"].targets

    assert [step.talent_id for step in targets] == [
        "squad_health_i",
        "squad_health_ii",
        "squad_offense_i",
        "squad_defense_i",
        "squad_defense_ii",
    ]


def test_talent_directive_round_trip_preserves_order_and_points() -> None:
    steps = (
        TalentPlanStep("food_production_i", 2),
        TalentPlanStep("stone_production_i", 2),
        TalentPlanStep("construction_speed_i", 10),
    )
    payload = talent_directive_payload(
        steps,
        name="建設用",
        catalog_version="1.0.0",
    )
    directive = talent_directive_from_payload(payload)

    assert payload["document_type"] == TALENT_DIRECTIVE_DOCUMENT_TYPE
    assert "available_points" not in payload
    assert directive.name == "建設用"
    assert directive.steps == steps


def test_unknown_talent_in_directive_is_rejected_by_catalog() -> None:
    catalog = _catalog()
    with pytest.raises(TalentCatalogError, match="unknown talent id"):
        catalog.expand_targets((TalentPlanStep("not_a_talent", 1),))
