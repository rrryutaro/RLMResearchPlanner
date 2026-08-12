from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from rlm_research_planner.domain.models import TalentPlanStep


TALENT_DIRECTIVE_DOCUMENT_TYPE = "RLMResearchPlanner.talent-directive"
TALENT_DIRECTIVE_SCHEMA_VERSION = 1


class TalentCatalogError(ValueError):
    pass


class TalentDirectiveFormatError(ValueError):
    pass


@dataclass(frozen=True)
class TalentPrerequisite:
    talent_id: str
    level: int


@dataclass(frozen=True)
class Talent:
    id: str
    branch: str
    row: int
    order: int
    max_level: int
    names: Mapping[str, str]
    effect_names: Mapping[str, str]
    max_effect: float
    prerequisite: TalentPrerequisite | None

    def localized_name(self, locale: str) -> str:
        return _localized(self.names, locale, self.id)

    def localized_effect(self, locale: str) -> str:
        return _localized(self.effect_names, locale, self.id)


@dataclass(frozen=True)
class TalentPreset:
    id: str
    names: Mapping[str, str]
    descriptions: Mapping[str, str]
    verification_status: str
    targets: tuple[TalentPlanStep, ...]

    def localized_name(self, locale: str) -> str:
        return _localized(self.names, locale, self.id)

    def localized_description(self, locale: str) -> str:
        return _localized(self.descriptions, locale, "")


@dataclass(frozen=True)
class TalentAllocationStep:
    talent_id: str
    start_level: int
    target_level: int
    allocated_level: int
    cumulative_points: int


@dataclass(frozen=True)
class TalentAllocation:
    steps: tuple[TalentAllocationStep, ...]
    available_points: int
    used_points: int
    required_points: int

    @property
    def remaining_points(self) -> int:
        return max(0, self.available_points - self.used_points)


@dataclass(frozen=True)
class TalentLevelRequirement:
    player_level: int | None
    required_base_points: int
    points_at_max_level: int

    @property
    def shortage_at_max_level(self) -> int:
        return max(0, self.required_base_points - self.points_at_max_level)

@dataclass(frozen=True)
class TalentDirective:
    name: str
    catalog_version: str
    steps: tuple[TalentPlanStep, ...]


