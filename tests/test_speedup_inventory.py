from rlm_research_planner.domain.models import (
    PaidItem,
    PaidOffer,
    SpeedupInventoryItem,
)
from rlm_research_planner.services.speedup_inventory import (
    SPEEDUP_DURATION_GROUPS,
    SPEEDUP_DURATION_SECONDS,
    add_paid_items_to_inventory,
    recommend_paid_offers,
    speedup_duration_group,
    speedup_coverage,
)


def test_speedup_inventory_uses_game_duration_presets() -> None:
    assert SPEEDUP_DURATION_SECONDS == (
        60,
        180,
        300,
        600,
        900,
        1800,
        3600,
        10800,
        28800,
        54000,
        86400,
        259200,
        604800,
        2592000,
    )
    assert SPEEDUP_DURATION_GROUPS == (
        ("minutes", (60, 180, 300, 600, 900, 1800, 3600)),
        ("hours", (10800, 28800, 54000, 86400)),
        ("days", (259200, 604800, 2592000)),
    )
    assert speedup_duration_group(3600) == "minutes"
    assert speedup_duration_group(3601) == "hours"
    assert speedup_duration_group(86401) == "days"


def test_research_uses_general_and_research_speedups_only() -> None:
    entries = [
        SpeedupInventoryItem("general", 3600, 2),
        SpeedupInventoryItem("research", 1800, 3),
        SpeedupInventoryItem("construction", 86400, 1),
    ]

    coverage = speedup_coverage(15_000, entries, "research")

    assert coverage.available_seconds == 12_600
    assert coverage.applied_seconds == 12_600
    assert coverage.remaining_seconds == 2_400
    assert coverage.surplus_seconds == 0


def test_construction_uses_general_and_construction_speedups_only() -> None:
    entries = [
        SpeedupInventoryItem("general", 3600, 1),
        SpeedupInventoryItem("construction", 1800, 2),
        SpeedupInventoryItem("research", 86400, 1),
    ]

    coverage = speedup_coverage(10_000, entries, "construction")

    assert coverage.available_seconds == 7200
    assert coverage.applied_seconds == 7200
    assert coverage.remaining_seconds == 2800


def test_speedups_never_overrun_an_individual_plan_step() -> None:
    entries = [
        SpeedupInventoryItem("general", 3 * 3600, 2),
        SpeedupInventoryItem("research", 20 * 60, 3),
        SpeedupInventoryItem("construction", 24 * 60, 99),
    ]

    coverage = speedup_coverage(
        3 * 3600 + 24 * 60,
        entries,
        "research",
        [24 * 60, 3 * 3600],
    )

    assert coverage.applied_seconds == 3 * 3600 + 20 * 60
    assert coverage.remaining_task_seconds == (4 * 60, 0)
    assert coverage.used_items == (
        SpeedupInventoryItem("general", 3 * 3600, 1),
        SpeedupInventoryItem("research", 20 * 60, 1),
    )


def test_speedup_allocation_chooses_the_best_fitting_combination() -> None:
    coverage = speedup_coverage(
        10 * 60,
        [
            SpeedupInventoryItem("research", 6 * 60, 1),
            SpeedupInventoryItem("research", 5 * 60, 2),
        ],
        "research",
        [10 * 60],
    )

    assert coverage.applied_seconds == 10 * 60
    assert coverage.remaining_seconds == 0
    assert coverage.used_items == (
        SpeedupInventoryItem("research", 5 * 60, 2),
    )


def test_paid_speedups_are_merged_into_inventory() -> None:
    result = add_paid_items_to_inventory(
        [SpeedupInventoryItem("general", 3600, 2)],
        [
            PaidItem("general", quantity=3, duration_seconds=3600),
            PaidItem("research", quantity=4, duration_seconds=1800),
            PaidItem("gems", quantity=100),
        ],
    )

    assert result == (
        SpeedupInventoryItem("general", 3600, 5),
        SpeedupInventoryItem("research", 1800, 4),
    )


