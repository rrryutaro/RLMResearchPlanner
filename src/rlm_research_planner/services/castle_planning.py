from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from rlm_research_planner.services.calculation import (
    apply_free_speedup_time,
    apply_guild_helps,
    apply_research_speed,
    free_speedup_seconds_for_vip,
)


CASTLE_RESOURCE_KEYS = ("food", "stone", "timber", "ore", "gold_hammer")


@dataclass(frozen=True)
class BuildingLevelData:
    building_id: str
    level: int
    base_time_seconds: int
    costs: Mapping[str, int]
    requirements: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class BuildingData:
    id: str
    names: Mapping[str, str]
    max_level: int
    levels: Mapping[int, BuildingLevelData]

    def localized_name(self, locale: str) -> str:
        return (
            self.names.get(locale)
            or self.names.get(locale.split("-", 1)[0])
            or self.names.get("en-US")
            or self.id
        )


@dataclass(frozen=True)
class CastlePlanStep:
    building_id: str
    level: int
    base_seconds: int
    adjusted_seconds: int
    costs: Mapping[str, int]


@dataclass(frozen=True)
class CastleBuildingSummary:
    building_id: str
    current_level: int
    target_level: int
    base_seconds: int
    adjusted_seconds: int
    costs: Mapping[str, int]


@dataclass(frozen=True)
class CastlePlanResult:
    current_castle_level: int
    target_castle_level: int
    effective_levels: Mapping[str, int]
    steps: tuple[CastlePlanStep, ...]
    buildings: tuple[CastleBuildingSummary, ...]
    total_base_seconds: int
    total_adjusted_seconds: int
    total_costs: Mapping[str, int]
    issues: tuple[str, ...] = ()