class TalentCatalog:
    def __init__(
        self,
        *,
        version: str,
        default_available_points: int,
        point_rewards_by_level: Iterable[int],
        talents: Iterable[Talent],
        presets: Iterable[TalentPreset],
    ) -> None:
        self.version = str(version)
        self.default_available_points = max(0, int(default_available_points))
        self.point_rewards_by_level = tuple(
            max(0, int(value)) for value in point_rewards_by_level
        )
        self.talents = {talent.id: talent for talent in talents}
        self.presets = {preset.id: preset for preset in presets}
        self.preset_order = tuple(preset.id for preset in presets)
        self._validate()

    @classmethod
    def load(cls, path: Path) -> "TalentCatalog":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TalentCatalogError(f"cannot load talent catalog: {exc}") from exc
        if (
            not isinstance(raw, dict)
            or raw.get("document_type") != "RLMResearchPlanner.talent-catalog"
            or int(raw.get("schema_version", 0)) != 1
        ):
            raise TalentCatalogError("unsupported talent catalog")
        talents: list[Talent] = []
        for item in raw.get("talents", []):
            if not isinstance(item, dict):
                continue
            prerequisite_raw = item.get("prerequisite")
            prerequisite = (
                TalentPrerequisite(
                    str(prerequisite_raw.get("talent_id", "")).strip(),
                    max(1, int(prerequisite_raw.get("level", 1))),
                )
                if isinstance(prerequisite_raw, dict)
                else None
            )
            effect = item.get("effect", {})
            talents.append(
                Talent(
                    id=str(item.get("id", "")).strip(),
                    branch=str(item.get("branch", "")).strip(),
                    row=max(1, int(item.get("row", 1))),
                    order=max(0, int(item.get("order", 0))),
                    max_level=max(1, int(item.get("max_level", 1))),
                    names=_text_mapping(item.get("name")),
                    effect_names=_text_mapping(
                        effect if isinstance(effect, Mapping) else {}
                    ),
                    max_effect=float(
                        effect.get("max", 0.0)
                        if isinstance(effect, Mapping)
                        else 0.0
                    ),
                    prerequisite=prerequisite,
                )
            )
        presets: list[TalentPreset] = []
        for item in raw.get("presets", []):
            if not isinstance(item, dict):
                continue
            presets.append(
                TalentPreset(
                    id=str(item.get("id", "")).strip(),
                    names=_text_mapping(item.get("name")),
                    descriptions=_text_mapping(item.get("description")),
                    verification_status=str(
                        item.get("verification_status", "provisional")
                    ),
                    targets=_normalized_steps(item.get("targets", [])),
                )
            )
        return cls(
            version=str(raw.get("catalog_version", "")),
            default_available_points=max(
                0, int(raw.get("default_available_points", 278))
            ),
            point_rewards_by_level=raw.get("talent_point_bonus_by_level", ()),
            talents=talents,
            presets=presets,
        )

    def _validate(self) -> None:
        if not self.talents:
            raise TalentCatalogError("talent catalog is empty")
        if len(self.point_rewards_by_level) != 60:
            raise TalentCatalogError(
                "talent point rewards must contain Player Lv.1 through Lv.60"
            )
        if sum(self.point_rewards_by_level) != self.default_available_points:
            raise TalentCatalogError(
                "talent point rewards do not match default available points"
            )
        for talent in self.talents.values():
            prerequisite = talent.prerequisite
            if prerequisite is None:
                continue
            parent = self.talents.get(prerequisite.talent_id)
            if parent is None:
                raise TalentCatalogError(
                    f"unknown talent prerequisite: {prerequisite.talent_id}"
                )
            if prerequisite.level > parent.max_level:
                raise TalentCatalogError(
                    f"invalid talent prerequisite level: {talent.id}"
                )
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(talent_id: str) -> None:
            if talent_id in visiting:
                raise TalentCatalogError(
                    f"cyclic talent prerequisite: {talent_id}"
                )
            if talent_id in visited:
                return
            visiting.add(talent_id)
            prerequisite = self.talents[talent_id].prerequisite
            if prerequisite is not None:
                visit(prerequisite.talent_id)
            visiting.remove(talent_id)
            visited.add(talent_id)

        for talent_id in self.talents:
            visit(talent_id)
        for preset in self.presets.values():
            self.expand_targets(preset.targets)

    def expand_targets(
        self, targets: Iterable[TalentPlanStep]
    ) -> tuple[TalentPlanStep, ...]:
        expanded: list[TalentPlanStep] = []
        planned_levels: dict[str, int] = {}

        def require(talent_id: str, target_level: int) -> None:
            talent = self.talents.get(talent_id)
            if talent is None:
                raise TalentCatalogError(f"unknown talent id: {talent_id}")
            target = max(1, min(talent.max_level, int(target_level)))
            prerequisite = talent.prerequisite
            if prerequisite is not None:
                require(prerequisite.talent_id, prerequisite.level)
            if target <= planned_levels.get(talent_id, 0):
                return
            expanded.append(TalentPlanStep(talent_id, target))
            planned_levels[talent_id] = target

        for step in _normalized_steps(targets):
            require(step.talent_id, step.target_level)
        return tuple(expanded)

    def layout_columns(self) -> dict[str, float]:
        """Place each branch in a stable lane instead of recentering every row."""

        branch_order = tuple(
            dict.fromkeys(
                talent.branch
                for talent in sorted(
                    self.talents.values(), key=lambda item: item.order
                )
            )
        )
        branch_widths = {
            branch: max(
                (
                    sum(
                        1
                        for candidate in self.talents.values()
                        if candidate.branch == branch and candidate.row == row
                    )
                    for row in {item.row for item in self.talents.values()}
                ),
                default=1,
            )
            for branch in branch_order
        }
        branch_starts: dict[str, int] = {}
        next_column = 0
        for branch in branch_order:
            branch_starts[branch] = next_column
            next_column += branch_widths[branch]

        columns: dict[str, float] = {}
        rows = sorted({talent.row for talent in self.talents.values()})
        for row in rows:
            for branch_index, branch in enumerate(branch_order):
                row_talents = sorted(
                    (
                        talent
                        for talent in self.talents.values()
                        if talent.row == row and talent.branch == branch
                    ),
                    key=lambda item: item.order,
                )
                unused_lanes = branch_widths[branch] - len(row_talents)
                # The game uses fixed lanes. A single military talent is on
                # the inner right lane; a single economy talent is on the
                # inner left lane, never halfway between two lanes.
                start = branch_starts[branch]
                if branch_index < len(branch_order) / 2.0:
                    start += unused_lanes
                for offset, talent in enumerate(row_talents):
                    columns[talent.id] = start + offset
        return columns

    def plan_for_preset(self, preset_id: str) -> tuple[TalentPlanStep, ...]:
        preset = self.presets.get(preset_id)
        if preset is None:
            raise TalentCatalogError(f"unknown talent preset: {preset_id}")
        return self.expand_targets(preset.targets)

    def prioritized_steps(
        self,
        steps: Iterable[TalentPlanStep],
        priority_talent_id: str = "",
    ) -> tuple[TalentPlanStep, ...]:
        normalized = list(_normalized_steps(steps))
        priority_id = str(priority_talent_id).strip()
        if not priority_id:
            return tuple(normalized)
        prioritized = [step for step in normalized if step.talent_id == priority_id]
        if not prioritized:
            return tuple(normalized)
        others = [step for step in normalized if step.talent_id != priority_id]
        return tuple((*prioritized, *others))

    def points_for_player_level(self, player_level: int) -> int:
        level = max(1, min(len(self.point_rewards_by_level), int(player_level)))
        return sum(self.point_rewards_by_level[:level])

    def player_level_requirement(
        self,
        required_points: int,
        bonus_points: int = 0,
    ) -> TalentLevelRequirement:
        required_base = max(0, int(required_points) - max(0, int(bonus_points)))
        cumulative = 0
        for level, reward in enumerate(self.point_rewards_by_level, start=1):
            cumulative += reward
            if cumulative >= required_base:
                return TalentLevelRequirement(
                    level,
                    required_base,
                    self.default_available_points,
                )
        return TalentLevelRequirement(
            None,
            required_base,
            self.default_available_points,
        )

    def allocate(
        self,
        steps: Iterable[TalentPlanStep],
        available_points: int,
        priority_talent_id: str = "",
    ) -> TalentAllocation:
        expanded = self.expand_targets(
            self.prioritized_steps(steps, priority_talent_id)
        )
        remaining = max(0, int(available_points))
        used = 0
        required = 0
        planned_levels: dict[str, int] = {}
        allocated: list[TalentAllocationStep] = []
        for step in expanded:
            start_level = planned_levels.get(step.talent_id, 0)
            required_delta = max(0, step.target_level - start_level)
            allocated_delta = min(required_delta, remaining)
            level = start_level + allocated_delta
            required += required_delta
            used += allocated_delta
            remaining -= allocated_delta
            planned_levels[step.talent_id] = level
            allocated.append(
                TalentAllocationStep(
                    step.talent_id,
                    start_level,
                    step.target_level,
                    level,
                    used,
                )
            )
        return TalentAllocation(
            tuple(allocated), max(0, int(available_points)), used, required
        )


