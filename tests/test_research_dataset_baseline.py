from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_ROOT = PROJECT_ROOT / "dataset" / "baseline"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_checked_in_pc_research_baseline_matches_current_loader() -> None:
    exporter = _load_module(
        "rlm_export_pc_research_baseline",
        PROJECT_ROOT / "dataset" / "scripts" / "export_pc_baseline.py",
    )
    baseline = exporter.build_pc_baseline()

    assert baseline["manifest"] == _load_json(BASELINE_ROOT / "manifest.json")
    assert baseline["research_ids"] == _load_json(
        BASELINE_ROOT / "research-ids.json"
    )
    for category_id, payload in baseline["categories"].items():
        assert payload == _load_json(
            BASELINE_ROOT / "pc" / "categories" / f"{category_id}.json"
        )
    assert baseline["plans"] == _load_json(BASELINE_ROOT / "pc" / "plans.json")


def test_platform_difference_report_matches_both_checked_in_baselines() -> None:
    comparator = _load_module(
        "rlm_compare_research_platform_baselines",
        PROJECT_ROOT
        / "dataset"
        / "scripts"
        / "compare_platform_baselines.py",
    )
    report = comparator.build_difference_report()

    assert report == _load_json(BASELINE_ROOT / "platform-differences.json")
    assert report["catalog_hashes"]["match"] is True
    assert report["missing_categories"] == {"pc": [], "pwa": []}
    assert report["shared_data_differences"] == []
