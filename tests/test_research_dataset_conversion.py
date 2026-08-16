from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = PROJECT_ROOT / "dataset"
GENERATED_ROOT = DATASET_ROOT / "generated"
BASELINE_ROOT = DATASET_ROOT / "baseline"
COMPARISON_REPORT = DATASET_ROOT / "reports" / "legacy-vs-generated.json"
UPDATE_GATE_REPORT = DATASET_ROOT / "reports" / "catalog-update-gate.json"
CATALOG_PATH = PROJECT_ROOT / "data" / "research" / "catalog.json"
PRIVATE_OBSERVATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "research"
    / "observations"
    / "economy_tree_ja-JP_2026-08-06.json"
)
GUILD_DUEL_OBSERVATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "research"
    / "observations"
    / "guild_duel_levels_ja-JP_2026-08-11.json"
)
GUILD_DUEL_ADDITIONAL_OBSERVATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "research"
    / "observations"
    / "guild_duel_levels_ja-JP_2026-08-15.json"
)


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _converter() -> ModuleType:
    return _load_module(
        "rlm_convert_legacy_research_catalog",
        DATASET_ROOT / "scripts" / "convert_legacy_catalog.py",
    )


def _validator() -> ModuleType:
    return _load_module(
        "rlm_validate_generated_research_dataset",
        DATASET_ROOT / "scripts" / "validate_dataset.py",
    )


def _comparator() -> ModuleType:
    return _load_module(
        "rlm_compare_legacy_and_generated_research",
        DATASET_ROOT / "scripts" / "compare_legacy_and_generated.py",
    )


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_generated_dataset_is_valid_and_has_frozen_identity_counts() -> None:
    validator = _validator()
    assert validator.validate_dataset(GENERATED_ROOT) == []

    documents = validator.load_dataset(GENERATED_ROOT)
    research_ids = {
        node["id"]
        for tree in documents["trees"].values()
        for node in tree["nodes"]
    }
    level_count = sum(
        len(node["levels"])
        for tree in documents["trees"].values()
        for node in tree["nodes"]
    )
    frozen_ids = {item["id"] for item in _read_json(BASELINE_ROOT / "research-ids.json")}

    assert len(documents["trees"]) == 16
    assert research_ids == frozen_ids
    assert len(research_ids) == 399
    assert level_count == 3179


def test_checked_in_generated_files_equal_fresh_in_memory_conversion() -> None:
    if not PRIVATE_OBSERVATION_PATH.is_file():
        pytest.skip("Private conversion inputs are not included in public releases.")
    converter = _converter()
    generated = converter.build_generated_dataset()

    assert _read_json(GENERATED_ROOT / "manifest.json") == generated["manifest"]
    assert _read_json(GENERATED_ROOT / "sources.json") == generated["sources"]
    assert _read_json(GENERATED_ROOT / "evidence.json") == generated["evidence"]
    assert _read_json(GENERATED_ROOT / "id-aliases.json") == generated["aliases"]
    for tree_id, tree in generated["trees"].items():
        assert _read_json(GENERATED_ROOT / "trees" / f"{tree_id}.json") == tree
    for locale, document in generated["locales"].items():
        assert _read_json(GENERATED_ROOT / "locales" / f"{locale}.json") == document


def test_generated_file_set_has_no_stale_json_documents() -> None:
    converter = _converter()
    generated = converter.build_generated_dataset()
    expected = {
        "manifest.json",
        "sources.json",
        "evidence.json",
        "id-aliases.json",
        *{f"trees/{tree_id}.json" for tree_id in generated["trees"]},
        *{f"locales/{locale}.json" for locale in generated["locales"]},
    }
    actual = {
        path.relative_to(GENERATED_ROOT).as_posix()
        for path in GENERATED_ROOT.rglob("*.json")
    }
    assert actual == expected


def test_current_ids_are_explicit_and_alias_map_starts_empty() -> None:
    converter = _converter()
    generated = converter.build_generated_dataset()
    current_ids = {
        node["id"]
        for tree in generated["trees"].values()
        for node in tree["nodes"]
    }
    assert generated["aliases"]["aliases"] == {}
    assert all(node_id.startswith(f"{tree_id}_") for tree_id, tree in generated["trees"].items() for node_id in (node["id"] for node in tree["nodes"]))
    assert len(current_ids) == 399