def talent_directive_payload(
    steps: Iterable[TalentPlanStep],
    *,
    name: str,
    catalog_version: str,
) -> dict[str, object]:
    return {
        "document_type": TALENT_DIRECTIVE_DOCUMENT_TYPE,
        "schema_version": TALENT_DIRECTIVE_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "name": str(name).strip()[:100],
        "catalog_version": str(catalog_version),
        "steps": [
            {"talent_id": step.talent_id, "target_level": step.target_level}
            for step in _normalized_steps(steps)
        ],
    }


def talent_directive_from_payload(raw: object) -> TalentDirective:
    if not isinstance(raw, Mapping):
        raise TalentDirectiveFormatError("invalid talent directive")
    if (
        raw.get("document_type") != TALENT_DIRECTIVE_DOCUMENT_TYPE
        or _safe_int(raw.get("schema_version")) != TALENT_DIRECTIVE_SCHEMA_VERSION
        or not isinstance(raw.get("steps"), list)
    ):
        raise TalentDirectiveFormatError("unsupported talent directive")
    steps = _normalized_steps(raw["steps"])
    if not steps:
        raise TalentDirectiveFormatError("empty talent directive")
    return TalentDirective(
        name=str(raw.get("name", "") or "").strip()[:100]
        or "Talent Directive",
        catalog_version=str(raw.get("catalog_version", "") or ""),
        steps=steps,
    )


def _normalized_steps(values: object) -> tuple[TalentPlanStep, ...]:
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes, Mapping)):
        return ()
    normalized: list[TalentPlanStep] = []
    latest_levels: dict[str, int] = {}
    for value in values:
        if isinstance(value, TalentPlanStep):
            talent_id = value.talent_id.strip()
            target_level = _safe_int(value.target_level)
        elif isinstance(value, Mapping):
            talent_id = str(
                value.get("talent_id", value.get("talentId", ""))
            ).strip()
            target_level = _safe_int(
                value.get("target_level", value.get("targetLevel", 0))
            )
        else:
            continue
        if not talent_id or target_level < 1:
            continue
        if target_level <= latest_levels.get(talent_id, 0):
            continue
        normalized.append(TalentPlanStep(talent_id, target_level))
        latest_levels[talent_id] = target_level
    return tuple(normalized)


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): str(text)
        for key, text in value.items()
        if str(text).strip()
    }


def _localized(values: Mapping[str, str], locale: str, fallback: str) -> str:
    normalized = str(locale).replace("_", "-")
    language = normalized.split("-", 1)[0]
    for candidate in (normalized, language, "en-US", "ja-JP"):
        if candidate in values and str(values[candidate]).strip():
            return str(values[candidate])
    return fallback
