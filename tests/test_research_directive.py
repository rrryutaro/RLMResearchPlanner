from __future__ import annotations

from pathlib import Path

from rlm_research_planner.domain.models import (
    PlayerState,
    ResearchPlanTask,
)
from rlm_research_planner.paths import AppPaths
from rlm_research_planner.repositories.catalog_repository import (
    JsonResearchCatalogRepository,
)
from rlm_research_planner.services.catalog_planning import CatalogResearchPlanner
from rlm_research_planner.services.research_directive import (
    RESEARCH_DIRECTIVE_DOCUMENT_TYPE,
    merge_research_directive_tasks,
    research_directive_from_payload,
    research_directive_payload,
)


def test_pwa_compatible_directive_contains_tasks_only_and_round_trips() -> None:
    payload = research_directive_payload(
        [
            ResearchPlanTask("military_heroic_fighter", 1),
            ResearchPlanTask("upgrade_military_heroic_fighter_subsidy", 7),
            ResearchPlanTask("upgrade_military_heroic_fighter_subsidy", 10),
        ],
        name="レジェンドファイター研究計画",
        dataset_id="test-dataset",
        game_version="v2.200.309",
    )

    assert payload["document_type"] == RESEARCH_DIRECTIVE_DOCUMENT_TYPE
    assert payload["tasks"] == [
        {"research_id": "military_heroic_fighter", "target_level": 1},
        {
            "research_id": "upgrade_military_heroic_fighter_subsidy",
            "target_level": 10,
        },
    ]
    for private_key in (
        "player",
        "settings",
        "research_levels",
        "building_levels",
        "resources",
    ):
        assert private_key not in payload

    directive = research_directive_from_payload(payload)
    assert directive.name == "レジェンドファイター研究計画"
    assert directive.dataset_id == "test-dataset"
    assert directive.game_version == "v2.200.309"
    assert [(task.research_id, task.target_level) for task in directive.tasks] == [
        ("military_heroic_fighter", 1),
        ("upgrade_military_heroic_fighter_subsidy", 10),
    ]


def test_directive_merge_changes_only_tasks_and_uses_the_higher_target() -> None:
    state = PlayerState(
        research_levels={"economy_construction_speed": 7},
        building_levels={"academy": 24},
        plan_tasks=[
            ResearchPlanTask(
                "economy_construction_speed", 8, "existing", ""
            )
        ],
    )
    state.settings.vip_level = 11
    state.settings.research_speed_percent = 228
    state.settings.resources["food"] = 1_234_567
    preserved_settings = state.settings
    preserved_levels = dict(state.research_levels)
    preserved_buildings = dict(state.building_levels)

    merged = merge_research_directive_tasks(
        state.plan_tasks,
        [
            ResearchPlanTask("economy_construction_speed", 10),
            ResearchPlanTask("military_heroic_fighter", 1),
        ],
        source_name="共有研究計画",
        created_at="imported",
    )
    state.plan_tasks = list(merged.tasks)

    assert merged.added == 1
    assert merged.updated == 1
    assert merged.unchanged == 0
    assert state.plan_tasks == [
        ResearchPlanTask(
            "economy_construction_speed", 10, "existing", "共有研究計画"
        ),
        ResearchPlanTask(
            "military_heroic_fighter", 1, "imported", "共有研究計画"
        ),
    ]
    assert state.settings is preserved_settings
    assert state.research_levels == preserved_levels
    assert state.building_levels == preserved_buildings


def test_directive_target_is_complete_or_recalculated_from_current_levels() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    observations = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    planner = CatalogResearchPlanner(observations)
    target_id = "military_heroic_fighter"

    full_plan = planner.create_plan(PlayerState(), target_id, 1)
    assert len(full_plan.steps) > 1

    first_step = full_plan.steps[0]
    partial_state = PlayerState(
        research_levels={first_step.research_id: first_step.level}
    )
    remaining_plan = planner.create_plan(partial_state, target_id, 1)
    assert len(remaining_plan.steps) < len(full_plan.steps)
    assert not any(
        step.research_id == first_step.research_id
        and step.level <= first_step.level
        for step in remaining_plan.steps
    )

    completed_levels: dict[str, int] = {}
    for step in full_plan.steps:
        completed_levels[step.research_id] = max(
            completed_levels.get(step.research_id, 0), step.level
        )
    completed_plan = planner.create_plan(
        PlayerState(research_levels=completed_levels), target_id, 1
    )
    assert completed_plan.steps == []
    assert completed_plan.total_adjusted_seconds == 0
