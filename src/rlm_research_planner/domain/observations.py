from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from rlm_research_planner.domain.models import locale_fallbacks


@dataclass(frozen=True)
class ObservedResearchRequirement:
    research_id: str
    level: int


@dataclass(frozen=True)
class ObservedResearchLevel:
    level: int
    academy_level: int | None = None
    base_time_seconds: int | None = None
    costs: Mapping[str, int] = field(default_factory=dict)
    power: int | None = None
    requirements: tuple[ObservedResearchRequirement, ...] = ()
    building_requirements: Mapping[str, int] = field(default_factory=dict)
    costs_verified: bool = False
    verification_status: str = "unverified"


@dataclass(frozen=True)
class ObservedResearchNode:
    id: str
    names: Mapping[str, str]
    max_level: int | None
    row: int
    column: int
    effect_label: str = ""
    effect_values: Mapping[int, str] = field(default_factory=dict)
    levels: Mapping[int, ObservedResearchLevel] = field(default_factory=dict)

    def localized_name(self, locale: str) -> str:
        for candidate in locale_fallbacks(locale):
            if candidate in self.names:
                return self.names[candidate]
        return next(iter(self.names.values()), self.id)

    def effect_at(self, level: int) -> str:
        return str(self.effect_values.get(level, "")).strip()

    def level_data(self, level: int) -> ObservedResearchLevel | None:
        return self.levels.get(level)


@dataclass(frozen=True)
class ObservedResearchEdge:
    prerequisite_id: str
    research_id: str


@dataclass(frozen=True)
class ObservedResearchConnectionGroup:
    """One visual bus joining one or more tree cards on visible rows."""

    prerequisite_ids: tuple[str, ...]
    research_ids: tuple[str, ...]


@dataclass(frozen=True)
class ResearchTreeObservation:
    observation_id: str
    category_id: str
    titles: Mapping[str, str]
    locale: str
    source_type: str
    verification_status: str
    captured_on: str
    game_version: str
    scope: str
    notes: str
    nodes: tuple[ObservedResearchNode, ...]
    edges: tuple[ObservedResearchEdge, ...]
    source_url: str = ""
    license_name: str = ""
    license_url: str = ""
    connection_groups: tuple[ObservedResearchConnectionGroup, ...] = ()

    def localized_title(self, locale: str) -> str:
        for candidate in locale_fallbacks(locale):
            if candidate in self.titles:
                return self.titles[candidate]
        return next(iter(self.titles.values()), self.observation_id)

    def node_by_id(self) -> dict[str, ObservedResearchNode]:
        return {node.id: node for node in self.nodes}
