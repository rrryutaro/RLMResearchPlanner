import pytest

from rlm_research_planner.domain.models import PaidItem, PaidOffer, PaidValuation
from rlm_research_planner.services.paid_offer_exchange import (
    PaidOfferExchangeError,
    paid_offer_exchange_payload,
    paid_offers_from_exchange_payload,
)


def test_paid_offer_exchange_round_trip_keeps_goal_items_and_rates() -> None:
    offer = PaidOffer(
        offer_id="pack-1",
        title="研究パック",
        goal="research",
        memo="共有用",
        diamond_cost=999,
        items=(PaidItem(kind="research", quantity=10, duration_seconds=3600),),
    )
    valuation = PaidValuation(
        points_per_gem=2,
        merging_speedup_points_per_hour=3,
        crafting_speedup_points_per_hour=4,
        use_speedup_gem_presets=False,
    )

    restored, rates, name = paid_offers_from_exchange_payload(
        paid_offer_exchange_payload([offer], valuation, name="研究向け")
    )

    assert restored == (offer,)
    assert rates == valuation
    assert name == "研究向け"


def test_paid_offer_exchange_rejects_a_full_player_backup() -> None:
    with pytest.raises(PaidOfferExchangeError):
        paid_offers_from_exchange_payload({"schema_version": 1, "player": {}})


def test_paid_offer_exchange_accepts_comparison_settings_only() -> None:
    valuation = PaidValuation(points_per_gem=2.5)

    restored, rates, name = paid_offers_from_exchange_payload(
        paid_offer_exchange_payload([], valuation, name="比較設定")
    )

    assert restored == ()
    assert rates == valuation
    assert name == "比較設定"