def test_display_connections_remain_separate_and_provisional() -> None:
    converter = _converter()
    generated = converter.build_generated_dataset()
    for tree in generated["trees"].values():
        for connection in tree["display_connections"]:
            assert connection["verification"]["status"] == "provisional"
            assert connection["from_ids"]
            assert connection["to_ids"]
            assert "prerequisites" not in connection
        for edge in tree["source_edges"]:
            assert edge["verification"]["status"] == "provisional"
            assert edge["prerequisite_id"]
            assert edge["research_id"]


def test_generated_values_and_representative_plans_match_legacy_behavior() -> None:
    comparator = _comparator()
    report = comparator.build_comparison(GENERATED_ROOT)
    assert report["phase"] == 4
    assert report["comparison_policy"]["application_runtime_changed"] is True
    assert report["status"] == "match"
    assert report["differences"] == []
    assert {
        key: report["statistics"][key]
        for key in (
            "categories",
            "research",
            "levels",
            "representative_plans",
            "validation_differences",
            "structural_differences",
            "planning_differences",
        )
    } == {
        "categories": 16,
        "research": 399,
        "levels": 3179,
        "representative_plans": 16,
        "validation_differences": 0,
        "structural_differences": 0,
        "planning_differences": 0,
    }
    assert report["statistics"]["data_quality_warnings"] == len(report["warnings"])
    warning_codes = {item["code"] for item in report["warnings"]}
    assert "level_value_decreased" in warning_codes
    assert "empty_verified_costs" in warning_codes
    assert _read_json(COMPARISON_REPORT) == report


def test_legacy_source_edges_and_guild_duel_license_are_preserved() -> None:
    converter = _converter()
    generated = converter.build_generated_dataset()
    baseline = {
        path.stem: _read_json(path)
        for path in (BASELINE_ROOT / "pc" / "categories").glob("*.json")
    }
    for tree_id, tree in generated["trees"].items():
        actual = [
            [edge["prerequisite_id"], edge["research_id"]]
            for edge in tree["source_edges"]
        ]
        assert actual == baseline[tree_id]["source_edges"]
    sources = {item["id"]: item for item in generated["sources"]["sources"]}
    guild_source = sources["src_bigsoneca_guild_duel_video"]
    assert guild_source["license"]["name"] == (
        "Public gameplay reference (facts transcribed)"
    )


def test_guild_duel_capture_is_private_evidence_for_provisional_level_data() -> None:
    if not GUILD_DUEL_OBSERVATION_PATH.is_file():
        pytest.skip("private Guild Duel observation is not included in public source")
    converter = _converter()
    generated = converter.build_generated_dataset()
    evidence_id = "evidence_guild_duel_levels_ja_jp_2026_08_11_01"
    evidence = {
        item["id"]: item for item in generated["evidence"]["evidence"]
    }[evidence_id]
    assert GUILD_DUEL_OBSERVATION_PATH.is_file()
    assert evidence["captured_on"] == "2026-08-11"
    assert evidence["locale"] == "ja-JP"
    assert evidence["redistribution_allowed"] is False
    assert "path" not in evidence

    guild_duel = generated["trees"]["guild_duel"]
    research = next(
        item
        for item in guild_duel["nodes"]
        if item["id"] == "guild_duel_research_incentive"
    )
    level_one = research["levels"][0]
    assert level_one["base_time_seconds"] == 7_745
    assert level_one["costs"]["special"] == 10
    assert level_one["verification"]["status"] == "provisional"
    assert level_one["verification"]["checked_on"] == "2026-08-11"
    assert level_one["verification"]["evidence_ids"] == [evidence_id]
    assert generated["locales"]["ja-JP"]["metrics"][research["id"]] == (
        "研究デュエルポイント"
    )


