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


CASTLE_RESOURCE_KEYS = (
    "food",
    "stone",
    "timber",
    "ore",
    "gold_hammer",
    "war_tome",
    "steel_cuffs",
    "soul_crystal",
    "mana_ore",
    "mana_crystal",
    "mana_steel",
)


def minimum_gems_for_amount(
    amount: int,
    packs: tuple[tuple[int, int], ...],
) -> int:
    """Return the cheapest gem cost for buying at least ``amount`` items."""

    required = max(0, int(amount))
    normalized = tuple(
        (max(1, int(quantity)), max(0, int(gems)))
        for quantity, gems in packs
        if int(quantity) > 0 and int(gems) >= 0
    )
    if required == 0:
        return 0
    if not normalized:
        raise ValueError("Gem-shop pack data is missing")
    maximum_quantity = max(quantity for quantity, _gems in normalized)
    limit = required + maximum_quantity - 1
    unreachable = 10**30
    costs = [unreachable] * (limit + 1)
    costs[0] = 0
    for owned in range(limit + 1):
        if costs[owned] == unreachable:
            continue
        for quantity, gems in normalized:
            next_amount = min(limit, owned + quantity)
            costs[next_amount] = min(costs[next_amount], costs[owned] + gems)
    return min(costs[required:])


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
class CastleManaStageData:
    stage: int
    base_time_seconds: int
    costs: Mapping[str, int]


@dataclass(frozen=True)
class CastlePlanStep:
    building_id: str
    level: int
    base_seconds: int
    adjusted_seconds: int
    costs: Mapping[str, int]
    mana_stage: int = 0


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
    current_mana_stage: int
    target_mana_stage: int
    target_building_id: str
    target_building_level: int
    effective_levels: Mapping[str, int]
    steps: tuple[CastlePlanStep, ...]
    buildings: tuple[CastleBuildingSummary, ...]
    total_base_seconds: int
    total_adjusted_seconds: int
    total_costs: Mapping[str, int]
    gem_costs: Mapping[str, int]
    total_gems: int
    issues: tuple[str, ...] = ()


class CastleCatalog:
    def __init__(
        self,
        buildings: Mapping[str, BuildingData],
        mana_stages: Mapping[int, CastleManaStageData] | None = None,
        gem_shop_packs: Mapping[str, tuple[tuple[int, int], ...]] | None = None,
    ) -> None:
        self.buildings = dict(buildings)
        self.mana_stages = dict(mana_stages or {})
        self.gem_shop_packs = dict(gem_shop_packs or {})

    @property
    def max_mana_stage(self) -> int:
        return max(self.mana_stages, default=0)

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
        mana_stages: dict[int, CastleManaStageData] = {}
        mana_source = raw.get("castle_mana_progression", {})
        for stage_text, stage_source in mana_source.get("stages", {}).items():
            stage = int(stage_text)
            mana_stages[stage] = CastleManaStageData(
                stage=stage,
                base_time_seconds=max(
                    0, int(stage_source.get("base_time_seconds") or 0)
                ),
                costs={
                    key: max(0, int(stage_source.get("costs", {}).get(key, 0)))
                    for key in CASTLE_RESOURCE_KEYS
                },
            )
        gem_shop_packs = {
            str(key): tuple(
                (
                    max(1, int(pack.get("quantity") or 1)),
                    max(0, int(pack.get("gems") or 0)),
                )
                for pack in packs
            )
            for key, packs in raw.get("gem_shop_packs", {}).items()
        }
        if "castle" not in buildings:
            raise ValueError("Castle data is missing")
        return cls(buildings, mana_stages, gem_shop_packs)

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

    def gem_costs_for(
        self,
        costs: Mapping[str, int],
        owned_resources: Mapping[str, int] | None = None,
    ) -> dict[str, int]:
        available = owned_resources or {}
        result: dict[str, int] = {}
        for key, packs in self.gem_shop_packs.items():
            missing = max(
                0,
                int(costs.get(key, 0)) - max(0, int(available.get(key, 0))),
            )
            if missing:
                result[key] = minimum_gems_for_amount(missing, packs)
        return result

    def create_plan(
        self,
        *,
        castle_level: int,
        target_castle_level: int,
        current_mana_stage: int = 0,
        target_mana_stage: int = 0,
        saved_levels: Mapping[str, int] | None = None,
        construction_speed_percent: float = 0.0,
        vip_level: int = 1,
        guild_helps: int = 0,
        target_building_id: str = "castle",
        target_building_level: int | None = None,
        owned_resources: Mapping[str, int] | None = None,
    ) -> CastlePlanResult:
        castle = self.buildings["castle"]
        current = min(castle.max_level, max(1, int(castle_level)))
        selected_building = self.buildings.get(target_building_id)
        if selected_building is None:
            raise KeyError(target_building_id)
        target = min(castle.max_level, max(current, int(target_castle_level)))
        selected_target = (
            target
            if target_building_id == "castle"
            else min(
                selected_building.max_level,
                max(
                    self.effective_levels(current, saved_levels).get(
                        target_building_id, 0
                    ),
                    int(target_building_level or 0),
                ),
            )
        )
        if target_building_id != "castle":
            target = current
        current_mana = (
            min(self.max_mana_stage, max(0, int(current_mana_stage)))
            if current >= castle.max_level
            else 0
        )
        target_mana = (
            min(
                self.max_mana_stage,
                max(current_mana, int(target_mana_stage)),
            )
            if target >= castle.max_level
            else 0
        )
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

        add_building(target_building_id, selected_target)
        for stage in range(
            current_mana + 1,
            target_mana + 1 if target_building_id == "castle" else current_mana + 1,
        ):
            data = self.mana_stages.get(stage)
            if data is None:
                issues.append(f"Missing Castle Mana stage data: {stage}")
                continue
            adjusted = apply_research_speed(
                data.base_time_seconds, construction_speed_percent
            )
            adjusted = apply_free_speedup_time(
                adjusted, free_speedup_seconds_for_vip(vip_level)
            )
            adjusted = apply_guild_helps(adjusted, max(0, int(guild_helps)))
            steps.append(
                CastlePlanStep(
                    building_id="castle",
                    level=castle.max_level,
                    base_seconds=data.base_time_seconds,
                    adjusted_seconds=adjusted,
                    costs=data.costs,
                    mana_stage=stage,
                )
            )
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
        gem_costs = self.gem_costs_for(total_costs, owned_resources)
        return CastlePlanResult(
            current_castle_level=current,
            target_castle_level=target,
            current_mana_stage=current_mana,
            target_mana_stage=(
                target_mana if target_building_id == "castle" else current_mana
            ),
            target_building_id=target_building_id,
            target_building_level=selected_target,
            effective_levels=effective,
            steps=tuple(steps),
            buildings=summaries,
            total_base_seconds=sum(step.base_seconds for step in steps),
            total_adjusted_seconds=sum(step.adjusted_seconds for step in steps),
            total_costs=total_costs,
            gem_costs=gem_costs,
            total_gems=sum(gem_costs.values()),
            issues=tuple(dict.fromkeys(issues)),
        )
