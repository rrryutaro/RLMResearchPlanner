from __future__ import annotations

from rlm_research_planner.domain.models import (
    PaidItem,
    PaidOffer,
    PaidValuation,
    PlayerSettings,
    PlayerState,
    ResearchPlanTask,
    SpeedupInventoryItem,
    TalentPlanStep,
)
from rlm_research_planner.repositories.player_repository import PlayerRepository


def test_player_state_round_trip_in_memory() -> None:
    repository = PlayerRepository(":memory:")
    try:
        state = PlayerState(
            settings=PlayerSettings(
                player_level=42,
                vip_level=11,
                castle_level=25,
                academy_level=24,
                research_speed_percent=123.45,
                research_speed_boost_percent=10.0,
                max_guild_helps=30,
                speedup_seconds=3600,
                technolabe_count=17,
                technolabe_recommendation_threshold_percent=92.5,
                resource_display_mode="short",
                resources={
                    "food": 10,
                    "stone": 20,
                    "timber": 30,
                    "ore": 40,
                    "gold": 50,
                    "special": 60,
                },
            ),
            research_levels={"econ_research_speed": 2},
            plan_tasks=[
                ResearchPlanTask(
                    "econ_research_speed", 3, "test-date", "共有研究計画"
                )
            ],
            talent_plan_name="研究・建設用",
            talent_preset_id="growth_speed",
            talent_priority_id="research_i",
            talent_available_points=278,
            talent_plan=[
                TalentPlanStep("food_production_i", 2),
                TalentPlanStep("construction_speed_i", 10),
            ],
            observed_stats={"研究速度": "+167.84%"},
        )
        repository.save(state)
        loaded = repository.load()
        assert loaded.settings.castle_level == 25
        assert loaded.settings.player_level == 42
        assert loaded.settings.research_speed_percent == 123.45
        assert loaded.settings.research_speed_boost_percent == 10.0
        assert loaded.settings.effective_research_speed_percent == 133.45
        assert loaded.settings.vip_level == 11
        assert loaded.research_levels == {"econ_research_speed": 2}
        assert loaded.observed_stats == {"研究速度": "+167.84%"}
        assert loaded.settings.resources["special"] == 60
        assert loaded.settings.resource_display_mode == "short"
        assert loaded.settings.technolabe_recommendation_threshold_percent == 92.5
        assert loaded.settings.technolabe_count == 17
        assert loaded.settings.speedup_inventory == [
            SpeedupInventoryItem("general", 1, 3600)
        ]
        assert loaded.plan_tasks == [
            ResearchPlanTask(
                "econ_research_speed", 3, "test-date", "共有研究計画"
            )
        ]
        assert loaded.talent_plan_name == "研究・建設用"
        assert loaded.talent_available_points == 278
        assert loaded.talent_priority_id == "research_i"
        assert loaded.talent_plan == state.talent_plan
    finally:
        repository.close()


