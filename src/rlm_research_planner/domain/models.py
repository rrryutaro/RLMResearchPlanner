from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping


RESOURCE_KEYS = (
    "food",
    "stone",
    "timber",
    "ore",
    "gold",
    "special",
    "gold_hammer",
    "war_tome",
    "steel_cuffs",
    "soul_crystal",
)


@dataclass(frozen=True)
class ResearchCategory:
    id: str
    display_order: int
    requires_special_items: bool = False
    verification_status: str = "unverified"


@dataclass(frozen=True)
class Research:
    id: str
    category_id: str
    max_level: int
    display_order: int
    effect_type: str
    tags: tuple[str, ...] = ()
    purposes: tuple[str, ...] = ()
    recommendation: str = "unrated"
    verification_status: str = "unverified"


@dataclass(frozen=True)
class ResearchLevel:
    research_id: str
    level: int
    academy_level: int
    base_time_seconds: int
    resources: Mapping[str, int]
    ancient_tomes: int
    power: int
    effect_value: float
    cumulative_effect: float
    source: str
    checked_on: str
    game_version: str
    verification_status: str
    notes: str = ""


@dataclass(frozen=True)
class Prerequisite:
    research_id: str
    target_level: int
    prerequisite_research_id: str | None = None
    prerequisite_level: int = 0
    building: str | None = None
    building_level: int = 0
    other_condition: str | None = None


@dataclass(frozen=True)
class LocalizedCategory:
    name: str
    description: str = ""


@dataclass(frozen=True)
class LocalizedResearch:
    name: str
    description: str = ""
    effect_label: str = ""
    recommendation_reason: str = ""


@dataclass(frozen=True)
class LocaleData:
    categories: Mapping[str, LocalizedCategory]
    research: Mapping[str, LocalizedResearch]


@dataclass(frozen=True)
class MasterData:
    dataset_id: str
    dataset_status: str
    game_version: str
    categories: tuple[ResearchCategory, ...]
    research: tuple[Research, ...]
    levels: tuple[ResearchLevel, ...]
    prerequisites: tuple[Prerequisite, ...]
    locales: Mapping[str, LocaleData]

    def research_by_id(self) -> dict[str, Research]:
        return {item.id: item for item in self.research}

    def levels_by_research(self, research_id: str) -> tuple[ResearchLevel, ...]:
        return tuple(
            sorted(
                (item for item in self.levels if item.research_id == research_id),
                key=lambda item: item.level,
            )
        )

    def level(self, research_id: str, level: int) -> ResearchLevel:
        for item in self.levels:
            if item.research_id == research_id and item.level == level:
                return item
        raise KeyError((research_id, level))

    def localized_research(self, research_id: str, locale: str) -> LocalizedResearch:
        for candidate in locale_fallbacks(locale):
            locale_data = self.locales.get(candidate)
            if locale_data and research_id in locale_data.research:
                return locale_data.research[research_id]
        return LocalizedResearch(name=research_id)

    def localized_category(self, category_id: str, locale: str) -> LocalizedCategory:
        for candidate in locale_fallbacks(locale):
            locale_data = self.locales.get(candidate)
            if locale_data and category_id in locale_data.categories:
                return locale_data.categories[category_id]
        return LocalizedCategory(name=category_id)


def locale_fallbacks(locale: str) -> tuple[str, ...]:
    normalized = locale.replace("_", "-")
    language = normalized.split("-", 1)[0]
    candidates = [normalized]
    if language == "ja":
        candidates.extend(("ja-JP", "en-US"))
    else:
        candidates.extend((language, "en-US", "ja-JP"))
    return tuple(dict.fromkeys(candidates))


@dataclass
class PlayerSettings:
    vip_level: int = 1
    castle_level: int = 1
    castle_target_level: int = 0
    castle_mana_stage: int = 0
    castle_target_mana_stage: int = 0
    academy_level: int = 1
    construction_speed_percent: float = 0.0
    construction_speed_boost_percent: float = 0.0
    research_speed_percent: float = 0.0
    research_speed_boost_percent: float = 0.0
    max_guild_helps: int = 0
    speedup_seconds: int = 0
    speedup_inventory: list[SpeedupInventoryItem] = field(default_factory=list)
    use_gems_for_speedups: bool = False
    technolabe_count: int = 0
    technolabe_recommendation_threshold_percent: float = 95.0
    resource_display_mode: str = "exact"
    resources: dict[str, int] = field(
        default_factory=lambda: {key: 0 for key in RESOURCE_KEYS}
    )

    @property
    def effective_construction_speed_percent(self) -> float:
        return max(0.0, float(self.construction_speed_percent)) + max(
            0.0, float(self.construction_speed_boost_percent)
        )

    @property
    def effective_research_speed_percent(self) -> float:
        return max(0.0, float(self.research_speed_percent)) + max(
            0.0, float(self.research_speed_boost_percent)
        )


MAX_GUILD_HELPS = 30


def max_guild_helps_for_castle(castle_level: int) -> int:
    """Return the in-game guild-help limit for a normal Castle level."""

    normalized_level = max(1, min(25, int(castle_level)))
    return min(MAX_GUILD_HELPS, normalized_level + 5)


@dataclass(frozen=True)
class ResearchPlanTask:
    research_id: str
    target_level: int
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_name: str = ""


@dataclass(frozen=True)
class TalentPlanStep:
    talent_id: str
    target_level: int


@dataclass(frozen=True)
class SpeedupInventoryItem:
    kind: str
    duration_seconds: int
    quantity: int


@dataclass(frozen=True)
class PaidItem:
    kind: str
    name: str = ""
    quantity: int = 0
    duration_seconds: int = 0
    gem_value_each: float = 0.0
    points_each: float = 0.0


@dataclass(frozen=True)
class PaidOffer:
    offer_id: str
    title: str
    goal: str = "all_round"
    memo: str = ""
    diamond_cost: int = 0
    included_gems: int = 0
    bonus_gems: int = 0
    items: tuple[PaidItem, ...] = ()
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class PaidValuation:
    points_per_gem: float = 1.0
    general_speedup_points_per_hour: float = 0.0
    research_speedup_points_per_hour: float = 0.0
    training_speedup_points_per_hour: float = 0.0
    construction_speedup_points_per_hour: float = 0.0
    healing_speedup_points_per_hour: float = 0.0
    merging_speedup_points_per_hour: float = 0.0
    crafting_speedup_points_per_hour: float = 0.0
    use_speedup_gem_presets: bool = True


@dataclass
class PlayerState:
    settings: PlayerSettings = field(default_factory=PlayerSettings)
    research_levels: dict[str, int] = field(default_factory=dict)
    building_levels: dict[str, int] = field(default_factory=dict)
    plan_tasks: list[ResearchPlanTask] = field(default_factory=list)
    talent_plan_name: str = ""
    talent_preset_id: str = "growth_speed"
    talent_priority_id: str = ""
    talent_available_points: int = 278
    talent_plan: list[TalentPlanStep] = field(default_factory=list)
    paid_offers: list[PaidOffer] = field(default_factory=list)
    paid_valuation: PaidValuation = field(default_factory=PaidValuation)
    observed_stats: dict[str, str] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
