from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
CATALOG_PATH = PROJECT_ROOT / "data" / "research" / "catalog.json"
BASELINE_ROOT = PROJECT_ROOT / "dataset" / "baseline"

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rlm_research_planner.domain.models import PlayerState  # noqa: E402
from rlm_research_planner.repositories.catalog_repository import (  # noqa: E402
    JsonResearchCatalogRepository,
)
from rlm_research_planner.services.catalog_planning import (  # noqa: E402
    CatalogResearchPlanner,
)


DOCUMENT_TYPE = "RLMResearchPlanner.research-baseline"
SCHEMA_VERSION = 1


def _read_catalog() -> tuple[dict[str, Any], str]:
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return raw, canonical_json_sha256(raw)


def canonical_json_sha256(value: Any) -> str:
    """Hash JSON facts independently of indentation and line endings."""
    canonical = json.dumps(
        _canonical_json_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_canonical_json_value(item) for item in value]
    if not isinstance(value, dict):
        return value

    def js_property_order(key: str) -> tuple[int, int | str]:
        try:
            number = int(key)
        except ValueError:
            return (1, key)
        if str(number) == key and 0 <= number < 2**32 - 1:
            return (0, number)
        return (1, key)

    return {
        key: _canonical_json_value(value[key])
        for key in sorted(value, key=js_property_order)
    }


def _level_payload(level: Any) -> dict[str, Any]:
    return {
        "level": level.level,
        "academy_level": level.academy_level,
        "base_time_seconds": level.base_time_seconds,
        "technolabe_count": level.technolabe_count,
        "costs": dict(level.costs),
        "power": level.power,
        "requirements": [
            {
                "research_id": requirement.research_id,
                "level": requirement.level,
            }
            for requirement in level.requirements
        ],
        "buildings": dict(level.building_requirements),
        "costs_verified": level.costs_verified,
        "verification_status": level.verification_status,
    }


def _node_payload(node: Any) -> dict[str, Any]:
    return {
        "id": node.id,
        "names": dict(node.names),
        "max_level": node.max_level,
        "row": node.row,
        "column": node.column,
        "effect_label": node.effect_label,
        "effect_values": {
            str(level): value
            for level, value in sorted(node.effect_values.items())
        },
        "levels": [
            _level_payload(level)
            for _, level in sorted(node.levels.items())
        ],
    }


def _display_pairs(observation: Any) -> list[list[str]]:
    pairs = {
        (prerequisite_id, research_id)
        for group in observation.connection_groups
        for prerequisite_id in group.prerequisite_ids
        for research_id in group.research_ids
    }
    return [list(pair) for pair in sorted(pairs)]


def _category_payload(observation: Any, source_hash: str) -> dict[str, Any]:
    return {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "platform": "pc",
        "source_catalog_sha256": source_hash,
        "category_id": observation.category_id,
        "titles": dict(observation.titles),
        "verification_status": observation.verification_status,
        "scope": observation.scope,
        "nodes": [
            _node_payload(node)
            for node in sorted(
                observation.nodes,
                key=lambda item: (item.row, item.column, item.id),
            )
        ],
        "source_edges": [
            [edge.prerequisite_id, edge.research_id]
            for edge in observation.edges
        ],
        "display_connection_groups": [
            {
                "prerequisite_ids": list(group.prerequisite_ids),
                "research_ids": list(group.research_ids),
            }
            for group in observation.connection_groups
        ],
        "display_connections": _display_pairs(observation),
    }


def _plan_step_payload(step: Any) -> dict[str, Any]:
    return {
        "research_id": step.research_id,
        "level": step.level,
        "base_time_seconds": step.base_time_seconds,
        "adjusted_time_seconds": step.adjusted_time_seconds,
        "after_help_seconds": step.after_help_seconds,
        "costs": dict(step.costs),
        "costs_verified": step.costs_verified,
        "technolabe_count": step.technolabe_count,
        "technolabe_efficiency_percent": step.technolabe_efficiency_percent,
        "power": step.power,
        "verification_status": step.verification_status,
    }


