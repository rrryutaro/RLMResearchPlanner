from __future__ import annotations

from dataclasses import replace

import pytest

from rlm_research_planner.domain.models import PlayerSettings, PlayerState, Prerequisite
from rlm_research_planner.services.planning import ResearchPlanner
from rlm_research_planner.services.validation import MasterDataValidator


def test_simple_prerequisite_path(planning_master) -> None:
    planner = ResearchPlanner(planning_master)
    result = planner.create_plan(PlayerState(), "econ_construction_speed", 1)
    assert [(step.research_id, step.level) for step in result.steps] == [
        ("econ_resource_production", 1),
        ("econ_construction_speed", 1),
    ]


def test_multiple_prerequisites_and_shared_dependency_are_deduplicated(planning_master) -> None:
    planner = ResearchPlanner(planning_master)
    result = planner.create_plan(PlayerState(), "mil_t3_unlock", 1)
    steps = [(step.research_id, step.level) for step in result.steps]
    assert steps.count(("econ_resource_production", 1)) == 1
    assert steps.count(("econ_research_speed", 1)) == 1
    assert ("mil_infantry_attack", 2) in steps
    assert ("mil_ranged_attack", 2) in steps
    assert ("mil_cavalry_attack", 2) in steps
    assert steps[-1] == ("mil_t3_unlock", 1)


def test_totals_match_steps(planning_master) -> None:
    state = PlayerState(settings=PlayerSettings(research_speed_percent=100, max_guild_helps=1))
    result = ResearchPlanner(planning_master).create_plan(state, "mil_t3_unlock", 1)
    assert result.total_power == sum(step.power for step in result.steps)
    assert result.total_ancient_tomes == sum(step.ancient_tomes for step in result.steps)
    for resource, total in result.total_resources.items():
        assert total == sum(step.resources[resource] for step in result.steps)
    assert result.total_after_help_seconds == sum(
        step.after_help_seconds for step in result.steps
    )


def test_unverified_data_adds_warnings(planning_master) -> None:
    result = ResearchPlanner(planning_master).create_plan(PlayerState(), "econ_resource_production", 1)
    assert any("unverified data" in warning for warning in result.warnings)


def test_current_level_at_or_above_target_has_no_steps(planning_master) -> None:
    state = PlayerState(research_levels={"econ_research_speed": 3})
    result = ResearchPlanner(planning_master).create_plan(state, "econ_research_speed", 2)
    assert result.steps == []


def test_cycle_is_detected_by_validator(planning_master) -> None:
    cyclic = replace(
        planning_master,
        prerequisites=planning_master.prerequisites
        + (
            Prerequisite(
                research_id="econ_resource_production",
                target_level=1,
                prerequisite_research_id="mil_t3_unlock",
                prerequisite_level=1,
            ),
        ),
    )
    issues = MasterDataValidator().validate(cyclic)
    assert any(issue.code == "cycle" for issue in issues)


def test_invalid_target_level_is_rejected(planning_master) -> None:
    with pytest.raises(ValueError):
        ResearchPlanner(planning_master).create_plan(PlayerState(), "mil_t3_unlock", 2)


def test_plan_reports_resource_and_speedup_shortfalls(planning_master) -> None:
    state = PlayerState(
        settings=PlayerSettings(
            academy_level=99,
            research_speed_percent=0,
            max_guild_helps=0,
            speedup_seconds=60,
            resources={
                "food": 0,
                "stone": 0,
                "timber": 0,
                "ore": 0,
                "gold": 0,
                "special": 0,
            },
        )
    )
    result = ResearchPlanner(planning_master).create_plan(
        state, "econ_resource_production", 1
    )
    assert result.speedup_shortfall_seconds == 540
    assert result.resource_shortfalls["food"] == 100
    assert result.timing_classification == "resource_shortage"


def test_plan_reports_academy_shortage_before_resource_shortage(planning_master) -> None:
    state = PlayerState(settings=PlayerSettings(academy_level=1))
    result = ResearchPlanner(planning_master).create_plan(
        state, "econ_construction_speed", 1
    )
    assert any("Academy level 2 required" in item for item in result.unmet_conditions)
    assert result.timing_classification == "prerequisite_shortage"


def test_plan_reports_help_savings_and_owned_speedup_coverage(planning_master) -> None:
    state = PlayerState(
        settings=PlayerSettings(
            academy_level=99,
            max_guild_helps=1,
            speedup_seconds=10_000,
            resources={
                "food": 10_000,
                "stone": 10_000,
                "timber": 10_000,
                "ore": 10_000,
                "gold": 10_000,
                "special": 10_000,
            },
        )
    )
    result = ResearchPlanner(planning_master).create_plan(
        state, "econ_resource_production", 1
    )
    assert result.help_reduction_seconds == 60
    assert result.speedup_shortfall_seconds == 0
    assert result.timing_classification == "help_then_speedups"