def test_paid_offer_recommendation_repeats_offer_and_ranks_by_total_cost() -> None:
    offers = [
        PaidOffer(
            "expensive",
            "Expensive",
            diamond_cost=500,
            items=(PaidItem("research", quantity=1, duration_seconds=5400),),
        ),
        PaidOffer(
            "cheap",
            "Cheap",
            diamond_cost=100,
            items=(PaidItem("general", quantity=1, duration_seconds=3600),),
        ),
        PaidOffer(
            "wrong",
            "Construction only",
            diamond_cost=1,
            items=(PaidItem("construction", quantity=99, duration_seconds=3600),),
        ),
    ]

    result = recommend_paid_offers(10_800, offers, "research")

    assert [item.offer_id for item in result] == ["cheap", "expensive"]
    assert result[0].purchases == 3
    assert result[0].total_diamond_cost == 300
    assert result[1].purchases == 2


def test_paid_offer_recommendation_separates_speedups_gems_and_shortfall() -> None:
    offer = PaidOffer(
        "mixed",
        "Mixed pack",
        diamond_cost=999,
        included_gems=250,
        bonus_gems=50,
        items=(PaidItem("research", quantity=1, duration_seconds=3600),),
    )

    result = recommend_paid_offers(
        4 * 3600,
        [offer],
        "research",
        use_gems=True,
    )

    assert len(result) == 1
    assert result[0].purchases == 1
    assert result[0].applied_speedup_seconds == 3600
    assert result[0].available_gems == 300
    assert result[0].gems_used == 300
    assert result[0].gem_applied_seconds == 3 * 3600
    assert result[0].remaining_seconds == 0


def test_paid_offer_recommendation_accepts_gem_only_offer() -> None:
    result = recommend_paid_offers(
        3 * 3600,
        [PaidOffer("gems", "Gem pack", included_gems=300)],
        "research",
        use_gems=True,
    )

    assert result[0].applied_speedup_seconds == 0
    assert result[0].gems_used == 300
    assert result[0].gem_applied_seconds == 3 * 3600


def test_gem_only_offer_is_hidden_when_gem_usage_is_disabled() -> None:
    result = recommend_paid_offers(
        3 * 3600,
        [PaidOffer("gems", "Gem pack", included_gems=300)],
        "research",
    )

    assert result == ()


def test_partial_paid_offer_is_shown_with_its_remaining_time() -> None:
    result = recommend_paid_offers(
        6_300,
        [
            PaidOffer(
                "partial",
                "Partial pack",
                diamond_cost=100,
                items=(
                    PaidItem("research", quantity=1, duration_seconds=3_600),
                ),
            )
        ],
        "research",
        task_seconds=(5_400, 900),
    )

    assert len(result) == 1
    assert result[0].purchases == 1
    assert result[0].applied_speedup_seconds == 3_600
    assert result[0].remaining_seconds == 2_700


def test_impossible_exact_paid_offer_falls_back_without_huge_search() -> None:
    result = recommend_paid_offers(
        20_108,
        [
            PaidOffer(
                "five-minute",
                "Five-minute pack",
                diamond_cost=100,
                items=(
                    PaidItem("research", quantity=40, duration_seconds=300),
                ),
            )
        ],
        "research",
        task_seconds=(20_108,),
    )

    assert len(result) == 1
    assert result[0].purchases == 1
    assert result[0].applied_speedup_seconds == 12_000
    assert result[0].remaining_seconds == 8_108


def test_paid_offer_simulation_caps_unusable_repeated_quantities() -> None:
    tasks = (20_108,) * 220
    result = recommend_paid_offers(
        sum(tasks),
        [
            PaidOffer(
                "research-pack",
                "Research pack",
                diamond_cost=1_999,
                items=(
                    PaidItem("research", quantity=60, duration_seconds=86_400),
                    PaidItem("research", quantity=40, duration_seconds=28_800),
                    PaidItem("research", quantity=40, duration_seconds=300),
                ),
            )
        ],
        "research",
        task_seconds=tasks,
    )

    assert len(result) == 1
    assert result[0].purchases == 1
    assert result[0].remaining_seconds > 0
