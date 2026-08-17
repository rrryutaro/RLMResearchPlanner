from __future__ import annotations

from pathlib import Path

import pytest

from rlm_research_planner.domain.models import PlayerSettings, PlayerState
from rlm_research_planner.domain.observations import (
    ObservedResearchLevel,
    ObservedResearchNode,
    ObservedResearchRequirement,
    ResearchTreeObservation,
)
from rlm_research_planner.paths import AppPaths
from rlm_research_planner.repositories.catalog_repository import (
    JsonResearchCatalogRepository,
)
from rlm_research_planner.services.catalog_planning import CatalogResearchPlanner
from rlm_research_planner.services.technolabe import (
    TECHNOLABE_CAPACITY_SECONDS,
    is_technolabe_recommended,
    technolabe_usage,
)


def _level(
    number: int,
    *,
    requirements: tuple[ObservedResearchRequirement, ...] = (),
    seconds: int | None = 100,
    food: int = 10,
    academy: int | None = None,
) -> ObservedResearchLevel:
    return ObservedResearchLevel(
        level=number,
        academy_level=number if academy is None else academy,
        base_time_seconds=seconds,
        costs={"food": food},
        power=number,
        requirements=requirements,
        costs_verified=True,
        verification_status="sourced",
    )


def _node(
    research_id: str,
    maximum: int,
    levels: dict[int, ObservedResearchLevel],
) -> ObservedResearchNode:
    return ObservedResearchNode(
        id=research_id,
        names={"en-US": research_id},
        max_level=maximum,
        row=0,
        column=0,
        levels=levels,
    )


def _planner(
    *nodes: ObservedResearchNode, category_id: str = "test"
) -> CatalogResearchPlanner:
    observation = ResearchTreeObservation(
        observation_id="test",
        category_id=category_id,
        titles={"en-US": "Test"},
        locale="en-US",
        source_type="test",
        verification_status="sourced",
        captured_on="2026-08-07",
        game_version="test",
        scope="test",
        notes="",
        nodes=nodes,
        edges=(),
    )
    return CatalogResearchPlanner((observation,))


def test_catalog_plan_recurses_and_deduplicates_shared_prerequisites() -> None:
    prerequisite = _node(
        "b",
        3,
        {number: _level(number) for number in range(1, 4)},
    )
    branch = _node(
        "c",
        1,
        {
            1: _level(
                1,
                requirements=(ObservedResearchRequirement("b", 3),),
            )
        },
    )
    target = _node(
        "a",
        1,
        {
            1: _level(
                1,
                requirements=(
                    ObservedResearchRequirement("b", 2),
                    ObservedResearchRequirement("c", 1),
                ),
            )
        },
    )
    state = PlayerState(research_levels={"b": 1})

    result = _planner(target, prerequisite, branch).create_plan(state, "a", 1)

    assert result.required_levels == {"a": 1, "b": 3, "c": 1}
    assert [(step.research_id, step.level) for step in result.steps] == [
        ("b", 2),
        ("b", 3),
        ("c", 1),
        ("a", 1),
    ]
    assert result.edges == {("b", "a"), ("b", "c"), ("c", "a")}
    assert result.total_base_seconds == 400
    assert result.total_costs == {"food": 40}
    assert result.resource_shortfalls == {"food": 40}


def test_catalog_plan_lists_all_lower_dependency_layers_first() -> None:
    deepest = _node("d", 1, {1: _level(1)})
    first_branch = _node(
        "c",
        1,
        {1: _level(1, requirements=(ObservedResearchRequirement("d", 1),))},
    )
    second_branch = _node("b", 1, {1: _level(1)})
    target = _node(
        "z",
        1,
        {
            1: _level(
                1,
                requirements=(
                    ObservedResearchRequirement("c", 1),
                    ObservedResearchRequirement("b", 1),
                ),
            )
        },
    )

    result = _planner(target, second_branch, first_branch, deepest).create_plan(
        PlayerState(), "z", 1
    )

    assert [(step.research_id, step.level) for step in result.steps] == [
        ("b", 1),
        ("d", 1),
        ("c", 1),
        ("z", 1),
    ]


def test_every_catalog_plan_lists_each_level_after_all_prerequisites() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    observations = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    planner = CatalogResearchPlanner(observations)

    for target in planner.nodes.values():
        if target.max_level is None:
            continue
        result = planner.create_plan(PlayerState(), target.id, target.max_level)
        completed: dict[str, int] = {}
        for step in result.steps:
            assert step.level == completed.get(step.research_id, 0) + 1, (
                target.id,
                step.research_id,
                step.level,
            )
            level_data = planner.nodes[step.research_id].level_data(step.level)
            if level_data is not None:
                for requirement in level_data.requirements:
                    assert completed.get(requirement.research_id, 0) >= requirement.level, (
                        target.id,
                        step.research_id,
                        step.level,
                        requirement.research_id,
                        requirement.level,
                    )
            completed[step.research_id] = step.level


def test_technolabe_efficiency_uses_original_time_and_sourced_count() -> None:
    assert TECHNOLABE_CAPACITY_SECONDS == 33 * 86_400 + 3 * 3_600 + 59 * 60
    base_time = 12 * 86_400
    count, efficiency = technolabe_usage(base_time, sourced_count=2)

    assert count == 2
    assert efficiency == pytest.approx(
        base_time / (2 * TECHNOLABE_CAPACITY_SECONDS) * 100
    )
    assert technolabe_usage(30 * 86_400) == (None, None)

    screenshot_count, screenshot_efficiency = technolabe_usage(
        5_427_900, sourced_count=6
    )
    assert screenshot_count == 6
    assert screenshot_efficiency == pytest.approx(31.57, abs=0.001)


