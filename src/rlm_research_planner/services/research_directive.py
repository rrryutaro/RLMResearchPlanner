from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping

from rlm_research_planner.domain.models import ResearchPlanTask


RESEARCH_DIRECTIVE_DOCUMENT_TYPE = "RLMResearchPlanner.research-directive"
RESEARCH_DIRECTIVE_SCHEMA_VERSION = 1


class ResearchDirectiveFormatError(ValueError):
    """Raised when a research directive document cannot be read safely."""


@dataclass(frozen=True)
class ResearchDirective:
    name: str
    dataset_id: str
    game_version: str
    tasks: tuple[ResearchPlanTask, ...]


@dataclass(frozen=True)
class ResearchDirectiveMergeResult:
    tasks: tuple[ResearchPlanTask, ...]
    added: int
    updated: int
    unchanged: int


def _positive_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _normalized_tasks(tasks: Iterable[object]) -> tuple[ResearchPlanTask, ...]:
    normalized: list[ResearchPlanTask] = []
    positions: dict[str, int] = {}
    for item in tasks:
        if isinstance(item, ResearchPlanTask):
            research_id = item.research_id.strip()
            target_level = _positive_int(item.target_level)
        elif isinstance(item, Mapping):
            research_id = str(
                item.get("research_id", item.get("researchId", ""))
            ).strip()
            target_level = _positive_int(
                item.get("target_level", item.get("targetLevel", 0))
            )
        else:
            continue
        if not research_id or target_level < 1:
            continue
        if research_id in positions:
            position = positions[research_id]
            existing = normalized[position]
            if target_level > existing.target_level:
                normalized[position] = ResearchPlanTask(
                    research_id=research_id,
                    target_level=target_level,
                )
            continue
        positions[research_id] = len(normalized)
        normalized.append(ResearchPlanTask(research_id, target_level))
    return tuple(normalized)


def research_directive_payload(
    tasks: Iterable[ResearchPlanTask],
    *,
    name: str = "",
    dataset_id: str = "",
    game_version: str = "",
) -> dict[str, object]:
    return {
        "document_type": RESEARCH_DIRECTIVE_DOCUMENT_TYPE,
        "schema_version": RESEARCH_DIRECTIVE_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "name": str(name).strip()[:100],
        "dataset_id": str(dataset_id),
        "game_version": str(game_version),
        "tasks": [
            {
                "research_id": task.research_id,
                "target_level": task.target_level,
            }
            for task in _normalized_tasks(tasks)
        ],
    }


def research_directive_from_payload(raw: object) -> ResearchDirective:
    if not isinstance(raw, Mapping):
        raise ResearchDirectiveFormatError("invalid research directive")
    if (
        raw.get("document_type") != RESEARCH_DIRECTIVE_DOCUMENT_TYPE
        or _positive_int(raw.get("schema_version"))
        != RESEARCH_DIRECTIVE_SCHEMA_VERSION
        or not isinstance(raw.get("tasks"), list)
    ):
        raise ResearchDirectiveFormatError("unsupported research directive")
    tasks = _normalized_tasks(raw["tasks"])
    if not tasks:
        raise ResearchDirectiveFormatError("empty research directive")
    name = str(raw.get("name", "") or "").strip()[:100] or "Research Directive"
    return ResearchDirective(
        name=name,
        dataset_id=str(raw.get("dataset_id", "") or ""),
        game_version=str(raw.get("game_version", "") or ""),
        tasks=tasks,
    )


def merge_research_directive_tasks(
    existing_tasks: Iterable[ResearchPlanTask],
    directive_tasks: Iterable[ResearchPlanTask],
    *,
    source_name: str = "",
    created_at: str | None = None,
) -> ResearchDirectiveMergeResult:
    merged: list[ResearchPlanTask] = []
    positions: dict[str, int] = {}
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    for task in existing_tasks:
        research_id = str(task.research_id).strip()
        target_level = _positive_int(task.target_level)
        if not research_id or target_level < 1:
            continue
        if research_id in positions:
            position = positions[research_id]
            previous = merged[position]
            if target_level > previous.target_level:
                merged[position] = ResearchPlanTask(
                    research_id=research_id,
                    target_level=target_level,
                    created_at=previous.created_at,
                    source_name=previous.source_name,
                )
            continue
        positions[research_id] = len(merged)
        merged.append(task)

    added = 0
    updated = 0
    unchanged = 0
    for directive in _normalized_tasks(directive_tasks):
        if directive.research_id not in positions:
            positions[directive.research_id] = len(merged)
            merged.append(
                ResearchPlanTask(
                    directive.research_id,
                    directive.target_level,
                    timestamp,
                    str(source_name),
                )
            )
            added += 1
            continue
        position = positions[directive.research_id]
        previous = merged[position]
        if directive.target_level > previous.target_level:
            merged[position] = ResearchPlanTask(
                previous.research_id,
                directive.target_level,
                previous.created_at,
                str(source_name or previous.source_name),
            )
            updated += 1
        else:
            unchanged += 1
    return ResearchDirectiveMergeResult(tuple(merged), added, updated, unchanged)