def test_json_backup_payload_round_trip_without_filesystem() -> None:
    repository = PlayerRepository(":memory:")
    try:
        state = PlayerState(
            settings=PlayerSettings(
                player_level=37,
                speedup_inventory=[
                    SpeedupInventoryItem("general", 3600, 2),
                    SpeedupInventoryItem("research", 1800, 4),
                ],
                use_gems_for_speedups=True,
                technolabe_count=23,
                technolabe_recommendation_threshold_percent=97.5,
            ),
            research_levels={"mil_infantry_attack": 1},
            plan_tasks=[
                ResearchPlanTask(
                    "mil_infantry_attack", 2, "test-date", "共有研究計画"
                )
            ],
            talent_plan_name="共有才能",
            talent_preset_id="custom",
            talent_priority_id="squad_offense_i",
            talent_available_points=300,
            talent_plan=[TalentPlanStep("squad_offense_i", 5)],
            observed_stats={"建設速度": "+299.75%"},
        )
        raw = repository.backup_payload(state)
        assert raw["schema_version"] == 1
        assert "play_style" not in raw["player"]["settings"]
        assert raw["player"]["settings"]["player_level"] == 37
        assert raw["player"]["settings"]["speedup_inventory"] == [
            {"kind": "general", "duration_seconds": 3600, "quantity": 2},
            {"kind": "research", "duration_seconds": 1800, "quantity": 4},
        ]
        assert raw["player"]["plan_tasks"][0]["source_name"] == "共有研究計画"
        assert raw["player"]["talent_plan"][0] == {
            "talent_id": "squad_offense_i",
            "target_level": 5,
        }
        restored = repository.restore_payload(raw)
        assert restored.research_levels == {"mil_infantry_attack": 1}
        assert restored.settings.player_level == 37
        assert restored.settings.speedup_inventory == state.settings.speedup_inventory
        assert restored.settings.use_gems_for_speedups is True
        assert restored.settings.technolabe_recommendation_threshold_percent == 97.5
        assert restored.settings.technolabe_count == 23
        assert restored.observed_stats == {"建設速度": "+299.75%"}
        assert restored.plan_tasks == [
            ResearchPlanTask(
                "mil_infantry_attack", 2, "test-date", "共有研究計画"
            )
        ]
        assert restored.talent_plan_name == "共有才能"
        assert restored.talent_available_points == 300
        assert restored.talent_priority_id == "squad_offense_i"
        assert restored.talent_plan == state.talent_plan
    finally:
        repository.close()


def test_legacy_backup_free_time_is_migrated_to_vip_level() -> None:
    repository = PlayerRepository(":memory:")
    try:
        raw = repository.backup_payload(
            PlayerState(settings=PlayerSettings(vip_level=11))
        )
        settings = raw["player"]["settings"]
        settings.pop("vip_level")
        settings.pop("research_speed_boost_percent")

        restored = repository.restore_payload(raw)

        assert restored.settings.vip_level == 11
        assert restored.settings.research_speed_boost_percent == 0.0
    finally:
        repository.close()


def test_guild_help_count_is_limited_by_castle_level() -> None:
    repository = PlayerRepository(":memory:")
    try:
        raw = repository.backup_payload(
            PlayerState(
                settings=PlayerSettings(castle_level=20, max_guild_helps=99)
            )
        )
        assert raw["player"]["settings"]["max_guild_helps"] == 25

        raw["player"]["settings"]["max_guild_helps"] = 99
        restored = repository.restore_payload(raw)

        assert restored.settings.castle_level == 20
        assert restored.settings.max_guild_helps == 25
    finally:
        repository.close()


def test_paid_offers_and_valuation_survive_save_and_backup() -> None:
    repository = PlayerRepository(":memory:")
    try:
        state = PlayerState(
            paid_offers=[
                PaidOffer(
                    offer_id="pack-1",
                    title="素材パック",
                    memo="比較用",
                    diamond_cost=999,
                    included_gems=3600,
                    items=(
                        PaidItem(
                            kind="monster_legendary",
                            name="伝説素材",
                            quantity=2,
                            gem_value_each=1200,
                            points_each=100,
                        ),
                    ),
                    created_at="created",
                    updated_at="updated",
                )
            ],
            paid_valuation=PaidValuation(
                points_per_gem=2,
                research_speedup_points_per_hour=5,
                healing_speedup_points_per_hour=3,
                merging_speedup_points_per_hour=4,
                crafting_speedup_points_per_hour=6,
            ),
        )
        repository.save(state)
        loaded = repository.load()
        assert loaded.paid_offers == state.paid_offers
        assert loaded.paid_valuation == state.paid_valuation

        restored = repository.restore_payload(repository.backup_payload(state))
        assert restored.paid_offers == state.paid_offers
        assert restored.paid_valuation == state.paid_valuation
    finally:
        repository.close()
