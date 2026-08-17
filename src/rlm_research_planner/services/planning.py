from __future__ import annotations

from dataclasses import dataclass, field

from rlm_research_planner.domain.models import (
    MasterData,
    PlayerState,
    RESOURCE_KEYS,
    SpeedupInventoryItem,
)
from rlm_research_planner.services.calculation import (
    GuildHelpPolicy,
    RoundingMode,
    apply_free_speedup_time,
    apply_guild_helps,
    apply_percentage_discount,
    apply_research_event_resource_discount,
    apply_research_speed,
    free_speedup_seconds_for_vip,
)
from rlm_research_planner.services.speedup_inventory import speedup_coverage


@dataclass(frozen=True)
class PlanStep:
    research_id: str
    level: int
    academy_level: int
    base_time_seconds: int
    adjusted_time_seconds: int
    after_help_seconds: int
    resources: dict[str, int]
    power: int
    ancient_tomes: int
    verification_status: str


@dataclass(frozen=True)
class PlanIssue:
    code: str
    values: dict[str, object]


@dataclass
class PlanResult:
    target_research_id: str
    target_level: int
    steps: list[PlanStep] = field(default_factory=list)
    total_base_seconds: int = 0
    total_adjusted_seconds: int = 0
    total_after_help_seconds: int = 0
    total_resources: dict[str, int] = field(
        default_factory=lambda: {key: 0 for key in RESOURCE_KEYS}
    )
    total_power: int = 0
    total_ancient_tomes: int = 0
    help_reduction_seconds: int = 0
    speedup_shortfall_seconds: int = 0
    resource_shortfalls: dict[str, int] = field(
        default_factory=lambda: {key: 0 for key in RESOURCE_KEYS}
    )
    unmet_conditions: list[str] = field(default_factory=list)
    timing_classification: str = "normal"
    warnings: list[str] = field(default_factory=list)
    issues: list[PlanIssue] = field(default_factory=list)


