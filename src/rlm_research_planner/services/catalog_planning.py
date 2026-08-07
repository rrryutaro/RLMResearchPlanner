from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from rlm_research_planner.domain.models import PlayerState, RESOURCE_KEYS
from rlm_research_planner.domain.observations import (
    ObservedResearchLevel,
    ObservedResearchNode,
    ResearchTreeObservation,
)
from rlm_research_planner.services.calculation import (
    GuildHelpPolicy,
    RoundingMode,
    apply_free_speedup_time,
    apply_guild_helps,
    apply_research_speed,
    free_speedup_seconds_for_vip,
)


@dataclass(frozen=True)
class CatalogPlanStep:
    research_id: str
    level: int
    base_time_seconds: int | None
    adjusted_time_seconds: int | None
    after_help_seconds: int | None
    costs: dict[str, int]
    power: int | None
    verification_status: str


@dataclass(frozen=True)
class CatalogPlanIssue:
    code: str
    research_id: str = ""
    level: int = 0
    value: int = 0
    name: str = ""


@dataclass
class CatalogPlanResult:
    target_research_id: str
    target_level: int
    required_levels: dict[str, int] = field(default_factory=dict)
    edges: set[tuple[str, str]] = field(default_factory=set)
    steps: list[CatalogPlanStep] = field(default_factory=list)
    total_base_seconds: int = 0
    total_adjusted_seconds: int = 0
    total_after_help_seconds: int = 0
    total_costs: dict[str, int] = field(default_factory=dict)
    total_power: int = 0
    resource_shortfalls: dict[str, int] = field(default_factory=dict)
    building_requirements: dict[str, int] = field(default_factory=dict)
    issues: list[CatalogPlanIssue] = field(default_factory=list)
    unknown_time_steps: int = 0
    unknown_cost_steps: int = 0
    unknown_power_steps: int = 0

    @property
    def complete_time_total(self) -> bool:
        return self.unknown_time_steps == 0

    @property
    def complete_cost_total(self) -> bool:
        return self.unknown_cost_steps == 0