def test_additional_guild_duel_capture_and_tome_inference_keep_provenance() -> None:
    if not GUILD_DUEL_ADDITIONAL_OBSERVATION_PATH.is_file():
        pytest.skip("private Guild Duel observation is not included in public source")
    converter = _converter()
    generated = converter.build_generated_dataset()
    evidence_id = "evidence_guild_duel_levels_ja_jp_2026_08_15_01"
    evidence = {
        item["id"]: item for item in generated["evidence"]["evidence"]
    }[evidence_id]
    assert GUILD_DUEL_ADDITIONAL_OBSERVATION_PATH.is_file()
    assert evidence["captured_on"] == "2026-08-15"
    assert evidence["redistribution_allowed"] is False
    assert "path" not in evidence

    guild_duel = generated["trees"]["guild_duel"]
    nodes = {item["id"]: item for item in guild_duel["nodes"]}
    speed_up = nodes["guild_duel_speed_up_incentive"]["levels"][0]
    assert speed_up["base_time_seconds"] == 6_372
    assert speed_up["costs"]["special"] == 20
    assert speed_up["verification"]["evidence_ids"] == [evidence_id]
    reward_two = nodes["guild_duel_reward_incentive_ii"]["levels"][0]
    assert reward_two["base_time_seconds"] == 669_731
    assert reward_two["costs"]["food"] == 12_000_000
    assert reward_two["verification"]["evidence_ids"] == [evidence_id]

    gathering = nodes["guild_duel_gathering_incentive"]["levels"][0]
    assert gathering["base_time_seconds"] == 7_745
    assert gathering["costs"] == {
        "food": 78_600,
        "stone": 32_600,
        "timber": 39_100,
        "ore": 19_600,
        "gold": 32_600,
        "special": 10,
    }
    assert gathering["verification"]["status"] == "provisional"
    assert gathering["verification"]["evidence_ids"] == [
        "evidence_guild_duel_levels_ja_jp_2026_08_11_01",
        "evidence_guild_duel_levels_ja_jp_2026_08_15_02",
    ]
    assert "verification_overrides" not in gathering
    sources = {item["id"]: item for item in generated["sources"]["sources"]}
    assert sources["src_neovis_guild_duel_research"]["url"] == (
        "https://neovis99.com/lords-mobile-capture-part151/"
    )


def test_fact_specific_cost_source_is_preserved_as_provisional_override() -> None:
    converter = _converter()
    generated = converter.build_generated_dataset()
    sources = {item["id"]: item for item in generated["sources"]["sources"]}
    source_id = "src_fandom_sigils_furious_defense_infantry"
    assert sources[source_id]["url"] == (
        "https://lordsmobile.fandom.com/wiki/Furious_Defense_%28Infantry%29"
    )

    tree = generated["trees"]["sigils"]
    node = next(
        item
        for item in tree["nodes"]
        if item["id"] == "sigils_furious_defense_infantry"
    )
    level = next(item for item in node["levels"] if item["level"] == 3)
    assert level["verification_overrides"]["costs"]["status"] == "provisional"
    assert level["verification_overrides"]["costs"]["source_ids"] == [source_id]

    helmet_source_id = "src_fandom_sigils_helmet_sigil"
    assert sources[helmet_source_id]["url"] == (
        "https://lordsmobile.fandom.com/wiki/Helmet_Sigil"
    )
    helmet = next(
        item for item in tree["nodes"] if item["id"] == "sigils_helmet_sigil"
    )
    helmet_level = next(item for item in helmet["levels"] if item["level"] == 1)
    assert helmet_level["costs"] == {
        "food": 8_137_320,
        "stone": 4_068_660,
        "timber": 4_068_660,
        "ore": 1_356_220,
        "gold": 3_904_320,
        "ancient_tomes": 96,
    }
    assert set(helmet_level["verification_overrides"]) == {
        "time",
        "costs",
        "requirements",
    }
    assert all(
        verification["source_ids"] == [helmet_source_id]
        and verification["status"] == "provisional"
        for verification in helmet_level["verification_overrides"].values()
    )


def test_catalog_update_gate_records_two_distinct_matching_revisions() -> None:
    gate = _read_json(UPDATE_GATE_REPORT)
    assert gate["required_updates"] == 2
    assert len(gate["updates"]) >= gate["required_updates"]
    hashes = [item["catalog_sha256"] for item in gate["updates"]]
    assert len(hashes) == len(set(hashes))
    assert all(item["comparison_status"] == "match" for item in gate["updates"])
    assert all(item["differences"] == 0 for item in gate["updates"])
    catalog = _read_json(CATALOG_PATH)
    exporter = _load_module(
        "rlm_export_pc_research_baseline",
        DATASET_ROOT / "scripts" / "export_pc_baseline.py",
    )
    assert hashes[-1] == exporter.canonical_json_sha256(catalog)
