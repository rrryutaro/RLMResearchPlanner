from rlm_research_planner.domain.models import PaidItem, PaidOffer, PaidValuation
from rlm_research_planner.services.paid_value import (
    default_points_each,
    minimum_gems_for_speedup_seconds,
    paid_kind_has_time,
    sorted_paid_offers,
    summarize_paid_offer,
)


def test_minimum_gems_use_standard_speedup_shop_combinations() -> None:
    assert minimum_gems_for_speedup_seconds(0).gems == 0
    assert minimum_gems_for_speedup_seconds(3 * 3600).gems == 300
    twenty_three_hours = minimum_gems_for_speedup_seconds(23 * 3600)
    assert twenty_three_hours.gems == 1_500
    assert twenty_three_hours.purchased_seconds == 24 * 3600


def test_paid_offer_summary_combines_time_gems_and_manual_items() -> None:
    offer = PaidOffer(
        offer_id="offer-1",
        title="Test pack",
        diamond_cost=100,
        included_gems=50,
        bonus_gems=50,
        items=(
            PaidItem(kind="general", quantity=2, duration_seconds=3600),
            PaidItem(kind="monster_rare", quantity=2, points_each=10),
            PaidItem(kind="chest", quantity=3, gem_value_each=5, points_each=2),
        ),
    )
    valuation = PaidValuation(
        points_per_gem=1,
        general_speedup_points_per_hour=4,
    )
    summary = summarize_paid_offer(offer, valuation)
    assert summary.speedup_seconds["general"] == 7200
    assert summary.speedup_gem_value == 260
    assert summary.total_gem_value == 375
    assert summary.direct_item_points == 26
    assert summary.speedup_points == 8
    assert summary.total_points == 409
    assert summary.points_per_diamond == 4.09


def test_paid_item_defaults_are_explicitly_editable_comparison_values() -> None:
    assert paid_kind_has_time("construction") is True
    assert paid_kind_has_time("healing") is True
    assert paid_kind_has_time("merging") is True
    assert paid_kind_has_time("crafting") is True
    assert paid_kind_has_time("monster_legendary") is False
    assert default_points_each("monster_common") == 1
    assert default_points_each("monster_uncommon") == 4
    assert default_points_each("monster_legendary") == 256


def test_speedup_gem_presets_distinguish_merging_and_crafting() -> None:
    offer = PaidOffer(
        offer_id="speedups",
        title="Special speed-ups",
        items=(
            PaidItem(kind="healing", quantity=1, duration_seconds=3600),
            PaidItem(kind="merging", quantity=1, duration_seconds=3600),
            PaidItem(kind="crafting", quantity=1, duration_seconds=3600),
        ),
    )
    summary = summarize_paid_offer(offer, PaidValuation())
    assert summary.speedup_gem_value == 390


def test_paid_offers_sort_by_points_per_diamond() -> None:
    valuation = PaidValuation()
    low = PaidOffer(offer_id="low", title="Low", diamond_cost=100, included_gems=100)
    high = PaidOffer(offer_id="high", title="High", diamond_cost=100, included_gems=200)
    assert [offer.offer_id for offer in sorted_paid_offers((low, high), valuation)] == ["high", "low"]