class CatalogResearchPlanner:
    """Calculate unmet research from the sourced catalog without inventing values."""

    def __init__(self, observations: tuple[ResearchTreeObservation, ...]) -> None:
        self.nodes: dict[str, ObservedResearchNode] = {
            node.id: node for observation in observations for node in observation.nodes
        }

    def create_plan(
        self,
        state: PlayerState,
        target_research_id: str,
        target_level: int,
        *,
        rounding: RoundingMode = RoundingMode.CEILING,
        help_policy: GuildHelpPolicy | None = None,
    ) -> CatalogPlanResult:
        if target_research_id not in self.nodes:
            raise KeyError(target_research_id)
        target = self.nodes[target_research_id]
        if target.max_level is None or not 1 <= target_level <= target.max_level:
            raise ValueError("target level is out of range")

        result = CatalogPlanResult(target_research_id, target_level)
        current_levels = state.research_levels
        if current_levels.get(target_research_id, 0) >= target_level:
            return result

        required: dict[str, int] = {target_research_id: target_level}
        pending: deque[str] = deque((target_research_id,))
        dependency_edges: set[tuple[str, str]] = set()
        missing_level_data: set[tuple[str, int]] = set()
        while pending:
            research_id = pending.popleft()
            node = self.nodes[research_id]
            needed = required[research_id]
            current = current_levels.get(research_id, 0)
            for level_number in range(current + 1, needed + 1):
                level_data = node.level_data(level_number)
                if level_data is None:
                    missing_level_data.add((research_id, level_number))
                    continue
                for requirement in level_data.requirements:
                    if requirement.research_id not in self.nodes:
                        continue
                    dependency_edges.add((requirement.research_id, research_id))
                    if current_levels.get(requirement.research_id, 0) >= requirement.level:
                        continue
                    previous = required.get(requirement.research_id, 0)
                    if requirement.level > previous:
                        required[requirement.research_id] = requirement.level
                        pending.append(requirement.research_id)

        result.required_levels = required
        result.edges = {
            edge
            for edge in dependency_edges
            if edge[0] in required and edge[1] in required
        }
        step_order = self._topological_step_order(required, current_levels)

        for research_id, level_number in sorted(missing_level_data):
            result.issues.append(
                CatalogPlanIssue("missing_level_data", research_id, level_number)
            )

        for research_id, level_number in step_order:
            level_data = self.nodes[research_id].level_data(level_number)
            step = self._create_step(
                research_id,
                level_number,
                level_data,
                state,
                rounding,
                help_policy,
            )
            result.steps.append(step)
            self._accumulate_step(result, step, level_data)

        for resource in RESOURCE_KEYS:
            required_amount = result.total_costs.get(resource, 0)
            available = state.settings.resources.get(resource, 0)
            if required_amount > available:
                result.resource_shortfalls[resource] = required_amount - available
        return result

    def _topological_step_order(
        self,
        required: dict[str, int],
        current_levels: dict[str, int],
    ) -> list[tuple[str, int]]:
        steps = {
            (research_id, level)
            for research_id, target_level in required.items()
            for level in range(current_levels.get(research_id, 0) + 1, target_level + 1)
        }
        prerequisites: dict[tuple[str, int], set[tuple[str, int]]] = defaultdict(set)
        for research_id, level in steps:
            previous = (research_id, level - 1)
            if previous in steps:
                prerequisites[(research_id, level)].add(previous)
            level_data = self.nodes[research_id].level_data(level)
            if level_data is None:
                continue
            for requirement in level_data.requirements:
                dependency = (requirement.research_id, requirement.level)
                if dependency in steps:
                    prerequisites[(research_id, level)].add(dependency)

        visiting: set[tuple[str, int]] = set()
        visited: set[tuple[str, int]] = set()
        order: list[tuple[str, int]] = []

        def visit(step: tuple[str, int]) -> None:
            if step in visiting:
                raise ValueError(
                    f"Cyclic prerequisite detected at {step[0]}:{step[1]}"
                )
            if step in visited:
                return
            visiting.add(step)
            for prerequisite in sorted(prerequisites.get(step, ())):
                visit(prerequisite)
            visiting.remove(step)
            visited.add(step)
            order.append(step)

        for step in sorted(steps):
            visit(step)
        return order

    @staticmethod
    def _create_step(
        research_id: str,
        level_number: int,
        level_data: ObservedResearchLevel | None,
        state: PlayerState,
        rounding: RoundingMode,
        help_policy: GuildHelpPolicy | None,
    ) -> CatalogPlanStep:
        if level_data is None:
            return CatalogPlanStep(
                research_id,
                level_number,
                None,
                None,
                None,
                {},
                None,
                "unverified",
            )
        adjusted = None
        after_help = None
        if level_data.base_time_seconds is not None:
            adjusted = apply_research_speed(
                level_data.base_time_seconds,
                state.settings.effective_research_speed_percent,
                rounding,
            )
            adjusted = apply_free_speedup_time(
                adjusted,
                free_speedup_seconds_for_vip(state.settings.vip_level),
            )
            after_help = apply_guild_helps(
                adjusted,
                state.settings.max_guild_helps,
                help_policy,
            )
        return CatalogPlanStep(
            research_id,
            level_number,
            level_data.base_time_seconds,
            adjusted,
            after_help,
            dict(level_data.costs),
            level_data.power,
            level_data.verification_status,
        )

    @staticmethod
    def _accumulate_step(
        result: CatalogPlanResult,
        step: CatalogPlanStep,
        level_data: ObservedResearchLevel | None,
    ) -> None:
        if step.base_time_seconds is None:
            result.unknown_time_steps += 1
        else:
            result.total_base_seconds += step.base_time_seconds
            result.total_adjusted_seconds += int(step.adjusted_time_seconds or 0)
            result.total_after_help_seconds += int(step.after_help_seconds or 0)
        if level_data is None or not level_data.costs_verified:
            result.unknown_cost_steps += 1
        for material, amount in step.costs.items():
            result.total_costs[material] = result.total_costs.get(material, 0) + amount
        if step.power is None:
            result.unknown_power_steps += 1
        else:
            result.total_power += step.power
        if level_data is None:
            return
        if level_data.academy_level is not None:
            result.building_requirements["academy"] = max(
                result.building_requirements.get("academy", 0),
                level_data.academy_level,
            )
        for building, level in level_data.building_requirements.items():
            result.building_requirements[building] = max(
                result.building_requirements.get(building, 0), level
            )
