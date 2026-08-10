from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from rlm_research_planner.domain.models import PaidItem, PaidOffer, PaidValuation


SPEEDUP_ITEM_KINDS = (
    "general",
    "research",
    "training",
    "construction",
    "healing",
    "merging",
    "crafting",
)
PAID_GOALS = (
    "all_round",
    "account_growth",
    "research",
    "construction",
    "troop_training",
    "combat",
    "monster_hunt",
    "equipment",
    "familiar",
    "artifact",
    "heroes",
    "events",
    "resources",
)
PAID_ITEM_KINDS = SPEEDUP_ITEM_KINDS + (
    "gems",
    "monster_common",
    "monster_uncommon",
    "monster_rare",
    "monster_epic",
    "monster_legendary",
    "chest",
    "resource",
    "material",
    "combat_item",
    "boost_item",
    "building_material",
    "familiar_item",
    "monster_energy",
    "hero_item",
    "artifact_item",
    "event_item",
    "currency",
    "custom",
)
DEFAULT_POINTS_EACH = {
    "monster_common": 1.0,
    "monster_uncommon": 4.0,
    "monster_rare": 16.0,
    "monster_epic": 64.0,
    "monster_legendary": 256.0,
}
SPEEDUP_GEM_VALUE_BY_SECONDS = {
    60: 5.0,
    15 * 60: 70.0,
    60 * 60: 130.0,
    3 * 60 * 60: 300.0,
    8 * 60 * 60: 650.0,
    15 * 60 * 60: 1_000.0,
    24 * 60 * 60: 1_500.0,
    3 * 24 * 60 * 60: 4_400.0,
    7 * 24 * 60 * 60: 10_000.0,
    30 * 24 * 60 * 60: 40_000.0,
}
MERGING_SPEEDUP_GEM_VALUE_BY_SECONDS = {
    15 * 60: 140.0,
    60 * 60: 260.0,
    3 * 60 * 60: 600.0,
    8 * 60 * 60: 1_300.0,
    15 * 60 * 60: 2_000.0,
    24 * 60 * 60: 3_000.0,
    3 * 24 * 60 * 60: 8_800.0,
    7 * 24 * 60 * 60: 20_000.0,
}


@dataclass(frozen=True)
class PaidOfferSummary:
    speedup_seconds: dict[str, int]
    total_speedup_seconds: int
    included_gems: int
    item_gem_value: float
    speedup_gem_value: float
    total_gem_value: float
    direct_item_points: float
    speedup_points: float
    total_points: float
    points_per_diamond: float | None
    gems_per_diamond: float | None


def paid_kind_has_time(kind: str) -> bool:
    return kind in SPEEDUP_ITEM_KINDS


def default_points_each(kind: str) -> float:
    return float(DEFAULT_POINTS_EACH.get(kind, 0.0))


def default_gem_value_each(kind: str) -> float:
    return 1.0 if kind == "gems" else 0.0


def speedup_gem_value_each(kind: str, duration_seconds: int) -> float:
    duration = max(0, int(duration_seconds))
    if kind == "merging":
        return MERGING_SPEEDUP_GEM_VALUE_BY_SECONDS.get(duration, 0.0)
    if kind == "crafting":
        return 0.0
    return SPEEDUP_GEM_VALUE_BY_SECONDS.get(duration, 0.0)


def _speedup_rate(valuation: PaidValuation, kind: str) -> float:
    return max(
        0.0,
        float(
            {
                "general": valuation.general_speedup_points_per_hour,
                "research": valuation.research_speedup_points_per_hour,
                "training": valuation.training_speedup_points_per_hour,
                "construction": valuation.construction_speedup_points_per_hour,
                "healing": valuation.healing_speedup_points_per_hour,
                "merging": valuation.merging_speedup_points_per_hour,
                "crafting": valuation.crafting_speedup_points_per_hour,
            }.get(kind, 0.0)
        ),
    )


def summarize_paid_offer(
    offer: PaidOffer,
    valuation: PaidValuation,
) -> PaidOfferSummary:
    speedup_seconds = {kind: 0 for kind in SPEEDUP_ITEM_KINDS}
    item_gem_value = 0.0
    speedup_gem_value = 0.0
    direct_item_points = 0.0
    for item in offer.items:
        quantity = max(0, int(item.quantity))
        if item.kind in speedup_seconds:
            speedup_seconds[item.kind] += max(0, int(item.duration_seconds)) * quantity
            if valuation.use_speedup_gem_presets and item.gem_value_each <= 0:
                speedup_gem_value += (
                    speedup_gem_value_each(item.kind, item.duration_seconds)
                    * quantity
                )
        item_gem_value += max(0.0, float(item.gem_value_each)) * quantity
        direct_item_points += max(0.0, float(item.points_each)) * quantity
    included_gems = max(0, int(offer.included_gems)) + max(
        0, int(offer.bonus_gems)
    )
    total_gem_value = included_gems + item_gem_value + speedup_gem_value
    speedup_points = sum(
        seconds / 3600.0 * _speedup_rate(valuation, kind)
        for kind, seconds in speedup_seconds.items()
    )
    total_points = (
        total_gem_value * max(0.0, float(valuation.points_per_gem))
        + direct_item_points
        + speedup_points
    )
    cost = max(0, int(offer.diamond_cost))
    return PaidOfferSummary(
        speedup_seconds=speedup_seconds,
        total_speedup_seconds=sum(speedup_seconds.values()),
        included_gems=included_gems,
        item_gem_value=item_gem_value,
        speedup_gem_value=speedup_gem_value,
        total_gem_value=total_gem_value,
        direct_item_points=direct_item_points,
        speedup_points=speedup_points,
        total_points=total_points,
        points_per_diamond=total_points / cost if cost else None,
        gems_per_diamond=total_gem_value / cost if cost else None,
    )


def sorted_paid_offers(
    offers: Iterable[PaidOffer],
    valuation: PaidValuation,
) -> tuple[PaidOffer, ...]:
    return tuple(
        sorted(
            offers,
            key=lambda offer: (
                -(
                    summarize_paid_offer(offer, valuation).points_per_diamond
                    or 0.0
                ),
                -summarize_paid_offer(offer, valuation).total_points,
                offer.title.casefold(),
            ),
        )
    )