class ResearchPlanner:
    def __init__(self, master: MasterData) -> None:
        self.master = master
        self._research = master.research_by_id()

    def create_plan(
        self,
        state: PlayerState,
        target_research_id: str,
        target_level: int,
        *,
        rounding: RoundingMode = RoundingMode.CEILING,
        help_policy: GuildHelpPolicy | None = None,
    ) -> PlanResult:
        if target_research_id not in self._research:
            raise KeyError(target_research_id)
        target = self._research[target_research_id]
        if target_level < 1 or target_level > target.max_level:
            raise ValueError("target level is out of range")
        result = PlanResult(target_research_id, target_level)
        requirements: dict[str, int] = {}
        visiting: set[tuple[str, int]] = set()
        order: list[tuple[str, int]] = []
        self._visit_target(
            target_research_id,
            target_level,
            state.research_levels,
            requirements,
            visiting,
            order,
        )

        emitted: set[tuple[str, int]] = set()
        for research_id, required_level in order:
            current_level = state.research_levels.get(research_id, 0)
            for level_number in range(current_level + 1, required_level + 1):
                key = (research_id, level_number)
                if key in emitted:
                    continue
                emitted.add(key)
                level = self.master.level(research_id, level_number)
                category_id = self._research[research_id].category_id
                discount_percent = (
                    state.settings.research_event_discount_percent_for(category_id)
                )
                discounted_base_seconds = apply_percentage_discount(
                    level.base_time_seconds,
                    discount_percent,
                )
                adjusted = apply_research_speed(
                    discounted_base_seconds,
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
                step = PlanStep(
                    research_id=research_id,
                    level=level_number,
                    academy_level=level.academy_level,
                    base_time_seconds=level.base_time_seconds,
                    adjusted_time_seconds=adjusted,
                    after_help_seconds=after_help,
                    resources={
                        key: apply_research_event_resource_discount(
                            key,
                            int(level.resources.get(key, 0)),
                            discount_percent,
                        )
                        for key in RESOURCE_KEYS
                    },
                    power=level.power,
                    ancient_tomes=level.ancient_tomes,
                    verification_status=level.verification_status,
                )
                result.steps.append(step)
                result.total_base_seconds += step.base_time_seconds
                result.total_adjusted_seconds += step.adjusted_time_seconds
                result.total_after_help_seconds += step.after_help_seconds
                result.total_power += step.power
                result.total_ancient_tomes += step.ancient_tomes
                for resource, amount in step.resources.items():
                    result.total_resources[resource] += amount
                if step.verification_status != "verified":
                    result.warnings.append(
                        f"{research_id} level {level_number} contains unverified data"
                    )
                    result.issues.append(
                        PlanIssue(
                            "unverified_data",
                            {"research_id": research_id, "level": level_number},
                        )
                    )

                if step.academy_level > state.settings.academy_level:
                    condition = (
                        f"Academy level {step.academy_level} required for "
                        f"{research_id} level {level_number}"
                    )
                    if condition not in result.unmet_conditions:
                        result.unmet_conditions.append(condition)
                        result.issues.append(
                            PlanIssue(
                                "academy_level",
                                {
                                    "research_id": research_id,
                                    "level": level_number,
                                    "required": step.academy_level,
                                },
                            )
                        )

                for prerequisite in self.master.prerequisites:
                    if (
                        prerequisite.research_id != research_id
                        or prerequisite.target_level > level_number
                    ):
                        continue
                    if (
                        prerequisite.building == "academy"
                        and prerequisite.building_level
                        > state.settings.academy_level
                    ):
                        condition = (
                            f"Academy level {prerequisite.building_level} required for "
                            f"{research_id} level {level_number}"
                        )
                        if condition not in result.unmet_conditions:
                            result.unmet_conditions.append(condition)
                            result.issues.append(
                                PlanIssue(
                                    "academy_level",
                                    {
                                        "research_id": research_id,
                                        "level": level_number,
                                        "required": prerequisite.building_level,
                                    },
                                )
                            )
                    elif prerequisite.building:
                        condition = (
                            f"{prerequisite.building} level "
                            f"{prerequisite.building_level} must be confirmed"
                        )
                        if condition not in result.unmet_conditions:
                            result.unmet_conditions.append(condition)
                            result.issues.append(
                                PlanIssue(
                                    "building_level",
                                    {
                                        "building": prerequisite.building,
                                        "required": prerequisite.building_level,
                                    },
                                )
                            )
                    if prerequisite.other_condition:
                        condition = (
                            f"Condition must be confirmed: "
                            f"{prerequisite.other_condition}"
                        )
                        if condition not in result.unmet_conditions:
                            result.unmet_conditions.append(condition)
                            result.issues.append(
                                PlanIssue(
                                    "other_condition",
                                    {"condition": prerequisite.other_condition},
                                )
                            )

        self._append_shortage_warnings(result, state)
        result.help_reduction_seconds = max(
            0, result.total_adjusted_seconds - result.total_after_help_seconds
        )
        inventory = state.settings.speedup_inventory
        if not inventory and state.settings.speedup_seconds > 0:
            inventory = [
                SpeedupInventoryItem(
                    "general", 1, state.settings.speedup_seconds
                )
            ]
        coverage = speedup_coverage(
            result.total_after_help_seconds,
            inventory,
            "research",
            (step.after_help_seconds for step in result.steps),
        )
        result.speedup_shortfall_seconds = coverage.remaining_seconds
        result.timing_classification = self._timing_classification(result)
        return result

    def _visit_target(
        self,
        research_id: str,
        target_level: int,
        current_levels: dict[str, int],
        requirements: dict[str, int],
        visiting: set[tuple[str, int]],
        order: list[tuple[str, int]],
    ) -> None:
        if current_levels.get(research_id, 0) >= target_level:
            return
        key = (research_id, target_level)
        if key in visiting:
            raise ValueError(f"Cyclic prerequisite detected at {research_id}:{target_level}")
        if requirements.get(research_id, 0) >= target_level:
            return
        visiting.add(key)
        for prerequisite in self.master.prerequisites:
            if prerequisite.research_id != research_id:
                continue
            if prerequisite.target_level > target_level:
                continue
            if prerequisite.prerequisite_research_id:
                self._visit_target(
                    prerequisite.prerequisite_research_id,
                    prerequisite.prerequisite_level,
                    current_levels,
                    requirements,
                    visiting,
                    order,
                )
        visiting.remove(key)
        requirements[research_id] = max(requirements.get(research_id, 0), target_level)
        order.append((research_id, target_level))

    @staticmethod
    def _append_shortage_warnings(result: PlanResult, state: PlayerState) -> None:
        for resource, required in result.total_resources.items():
            available = state.settings.resources.get(resource, 0)
            if required > available:
                result.resource_shortfalls[resource] = required - available
                result.warnings.append(
                    f"Insufficient {resource}: need {required - available} more"
                )
                result.issues.append(
                    PlanIssue(
                        "resource_shortage",
                        {"resource": resource, "amount": required - available},
                    )
                )
        inventory = state.settings.speedup_inventory
        if not inventory and state.settings.speedup_seconds > 0:
            inventory = [
                SpeedupInventoryItem(
                    "general", 1, state.settings.speedup_seconds
                )
            ]
        coverage = speedup_coverage(
            result.total_after_help_seconds,
            inventory,
            "research",
            (step.after_help_seconds for step in result.steps),
        )
        if coverage.remaining_seconds > 0:
            result.warnings.append(
                "Available speedups do not cover the post-help research time"
            )
            result.issues.append(
                PlanIssue(
                    "speedup_shortage",
                    {
                        "seconds": coverage.remaining_seconds
                    },
                )
            )
        result.warnings.extend(result.unmet_conditions)

    @staticmethod
    def _timing_classification(result: PlanResult) -> str:
        if result.unmet_conditions:
            return "prerequisite_shortage"
        if any(result.resource_shortfalls.values()):
            return "resource_shortage"
        if result.total_ancient_tomes > 0:
            return "ancient_tomes_caution"
        if result.total_adjusted_seconds > 0 and result.total_after_help_seconds == 0:
            return "help_only_possible"
        if result.total_after_help_seconds > 0 and result.speedup_shortfall_seconds == 0:
            return "help_then_speedups"
        if result.help_reduction_seconds >= 3600:
            return "busy_hours_recommended"
        return "normal"
