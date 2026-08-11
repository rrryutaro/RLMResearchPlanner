from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE_ROOT = PROJECT_ROOT / "dataset" / "baseline"
DOCUMENT_TYPE = "RLMResearchPlanner.research-platform-differences"
SCHEMA_VERSION = 1


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _category_files(platform: str) -> dict[str, Path]:
    directory = BASELINE_ROOT / platform / "categories"
    return {path.stem: path for path in sorted(directory.glob("*.json"))}


def _shared_level(level: dict[str, Any]) -> dict[str, Any]:
    return {
        key: level.get(key)
        for key in (
            "level",
            "academy_level",
            "base_time_seconds",
            "technolabe_count",
            "costs",
            "power",
            "requirements",
            "buildings",
            "costs_verified",
        )
    }


def _shared_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node.get("id"),
        "names": node.get("names"),
        "max_level": node.get("max_level"),
        "row": node.get("row"),
        "column": node.get("column"),
        "effect_label": node.get("effect_label"),
        "effect_values": node.get("effect_values"),
        "levels": [_shared_level(level) for level in node.get("levels", [])],
    }


def _shared_plan_step(step: dict[str, Any]) -> dict[str, Any]:
    shared = {
        key: step.get(key)
        for key in (
            "research_id",
            "level",
            "base_time_seconds",
            "adjusted_time_seconds",
            "after_help_seconds",
            "costs",
            "costs_verified",
            "technolabe_count",
            "technolabe_efficiency_percent",
        )
    }
    shared["costs"] = {
        key: value
        for key, value in sorted((step.get("costs") or {}).items())
        if int(value) != 0
    }
    return shared


def _shared_plan(plan: dict[str, Any]) -> dict[str, Any]:
    totals = plan.get("totals", {})
    shared = {
        "category_id": plan.get("category_id"),
        "target_research_id": plan.get("target_research_id"),
        "target_level": plan.get("target_level"),
        "required_levels": plan.get("required_levels"),
        "steps": [_shared_plan_step(step) for step in plan.get("steps", [])],
        "totals": {
            key: totals.get(key)
            for key in (
                "base_time_seconds",
                "adjusted_time_seconds",
                "after_help_seconds",
                "costs",
                "unknown_time_steps",
                "unknown_cost_steps",
                "unknown_technolabe_steps",
                "technolabe_count",
                "technolabe_base_seconds",
                "technolabe_efficiency_percent",
            )
        },
    }
    shared["totals"]["costs"] = {
        key: value
        for key, value in sorted((totals.get("costs") or {}).items())
        if int(value) != 0
    }
    return shared


def build_difference_report() -> dict[str, Any]:
    pc_files = _category_files("pc")
    pwa_files = _category_files("pwa")
    category_ids = sorted(set(pc_files) | set(pwa_files))
    missing_categories = {
        "pc": sorted(set(pwa_files) - set(pc_files)),
        "pwa": sorted(set(pc_files) - set(pwa_files)),
    }
    shared_data_differences: list[dict[str, Any]] = []
    metadata_differences: list[dict[str, Any]] = []
    connection_differences: list[dict[str, Any]] = []
    pc_hashes: set[str] = set()
    pwa_hashes: set[str] = set()

    for category_id in sorted(set(pc_files) & set(pwa_files)):
        pc = _load(pc_files[category_id])
        pwa = _load(pwa_files[category_id])
        pc_hashes.add(str(pc.get("source_catalog_sha256", "")))
        pwa_hashes.add(str(pwa.get("source_catalog_sha256", "")))
        if [_shared_node(node) for node in pc.get("nodes", [])] != [
            _shared_node(node) for node in pwa.get("nodes", [])
        ]:
            shared_data_differences.append(
                {"category_id": category_id, "field": "nodes"}
            )
        for field in ("verification_status", "scope"):
            if pc.get(field) != pwa.get(field):
                metadata_differences.append(
                    {
                        "category_id": category_id,
                        "field": field,
                        "pc": pc.get(field),
                        "pwa": pwa.get(field),
                    }
                )
        pc_pairs = {tuple(pair) for pair in pc.get("display_connections", [])}
        pwa_pairs = {tuple(pair) for pair in pwa.get("display_connections", [])}
        if pc_pairs != pwa_pairs:
            connection_differences.append(
                {
                    "category_id": category_id,
                    "pc_only": [list(pair) for pair in sorted(pc_pairs - pwa_pairs)],
                    "pwa_only": [list(pair) for pair in sorted(pwa_pairs - pc_pairs)],
                }
            )

    pc_plans = {
        plan["category_id"]: plan
        for plan in _load(BASELINE_ROOT / "pc" / "plans.json")["plans"]
    }
    pwa_plans = {
        plan["category_id"]: plan
        for plan in _load(BASELINE_ROOT / "pwa" / "plans.json")["plans"]
    }
    plan_differences = [
        {"category_id": category_id, "field": "representative_plan"}
        for category_id in sorted(set(pc_plans) | set(pwa_plans))
        if category_id not in pc_plans
        or category_id not in pwa_plans
        or _shared_plan(pc_plans[category_id])
        != _shared_plan(pwa_plans[category_id])
    ]
    return {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "category_ids": category_ids,
        "catalog_hashes": {
            "pc": sorted(pc_hashes),
            "pwa": sorted(pwa_hashes),
            "match": pc_hashes == pwa_hashes and len(pc_hashes) == 1,
        },
        "missing_categories": missing_categories,
        "shared_data_differences": shared_data_differences,
        "metadata_differences": metadata_differences,
        "display_connection_differences": connection_differences,
        "representative_plan_differences": plan_differences,
        "known_runtime_policy_differences": [],
    }


def write_difference_report(report: dict[str, Any]) -> None:
    path = BASELINE_ROOT / "platform-differences.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    report = build_difference_report()
    write_difference_report(report)
    print(
        "Platform difference report generated: "
        f"{len(report['display_connection_differences'])} tree connection differences"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
