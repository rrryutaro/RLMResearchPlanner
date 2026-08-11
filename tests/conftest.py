from __future__ import annotations

from pathlib import Path

import pytest

from rlm_research_planner.domain.models import (
    LocaleData,
    LocalizedCategory,
    LocalizedResearch,
    MasterData,
    Prerequisite,
    Research,
    ResearchCategory,
    ResearchLevel,
)
from rlm_research_planner.repositories.master_repository import JsonMasterRepository


@pytest.fixture()
def master():
    data_directory = Path(__file__).resolve().parents[1] / "data" / "research"
    return JsonMasterRepository(data_directory).load()


@pytest.fixture()
def planning_master():
    """Synthetic planner-only fixture; production data intentionally stays empty."""

    research_specs = (
        ("econ_resource_production", "economy", 1),
        ("econ_construction_speed", "economy", 1),
        ("econ_research_speed", "economy", 3),
        ("mil_infantry_attack", "military", 2),
        ("mil_ranged_attack", "military", 2),
        ("mil_cavalry_attack", "military", 2),
        ("mil_t3_unlock", "military", 1),
    )
    research = tuple(
        Research(
            id=research_id,
            category_id=category_id,
            max_level=maximum,
            display_order=index,
            effect_type="test",
            verification_status="unverified",
        )
        for index, (research_id, category_id, maximum) in enumerate(research_specs)
    )
    levels = []
    for research_id, _category_id, maximum in research_specs:
        for level in range(1, maximum + 1):
            levels.append(
                ResearchLevel(
                    research_id=research_id,
                    level=level,
                    academy_level=(
                        2 if research_id == "econ_construction_speed" else 1
                    ),
                    base_time_seconds=(
                        1_200
                        if research_id == "econ_resource_production"
                        else 120
                    ),
                    resources={
                        "food": (
                            100 if research_id == "econ_resource_production" else 0
                        ),
                        "stone": 0,
                        "timber": 0,
                        "ore": 0,
                        "gold": 0,
                        "special": 0,
                    },
                    ancient_tomes=0,
                    power=level * 10,
                    effect_value=float(level),
                    cumulative_effect=float(level),
                    source="test fixture",
                    checked_on="2026-08-06",
                    game_version="test",
                    verification_status="unverified",
                )
            )
    prerequisites = (
        Prerequisite(
            "econ_construction_speed", 1, "econ_resource_production", 1
        ),
        Prerequisite(
            "econ_construction_speed", 1, building="Academy", building_level=2
        ),
        Prerequisite("econ_research_speed", 1, "econ_resource_production", 1),
        Prerequisite("mil_infantry_attack", 1, "econ_research_speed", 1),
        Prerequisite("mil_ranged_attack", 1, "econ_research_speed", 1),
        Prerequisite("mil_cavalry_attack", 1, "econ_research_speed", 1),
        Prerequisite("mil_t3_unlock", 1, "mil_infantry_attack", 2),
        Prerequisite("mil_t3_unlock", 1, "mil_ranged_attack", 2),
        Prerequisite("mil_t3_unlock", 1, "mil_cavalry_attack", 2),
    )
    localized = {
        research_id: LocalizedResearch(name=research_id, effect_label="Effect")
        for research_id, _category_id, _maximum in research_specs
    }
    return MasterData(
        dataset_id="planner-test-fixture",
        dataset_status="test_only",
        game_version="test",
        categories=(
            ResearchCategory("economy", 0),
            ResearchCategory("military", 1),
        ),
        research=research,
        levels=tuple(levels),
        prerequisites=prerequisites,
        locales={
            "en-US": LocaleData(
                categories={
                    "economy": LocalizedCategory("Economy"),
                    "military": LocalizedCategory("Military"),
                },
                research=localized,
            )
        },
    )