def _plan_payload(observation: Any, planner: CatalogResearchPlanner) -> dict[str, Any]:
    candidates = [
        node
        for node in observation.nodes
        if node.max_level is not None and node.max_level > 0
    ]
    target = max(candidates, key=lambda item: (item.row, item.column, item.id))
    result = planner.create_plan(PlayerState(), target.id, int(target.max_level))
    return {
        "category_id": observation.category_id,
        "target_research_id": target.id,
        "target_level": int(target.max_level),
        "required_levels": dict(sorted(result.required_levels.items())),
        "dependency_edges": [list(edge) for edge in sorted(result.edges)],
        "steps": [_plan_step_payload(step) for step in result.steps],
        "totals": {
            "base_time_seconds": result.total_base_seconds,
            "adjusted_time_seconds": result.total_adjusted_seconds,
            "after_help_seconds": result.total_after_help_seconds,
            "costs": dict(sorted(result.total_costs.items())),
            "power": result.total_power,
            "unknown_time_steps": result.unknown_time_steps,
            "unknown_cost_steps": result.unknown_cost_steps,
            "unknown_power_steps": result.unknown_power_steps,
            "unknown_technolabe_steps": result.unknown_technolabe_steps,
            "technolabe_count": result.total_technolabes,
            "technolabe_base_seconds": result.technolabe_base_seconds,
            "technolabe_efficiency_percent": (
                result.technolabe_efficiency_percent
            ),
        },
        "issues": [
            {
                "code": issue.code,
                "research_id": issue.research_id,
                "level": issue.level,
                "value": issue.value,
                "name": issue.name,
            }
            for issue in result.issues
        ],
    }


def build_pc_baseline() -> dict[str, Any]:
    raw, source_hash = _read_catalog()
    observations = JsonResearchCatalogRepository(CATALOG_PATH).load_all()
    planner = CatalogResearchPlanner(observations)
    categories = {
        observation.category_id: _category_payload(observation, source_hash)
        for observation in observations
    }
    plans = [_plan_payload(observation, planner) for observation in observations]
    research_ids = [
        {
            "id": node.id,
            "category_id": observation.category_id,
            "en-US": node.names.get("en-US", ""),
            "ja-JP": node.names.get("ja-JP", ""),
            "max_level": node.max_level,
        }
        for observation in observations
        for node in sorted(
            observation.nodes,
            key=lambda item: (item.row, item.column, item.id),
        )
    ]
    level_count = sum(
        len(node.levels)
        for observation in observations
        for node in observation.nodes
    )
    manifest = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "baseline_phase": 0,
        "source_catalog": {
            "path": "tools/RLMResearchPlanner/data/research/catalog.json",
            "sha256": source_hash,
            "schema_version": raw.get("schema_version"),
            "dataset_id": raw.get("dataset_id", ""),
            "checked_on": raw.get("checked_on", ""),
            "game_version": raw.get("game_version", ""),
        },
        "statistics": {
            "categories": len(observations),
            "research": len(research_ids),
            "levels": level_count,
            "representative_plans": len(plans),
        },
        "category_ids": [item.category_id for item in observations],
        "edit_policy": {
            "source_of_truth": "legacy_catalog",
            "generated_files_are_editable": False,
            "applications_read_this_baseline": False,
        },
    }
    return {
        "manifest": manifest,
        "research_ids": research_ids,
        "categories": categories,
        "plans": {
            "document_type": DOCUMENT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "platform": "pc",
            "source_catalog_sha256": source_hash,
            "plans": plans,
        },
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_pc_baseline(baseline: dict[str, Any]) -> None:
    _write_json(BASELINE_ROOT / "manifest.json", baseline["manifest"])
    _write_json(BASELINE_ROOT / "research-ids.json", baseline["research_ids"])
    for category_id, payload in baseline["categories"].items():
        _write_json(
            BASELINE_ROOT / "pc" / "categories" / f"{category_id}.json",
            payload,
        )
    _write_json(BASELINE_ROOT / "pc" / "plans.json", baseline["plans"])


def main() -> int:
    baseline = build_pc_baseline()
    write_pc_baseline(baseline)
    print(
        "PC research baseline generated: "
        f"{baseline['manifest']['statistics']['research']} research IDs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
