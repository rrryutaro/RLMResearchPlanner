from pathlib import Path

from rlm_research_planner.domain.models import PlayerState
from rlm_research_planner.repositories.player_repository import PlayerRepository
from rlm_research_planner.services.castle_planning import (
    CASTLE_RESOURCE_KEYS,
    CastleCatalog,
)


ROOT = Path(__file__).resolve().parents[1]


def load_catalog() -> CastleCatalog:
    return CastleCatalog.load(ROOT / "data" / "buildings" / "castle_catalog.json")


def test_castle_catalog_has_all_standard_building_levels() -> None:
    catalog = load_catalog()
    assert len(catalog.buildings) == 18
    assert all(len(building.levels) == 25 for building in catalog.buildings.values())
    assert all(
        building.levels[25].costs["gold_hammer"] == 1
        for building in catalog.buildings.values()
    )
    known_ids = set(catalog.buildings)
    assert {
        building_id
        for building in catalog.buildings.values()
        for level in building.levels.values()
        for building_id, _required_level in level.requirements
    } <= known_ids
    assert catalog.max_mana_stage == 5
    assert sorted(catalog.mana_stages) == [1, 2, 3, 4, 5]


def test_castle_plan_traces_facilities_and_totals_each_resource() -> None:
    catalog = load_catalog()
    plan = catalog.create_plan(
        castle_level=5,
        target_castle_level=6,
        construction_speed_percent=0,
        vip_level=1,
    )
    assert [(step.building_id, step.level) for step in plan.steps] == [
        ("castle_wall", 5),
        ("vault", 1),
        ("vault", 2),
        ("vault", 3),
        ("vault", 4),
        ("vault", 5),
        ("castle", 6),
    ]
    assert plan.total_base_seconds == sum(step.base_seconds for step in plan.steps)
    assert plan.total_costs == {
        key: sum(step.costs[key] for step in plan.steps)
        for key in CASTLE_RESOURCE_KEYS
    }
    assert {item.building_id: item.target_level for item in plan.buildings} == {
        "castle_wall": 5,
        "vault": 5,
        "castle": 6,
    }


def test_construction_speed_reduces_castle_plan_time() -> None:
    catalog = load_catalog()
    normal = catalog.create_plan(
        castle_level=24,
        target_castle_level=25,
        construction_speed_percent=0,
        vip_level=1,
    )
    faster = catalog.create_plan(
        castle_level=24,
        target_castle_level=25,
        construction_speed_percent=200,
        vip_level=1,
    )
    assert faster.total_adjusted_seconds < normal.total_adjusted_seconds
    assert faster.total_costs == normal.total_costs
    assert faster.total_costs["gold_hammer"] >= 1


def test_individual_academy_plan_includes_advanced_facilities_and_gem_estimate() -> None:
    catalog = load_catalog()
    plan = catalog.create_plan(
        castle_level=25,
        target_castle_level=25,
        saved_levels={
            "academy": 24,
            "battle_hall": 24,
            "prison": 24,
            "altar": 24,
        },
        target_building_id="academy",
        target_building_level=25,
        owned_resources={"war_tome": 1000},
        construction_speed_percent=0,
        vip_level=1,
    )
    assert plan.target_building_id == "academy"
    assert plan.target_building_level == 25
    assert ("battle_hall", 25) in {
        (step.building_id, step.level) for step in plan.steps
    }
    assert ("prison", 25) in {
        (step.building_id, step.level) for step in plan.steps
    }
    assert ("altar", 25) in {
        (step.building_id, step.level) for step in plan.steps
    }
    assert plan.total_costs["war_tome"] == 4500
    assert plan.gem_costs["war_tome"] == 35_500
    assert plan.total_gems == sum(plan.gem_costs.values())


def test_castle_plan_supports_five_post_25_mana_stages() -> None:
    catalog = load_catalog()
    plan = catalog.create_plan(
        castle_level=25,
        target_castle_level=25,
        current_mana_stage=1,
        target_mana_stage=5,
        construction_speed_percent=0,
        vip_level=1,
    )
    assert [(step.level, step.mana_stage) for step in plan.steps] == [
        (25, 2),
        (25, 3),
        (25, 4),
        (25, 5),
    ]
    assert plan.current_mana_stage == 1
    assert plan.target_mana_stage == 5
    assert plan.total_costs["mana_ore"] == 23029 * 4
    assert plan.total_costs["mana_crystal"] == 242 * 4
    assert plan.total_costs["mana_steel"] == 0


def test_post_25_mana_plan_includes_castle_25_when_not_completed() -> None:
    catalog = load_catalog()
    plan = catalog.create_plan(
        castle_level=24,
        target_castle_level=25,
        target_mana_stage=1,
        construction_speed_percent=0,
        vip_level=1,
    )
    assert plan.steps[-2].building_id == "castle"
    assert (plan.steps[-2].level, plan.steps[-2].mana_stage) == (25, 0)
    assert (plan.steps[-1].level, plan.steps[-1].mana_stage) == (25, 1)


def test_player_repository_round_trips_castle_settings() -> None:
    repository = PlayerRepository(":memory:")
    try:
        state = PlayerState()
        state.settings.construction_speed_percent = 176.25
        state.settings.construction_speed_boost_percent = 20
        state.settings.castle_target_level = 13
        state.settings.castle_mana_stage = 2
        state.settings.castle_target_mana_stage = 4
        state.building_levels = {"castle_wall": 12, "academy": 11}
        repository.save(state)
        restored = repository.load()
        assert restored.settings.construction_speed_percent == 176.25
        assert restored.settings.construction_speed_boost_percent == 20
        assert restored.settings.effective_construction_speed_percent == 196.25
        assert restored.settings.castle_target_level == 13
        assert restored.settings.castle_mana_stage == 2
        assert restored.settings.castle_target_mana_stage == 4
        assert restored.building_levels == {"castle_wall": 12, "academy": 11}
    finally:
        repository.close()