def test_technolabe_recommendation_uses_player_threshold_boundary() -> None:
    assert is_technolabe_recommended(95.0) is True
    assert is_technolabe_recommended(94.9) is False
    assert is_technolabe_recommended(92.5, 92.5) is True
    assert is_technolabe_recommended(None, 0.0) is False


def test_catalog_plan_omits_satisfied_prerequisites_from_dependency_tree() -> None:
    prerequisite = _node("b", 1, {1: _level(1)})
    target = _node(
        "a",
        1,
        {
            1: _level(
                1,
                requirements=(ObservedResearchRequirement("b", 1),),
            )
        },
    )

    result = _planner(target, prerequisite).create_plan(
        PlayerState(research_levels={"b": 1}), "a", 1
    )

    assert result.required_levels == {"a": 1}
    assert result.edges == set()


def test_catalog_plan_matches_game_time_after_free_speedup_deduction() -> None:
    target = _node("fire_trebuchet_subsidy", 4, {4: _level(4, seconds=473_040)})
    state = PlayerState(
        settings=PlayerSettings(
            vip_level=11,
            research_speed_percent=214.84,
            research_speed_boost_percent=10.0,
        ),
        research_levels={"fire_trebuchet_subsidy": 3},
    )

    result = _planner(target).create_plan(state, "fire_trebuchet_subsidy", 4)

    assert len(result.steps) == 1
    assert result.steps[0].adjusted_time_seconds == 139_623
    assert result.total_adjusted_seconds == 139_623


def test_catalog_plan_matches_research_breakthrough_event_screenshot() -> None:
    target = _node(
        "military_cavalry_defense_i",
        8,
        {
            8: ObservedResearchLevel(
                level=8,
                academy_level=1,
                base_time_seconds=2_166_780,
                costs={"food": 1_228_207, "special": 10},
                power=178_101,
                requirements=(),
                costs_verified=True,
                verification_status="sourced",
            )
        },
    )
    state = PlayerState(
        settings=PlayerSettings(
            vip_level=11,
            research_speed_percent=285.68,
            event_research_discount_percent=30.0,
        ),
        research_levels={target.id: 7},
    )

    result = _planner(target, category_id="military").create_plan(
        state, target.id, 8
    )

    assert len(result.steps) == 1
    assert result.steps[0].base_time_seconds == 2_166_780
    assert result.steps[0].adjusted_time_seconds == 387_266
    assert result.steps[0].costs == {"food": 859_744, "special": 10}


def test_event_discount_does_not_change_other_research_categories() -> None:
    target = _node("monster_hunt_test", 1, {1: _level(1, seconds=100, food=100)})
    state = PlayerState(
        settings=PlayerSettings(event_research_discount_percent=30.0)
    )

    result = _planner(target, category_id="monster_hunt").create_plan(
        state, target.id, 1
    )

    assert result.steps[0].adjusted_time_seconds == 0
    assert result.steps[0].costs == {"food": 100}


def test_catalog_plan_marks_unknown_values_without_treating_them_as_zero() -> None:
    target = _node("a", 1, {})

    result = _planner(target).create_plan(PlayerState(), "a", 1)

    assert result.total_base_seconds == 0
    assert result.total_costs == {}
    assert result.unknown_time_steps == 1
    assert result.unknown_cost_steps == 1
    assert result.unknown_power_steps == 1
    assert result.steps[0].costs_verified is False
    assert [(issue.code, issue.research_id, issue.level) for issue in result.issues] == [
        ("missing_level_data", "a", 1)
    ]


def test_catalog_plan_rejects_cycles() -> None:
    first = _node(
        "a",
        1,
        {1: _level(1, requirements=(ObservedResearchRequirement("b", 1),))},
    )
    second = _node(
        "b",
        1,
        {1: _level(1, requirements=(ObservedResearchRequirement("a", 1),))},
    )

    with pytest.raises(ValueError, match="Cyclic prerequisite"):
        _planner(first, second).create_plan(PlayerState(), "a", 1)


def test_shortest_available_steps_only_lists_research_that_can_start_now() -> None:
    quick = _node("quick", 2, {1: _level(1, seconds=1_200)})
    slow = _node("slow", 1, {1: _level(1, seconds=1_800)})
    locked = _node(
        "locked",
        1,
        {
            1: _level(
                1,
                seconds=900,
                requirements=(ObservedResearchRequirement("quick", 1),),
            )
        },
    )
    academy_locked = _node(
        "academy_locked",
        1,
        {1: _level(1, seconds=700, academy=2)},
    )
    unknown = _node("unknown", 1, {1: _level(1, seconds=None)})
    completed = _node("completed", 1, {1: _level(1, seconds=600)})
    planner = _planner(
        quick,
        slow,
        locked,
        academy_locked,
        unknown,
        completed,
    )
    state = PlayerState(
        settings=PlayerSettings(vip_level=1, academy_level=1),
        research_levels={"completed": 1},
    )

    steps = planner.shortest_available_steps(state)

    assert [(step.research_id, step.level) for step in steps] == [
        ("quick", 1),
        ("slow", 1),
    ]
    assert [step.adjusted_time_seconds for step in steps] == [600, 1_200]

    state.research_levels["quick"] = 1
    unlocked = planner.shortest_available_steps(state)
    assert [(step.research_id, step.level) for step in unlocked] == [
        ("locked", 1),
        ("slow", 1),
    ]
