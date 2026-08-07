from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping


RESOURCE_KEYS = ("food", "stone", "timber", "ore", "gold", "special")


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
    castle_level: int = 1
    academy_level: int = 1
    research_speed_percent: float = 0.0
    free_speedup_seconds: int = 0
    max_guild_helps: int = 0
    speedup_seconds: int = 0
    resources: dict[str, int] = field(
        default_factory=lambda: {key: 0 for key in RESOURCE_KEYS}
    )


@dataclass
class PlayerState:
    settings: PlayerSettings = field(default_factory=PlayerSettings)
    research_levels: dict[str, int] = field(default_factory=dict)
    observed_stats: dict[str, str] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
