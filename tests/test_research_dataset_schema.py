from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = PROJECT_ROOT / "dataset"
EXAMPLE_ROOT = DATASET_ROOT / "examples" / "minimal"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validator() -> ModuleType:
    return _load_module(
        "rlm_validate_research_dataset",
        DATASET_ROOT / "scripts" / "validate_dataset.py",
    )


def _documents() -> tuple[ModuleType, dict[str, object]]:
    validator = _validator()
    return validator, validator.load_dataset(EXAMPLE_ROOT)


def test_phase_one_schema_set_has_resolvable_references() -> None:
    validator = _validator()
    assert validator.validate_schema_documents() == []
    schemas = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((DATASET_ROOT / "schemas").glob("*.schema.json"))
    ]
    assert len(schemas) == 7
    assert len({item["$id"] for item in schemas}) == len(schemas)


def test_minimal_nonempty_dataset_passes_semantic_validation() -> None:
    validator = _validator()
    assert validator.validate_dataset(EXAMPLE_ROOT) == []


def test_research_facts_do_not_contain_localized_display_names() -> None:
    validator = _validator()
    documents = validator.load_dataset(DATASET_ROOT / "generated")
    forbidden = {"name", "names", "title", "titles", "display_name", "localized_names"}

    def inspect(value: object, path: str) -> list[str]:
        errors: list[str] = []
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{path}.{key}"
                if key in forbidden:
                    errors.append(child)
                errors.extend(inspect(item, child))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                errors.extend(inspect(item, f"{path}[{index}]"))
        return errors

    assert not [
        item
        for tree_id, tree in documents["trees"].items()
        for item in inspect(tree, f"tree {tree_id}")
    ]


def test_optional_rtl_locale_can_be_added_without_changing_research_facts() -> None:
    validator, documents = _documents()
    broken = copy.deepcopy(documents)
    english = copy.deepcopy(broken["locales"]["en-US"])
    english["locale"] = "ar"
    english["direction"] = "rtl"
    english["fallback_locale"] = "en-US"
    english["research"] = {
        "economy_construction_speed": "سرعة البناء",
    }
    english["trees"] = {"economy": "الاقتصاد"}
    english["metrics"] = {}
    broken["locales"]["ar"] = english
    assert validator.validate_documents(broken) == []


def test_json_schema_rejects_unknown_fields_and_wrong_document_type() -> None:
    validator, documents = _documents()
    broken = copy.deepcopy(documents)
    broken["trees"]["economy"]["nodes"][0]["unexpected"] = True
    broken["locales"]["en-US"]["document_type"] = "wrong"
    broken["locales"]["en-US"]["research"][
        "economy_construction_speed"
    ] = "Construction\nSpeed"
    errors = validator.validate_schema_instances(broken)
    assert any("unexpected" in error and "not allowed" in error for error in errors)
    assert any("locale en-US.document_type" in error for error in errors)
    assert any("locale en-US.research.economy_construction_speed" in error for error in errors)


def test_non_monotonic_values_are_reported_without_being_rewritten() -> None:
    validator, documents = _documents()
    tree = documents["trees"]["economy"]
    node = tree["nodes"][0]
    node["max_level"] = 2
    node["levels"].append(
        {
            "level": 2,
            "academy_level": 1,
            "base_time_seconds": 1,
            "technolabe_count": 1,
            "power": 1,
            "costs": {"food": 1},
            "prerequisites": [],
            "buildings": {},
        }
    )
    node["levels"][0]["base_time_seconds"] = 2
    node["levels"][0]["costs"]["food"] = 2
    warnings = validator.collect_data_quality_warnings(documents)
    assert any(item["field"] == "base_time_seconds" for item in warnings)
    assert any(item["field"] == "costs.food" for item in warnings)
    assert validator.validate_documents(documents) == []


def test_empty_costs_and_reverse_display_rows_are_review_warnings() -> None:
    validator, documents = _documents()
    tree = documents["trees"]["economy"]
    first = tree["nodes"][0]
    first["layout"]["row"] = 1
    first["levels"][0]["costs"] = {}
    second = copy.deepcopy(first)
    second["id"] = "economy_second"
    second["layout"] = {"row": 0, "column": 1}
    second["levels"] = []
    second["effects"] = []
    tree["nodes"].append(second)
    tree["display_connections"] = [
        {
            "from_ids": [first["id"]],
            "to_ids": [second["id"]],
            "verification": tree["default_verification"],
        }
    ]
    warnings = validator.collect_data_quality_warnings(documents)
    assert any(item["code"] == "empty_verified_costs" for item in warnings)
    assert any(
        item["code"] == "display_connection_reverses_rows" for item in warnings
    )