class CastleCatalog:
    def __init__(self, buildings: Mapping[str, BuildingData]) -> None:
        self.buildings = dict(buildings)

    @classmethod
    def load(cls, path: Path) -> "CastleCatalog":
        raw = json.loads(path.read_text(encoding="utf-8"))
        buildings: dict[str, BuildingData] = {}
        for source in raw.get("buildings", []):
            building_id = str(source["id"])
            levels: dict[int, BuildingLevelData] = {}
            for level_text, level_source in source.get("levels", {}).items():
                level = int(level_text)
                levels[level] = BuildingLevelData(
                    building_id=building_id,
                    level=level,
                    base_time_seconds=max(
                        0, int(level_source.get("base_time_seconds") or 0)
                    ),
                    costs={
                        key: max(0, int(level_source.get("costs", {}).get(key, 0)))
                        for key in CASTLE_RESOURCE_KEYS
                    },
                    requirements=tuple(
                        (
                            str(requirement["building_id"]),
                            max(1, int(requirement["level"])),
                        )
                        for requirement in level_source.get("requirements", [])
                    ),
                )
            buildings[building_id] = BuildingData(
                id=building_id,
                names={str(key): str(value) for key, value in source["names"].items()},
                max_level=max(1, int(source.get("max_level", 25))),
                levels=levels,
            )
        if "castle" not in buildings:
            raise ValueError("Castle data is missing")
        return cls(buildings)

    def minimum_levels_for_castle(self, castle_level: int) -> dict[str, int]:
        levels: dict[str, int] = {building_id: 0 for building_id in self.buildings}
        visiting: set[tuple[str, int]] = set()

        def require(building_id: str, target_level: int) -> None:
            building = self.buildings.get(building_id)
            if not building:
                return
            normalized = min(building.max_level, max(0, int(target_level)))
            if normalized <= levels[building_id]:
                return
            previous = levels[building_id]
            levels[building_id] = normalized
            for level in range(previous + 1, normalized + 1):
                key = (building_id, level)
                if key in visiting:
                    raise ValueError(
                        f"Cyclic building prerequisite detected at {building_id}:{level}"
                    )
                visiting.add(key)
                data = building.levels.get(level)
                if data:
                    for required_id, required_level in data.requirements:
                        require(required_id, required_level)
                visiting.remove(key)

        require("castle", castle_level)
        return levels

    def effective_levels(
        self, castle_level: int, saved_levels: Mapping[str, int] | None = None
    ) -> dict[str, int]:
        result = self.minimum_levels_for_castle(castle_level)
        for building_id, value in (saved_levels or {}).items():
            building = self.buildings.get(building_id)
            if not building:
                continue
            result[building_id] = max(
                result.get(building_id, 0),
                min(building.max_level, max(0, int(value))),
            )
        result["castle"] = max(result.get("castle", 0), int(castle_level))
        return result

    def create_plan(
        self,
        *,
        castle_level: int,
        target_castle_level: int,
        saved_levels: Mapping[str, int] | None = None,
        construction_speed_percent: float = 0.0,
        vip_level: int = 1,
        guild_helps: int = 0,
    ) -> CastlePlanResult:
        castle = self.buildings["castle"]
        current = min(castle.max_level, max(1, int(castle_level)))
        target = min(castle.max_level, max(current, int(target_castle_level)))
        effective = self.effective_levels(current, saved_levels)
        steps: list[CastlePlanStep] = []
        completed: set[tuple[str, int]] = set()
        visiting: set[tuple[str, int]] = set()
        issues: list[str] = []

        def add_building(building_id: str, target_level: int) -> None:
            building = self.buildings.get(building_id)
            if not building:
                issues.append(f"Unknown building: {building_id}")
                return
            normalized = min(building.max_level, max(0, int(target_level)))
            start = effective.get(building_id, 0) + 1
            for level in range(start, normalized + 1):
                key = (building_id, level)
                if key in completed:
                    continue
                if key in visiting:
                    raise ValueError(
                        f"Cyclic building prerequisite detected at {building_id}:{level}"
                    )
                visiting.add(key)
                data = building.levels.get(level)
                if not data:
                    issues.append(f"Missing building data: {building_id}:{level}")
                    visiting.remove(key)
                    continue
                for required_id, required_level in data.requirements:
                    add_building(required_id, required_level)
                adjusted = apply_research_speed(
                    data.base_time_seconds, construction_speed_percent
                )
                adjusted = apply_free_speedup_time(
                    adjusted, free_speedup_seconds_for_vip(vip_level)
                )
                adjusted = apply_guild_helps(adjusted, max(0, int(guild_helps)))
                steps.append(
                    CastlePlanStep(
                        building_id=building_id,
                        level=level,
                        base_seconds=data.base_time_seconds,
                        adjusted_seconds=adjusted,
                        costs=data.costs,
                    )
                )
                completed.add(key)
                visiting.remove(key)

        add_building("castle", target)
        summary_by_id: dict[str, dict[str, object]] = {}
        total_costs = {key: 0 for key in CASTLE_RESOURCE_KEYS}
        for step in steps:
            summary = summary_by_id.setdefault(
                step.building_id,
                {
                    "target_level": effective.get(step.building_id, 0),
                    "base_seconds": 0,
                    "adjusted_seconds": 0,
                    "costs": {key: 0 for key in CASTLE_RESOURCE_KEYS},
                },
            )
            summary["target_level"] = max(int(summary["target_level"]), step.level)
            summary["base_seconds"] = int(summary["base_seconds"]) + step.base_seconds
            summary["adjusted_seconds"] = (
                int(summary["adjusted_seconds"]) + step.adjusted_seconds
            )
            costs = summary["costs"]
            assert isinstance(costs, dict)
            for key in CASTLE_RESOURCE_KEYS:
                amount = int(step.costs.get(key, 0))
                costs[key] = int(costs[key]) + amount
                total_costs[key] += amount
        summaries = tuple(
            CastleBuildingSummary(
                building_id=building_id,
                current_level=effective.get(building_id, 0),
                target_level=int(summary["target_level"]),
                base_seconds=int(summary["base_seconds"]),
                adjusted_seconds=int(summary["adjusted_seconds"]),
                costs=dict(summary["costs"]),
            )
            for building_id, summary in summary_by_id.items()
        )
        return CastlePlanResult(
            current_castle_level=current,
            target_castle_level=target,
            effective_levels=effective,
            steps=tuple(steps),
            buildings=summaries,
            total_base_seconds=sum(step.base_seconds for step in steps),
            total_adjusted_seconds=sum(step.adjusted_seconds for step in steps),
            total_costs=total_costs,
            issues=tuple(dict.fromkeys(issues)),
        )
