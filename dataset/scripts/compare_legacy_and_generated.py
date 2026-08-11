from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = PROJECT_ROOT / "dataset"
GENERATED_ROOT = DATASET_ROOT / "generated"
REPORT_PATH = DATASET_ROOT / "reports" / "legacy-vs-generated.json"
CATALOG_PATH = PROJECT_ROOT / "data" / "research" / "catalog.json"

sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(DATASET_ROOT / "scripts"))

from export_pc_baseline import (  # noqa: E402
    build_pc_baseline,
    canonical_json_sha256,
)
from validate_dataset import (  # noqa: E402
    collect_data_quality_warnings,
    load_dataset,
    validate_dataset,
)
from rlm_research_planner.domain.models import PlayerState  # noqa: E402
from rlm_research_planner.domain.observations import (  # noqa: E402
    ResearchTreeObservation,
)
from rlm_research_planner.repositories.research_dataset_adapter import (  # noqa: E402
    observations_from_research_dataset,
)
from rlm_research_planner.services.catalog_planning import (  # noqa: E402
    CatalogResearchPlanner,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _observations_from_generated(root: Path) -> tuple[ResearchTreeObservation, ...]:
    return observations_from_research_dataset(load_dataset(root))


def _generated_category_projection(
    observation: ResearchTreeObservation,
) -> dict[str, Any]:
    return {
        "category_id": observation.category_id,
        "titles": dict(observation.titles),
        "nodes": [
            {
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
                    {
                        "level": level.level,
                        "academy_level": level.academy_level,
                        "base_time_seconds": level.base_time_seconds,
                        "technolabe_count": level.technolabe_count,
                        "costs": dict(level.costs),
                        "costs_verified": level.costs_verified,
                        "power": level.power,
                        "requirements": [
                            {
                                "research_id": requirement.research_id,
                                "level": requirement.level,
                            }
                            for requirement in level.requirements
                        ],
                        "buildings": dict(level.building_requirements),
                    }
                    for _, level in sorted(node.levels.items())
                ],
            }
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
    }


def _legacy_category_projection(category: dict[str, Any]) -> dict[str, Any]:
    return {
        "category_id": category["category_id"],
        "titles": category["titles"],
        "nodes": [
            {
                key: node[key]
                for key in (
                    "id",
                    "names",
                    "max_level",
                    "row",
                    "column",
                    "effect_label",
                    "effect_values",
                    "levels",
                )
            }
            for node in category["nodes"]
        ],
        "source_edges": category["source_edges"],
        "display_connection_groups": category["display_connection_groups"],
    }


def _plan_payload(
    category_id: str,
    target_id: str,
    target_level: int,
    planner: CatalogResearchPlanner,
) -> dict[str, Any]:
    result = planner.create_plan(PlayerState(), target_id, target_level)
    return {
        "category_id": category_id,
        "target_research_id": target_id,
        "target_level": target_level,
        "required_levels": dict(sorted(result.required_levels.items())),
        "dependency_edges": [list(edge) for edge in sorted(result.edges)],
        "steps": [
            {
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
            }
            for step in result.steps
        ],
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
            "technolabe_efficiency_percent": result.technolabe_efficiency_percent,
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


def _without_legacy_verification(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_legacy_verification(item)
            for key, item in value.items()
            if key != "verification_status"
        }
    if isinstance(value, list):
        return [_without_legacy_verification(item) for item in value]
    return value


def _first_differences(
    expected: Any,
    actual: Any,
    path: str = "$",
    *,
    limit: int = 100,
) -> list[str]:
    differences: list[str] = []
    if type(expected) is not type(actual):
        return [f"{path}: type {type(expected).__name__} != {type(actual).__name__}"]
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            if len(differences) >= limit:
                break
            child_path = f"{path}.{key}"
            if key not in expected:
                differences.append(f"{child_path}: unexpected")
            elif key not in actual:
                differences.append(f"{child_path}: missing")
            else:
                differences.extend(
                    _first_differences(
                        expected[key],
                        actual[key],
                        child_path,
                        limit=limit - len(differences),
                    )
                )
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            differences.append(f"{path}: length {len(expected)} != {len(actual)}")
        for index, (left, right) in enumerate(zip(expected, actual)):
            if len(differences) >= limit:
                break
            differences.extend(
                _first_differences(
                    left,
                    right,
                    f"{path}[{index}]",
                    limit=limit - len(differences),
                )
            )
    elif expected != actual:
        differences.append(f"{path}: {expected!r} != {actual!r}")
    return differences[:limit]


def build_comparison(root: Path = GENERATED_ROOT) -> dict[str, Any]:
    validation_errors = validate_dataset(root)
    loaded_documents = load_dataset(root)
    data_quality_warnings = collect_data_quality_warnings(loaded_documents)
    legacy = build_pc_baseline()
    observations = _observations_from_generated(root)
    generated_categories = {
        item.category_id: _generated_category_projection(item)
        for item in observations
    }
    structural_differences: list[str] = []
    for category_id, legacy_category in legacy["categories"].items():
        generated_category = generated_categories.get(category_id)
        if generated_category is None:
            structural_differences.append(f"category {category_id}: missing")
            continue
        expected = _without_legacy_verification(
            _legacy_category_projection(legacy_category)
        )
        structural_differences.extend(
            f"category {category_id} {item}"
            for item in _first_differences(expected, generated_category)
        )
    for category_id in sorted(set(generated_categories) - set(legacy["categories"])):
        structural_differences.append(f"category {category_id}: unexpected")

    planner = CatalogResearchPlanner(observations)
    planning_differences: list[str] = []
    generated_plans: list[dict[str, Any]] = []
    for legacy_plan in legacy["plans"]["plans"]:
        generated_plan = _plan_payload(
            legacy_plan["category_id"],
            legacy_plan["target_research_id"],
            legacy_plan["target_level"],
            planner,
        )
        generated_plans.append(generated_plan)
        expected = _without_legacy_verification(legacy_plan)
        planning_differences.extend(
            f"plan {legacy_plan['category_id']} {item}"
            for item in _first_differences(expected, generated_plan)
        )

    catalog_hash = canonical_json_sha256(
        json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    )
    differences = [
        *(f"validation {item}" for item in validation_errors),
        *structural_differences,
        *planning_differences,
    ]
    return {
        "document_type": "RLMResearchData.legacy-comparison",
        "schema_version": 1,
        "phase": 4,
        "source_catalog_sha256": catalog_hash,
        "dataset_version": loaded_documents["manifest"]["dataset_version"],
        "status": "match" if not differences else "mismatch",
        "statistics": {
            "categories": len(observations),
            "research": sum(len(item.nodes) for item in observations),
            "levels": sum(
                len(node.levels) for item in observations for node in item.nodes
            ),
            "representative_plans": len(generated_plans),
            "validation_differences": len(validation_errors),
            "structural_differences": len(structural_differences),
            "planning_differences": len(planning_differences),
            "data_quality_warnings": len(data_quality_warnings),
        },
        "comparison_policy": {
            "values_compared": [
                "stable IDs and localized names",
                "maximum levels and layout coordinates",
                "raw effects",
                "all level times, costs, requirements, buildings, and power",
                "legacy source edges consumed by the desktop UI",
                "display connection groups",
                "one deterministic dependency plan per tree",
            ],
            "metadata_translation": (
                "Legacy verification labels are intentionally translated to the new "
                "verification vocabulary and are excluded from value equality."
            ),
            "application_runtime_changed": True,
            "desktop_default_input": "generated research dataset",
            "desktop_legacy_fallback": "--legacy-research-catalog",
        },
        "differences": differences,
        "warnings": data_quality_warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare the Phase 4 dataset with the legacy desktop behavior."
    )
    parser.add_argument("--dataset", type=Path, default=GENERATED_ROOT)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    report = build_comparison(args.dataset)
    _write_json(args.report, report)
    print(
        f"Legacy comparison: {report['status']} "
        f"({len(report['differences'])} differences)"
    )
    return 0 if report["status"] == "match" else 1


if __name__ == "__main__":
    raise SystemExit(main())