def test_unparsed_effect_requires_text_unit_and_display_fallback() -> None:
    validator, documents = _documents()
    broken = copy.deepcopy(documents)
    effect = broken["trees"]["economy"]["nodes"][0]["effects"][0]
    effect["parsed"] = False
    effect["unit"] = "percent"
    effect["values"][0].pop("display_fallback", None)
    errors = validator.validate_documents(broken)
    assert any("unparsed effect must use text unit" in error for error in errors)
    assert any("unparsed effect needs display fallback" in error for error in errors)


def test_unknown_prerequisite_is_rejected() -> None:
    validator, documents = _documents()
    broken = copy.deepcopy(documents)
    broken["trees"]["economy"]["nodes"][0]["levels"][0][
        "prerequisites"
    ] = [{"research_id": "economy_missing", "level": 1}]
    assert any(
        "unknown prerequisite economy_missing" in error
        for error in validator.validate_documents(broken)
    )


def test_unknown_source_edge_and_structure_only_data_are_rejected() -> None:
    validator, documents = _documents()
    broken = copy.deepcopy(documents)
    tree = broken["trees"]["economy"]
    tree["source_edges"] = [
        {
            "prerequisite_id": tree["nodes"][0]["id"],
            "research_id": "economy_missing",
            "verification": tree["default_verification"],
        }
    ]
    tree["coverage"] = "structure_only"
    errors = validator.validate_documents(broken)
    assert any("source edge 0: unknown local research id" in error for error in errors)
    assert any("structure_only tree contains level data" in error for error in errors)


def test_prerequisite_cycle_is_rejected() -> None:
    validator, documents = _documents()
    broken = copy.deepcopy(documents)
    node = broken["trees"]["economy"]["nodes"][0]
    node["levels"][0]["prerequisites"] = [
        {"research_id": node["id"], "level": 1}
    ]
    errors = validator.validate_documents(broken)
    assert any("self prerequisite" in error for error in errors)
    assert any("cycle detected" in error for error in errors)


def test_complete_tree_level_gap_is_rejected() -> None:
    validator, documents = _documents()
    broken = copy.deepcopy(documents)
    broken["trees"]["economy"]["coverage"] = "complete"
    assert any(
        "complete tree has level gaps" in error
        for error in validator.validate_documents(broken)
    )


def test_negative_cost_is_rejected_without_treating_unknown_as_zero() -> None:
    validator, documents = _documents()
    broken = copy.deepcopy(documents)
    level = broken["trees"]["economy"]["nodes"][0]["levels"][0]
    level["costs"]["food"] = -1
    errors = validator.validate_documents(broken)
    assert any("invalid cost food" in error for error in errors)
    level["costs"] = None
    assert not any(
        "invalid cost" in error for error in validator.validate_documents(broken)
    )


def test_verification_procedure_rules_are_enforced() -> None:
    validator, documents = _documents()
    broken = copy.deepcopy(documents)
    verification = broken["trees"]["economy"]["default_verification"]
    verification.clear()
    verification["status"] = "verified"
    assert any(
        "verified facts require direct evidence" in error
        for error in validator.validate_documents(broken)
    )
    verification.clear()
    verification["status"] = "cross_checked"
    verification["source_ids"] = ["src_fandom_economy"]
    assert any(
        "cross_checked facts require two references" in error
        for error in validator.validate_documents(broken)
    )
    verification.clear()
    verification["status"] = "disputed"
    assert any(
        "disputed facts require notes" in error
        for error in validator.validate_documents(broken)
    )


def test_alias_cycle_and_unknown_locale_id_are_rejected() -> None:
    validator, documents = _documents()
    broken = copy.deepcopy(documents)
    broken["aliases"]["aliases"] = {
        "old_one": "old_two",
        "old_two": "old_one",
    }
    broken["locales"]["ja-JP"]["research"]["unknown_research"] = "不明"
    errors = validator.validate_documents(broken)
    assert any("aliases: cycle detected" in error for error in errors)
    assert any("contains unknown research IDs" in error for error in errors)
