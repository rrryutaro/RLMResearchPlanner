from __future__ import annotations

from pathlib import Path

import pytest

from rlm_research_planner.repositories.catalog_repository import (
    JsonResearchCatalogRepository,
)
from rlm_research_planner.repositories.research_dataset_repository import (
    JsonResearchDatasetRepository,
)
from rlm_research_planner.app import _load_research_observations, _parser
from rlm_research_planner.paths import AppPaths


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_generated_dataset_repository_preserves_legacy_observations() -> None:
    legacy = JsonResearchCatalogRepository(
        PROJECT_ROOT / "data" / "research" / "catalog.json"
    ).load_all()
    generated = JsonResearchDatasetRepository(
        PROJECT_ROOT / "dataset" / "generated"
    ).load_all()

    assert generated == legacy


def test_desktop_uses_dataset_by_default_and_keeps_legacy_switch() -> None:
    paths = AppPaths(tool_root=PROJECT_ROOT, bundled_root=PROJECT_ROOT)
    assert _parser().parse_args([]).legacy_research_catalog is False
    generated = _load_research_observations(paths, use_legacy=False)
    legacy = _load_research_observations(paths, use_legacy=True)
    assert generated
    assert generated == legacy


def test_dataset_repository_returns_empty_when_manifest_is_absent(
    tmp_path: Path,
) -> None:
    assert JsonResearchDatasetRepository(tmp_path).load_all() == ()


def test_dataset_repository_rejects_paths_outside_dataset_root(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifest.json").write_text(
        """{
          "document_type": "RLMResearchData.manifest",
          "schema_version": 2,
          "dataset_id": "lords_mobile_research_data",
          "dataset_version": "0.1.0",
          "sources_path": "../sources.json",
          "evidence_path": "evidence.json",
          "aliases_path": "id-aliases.json",
          "trees": [],
          "locales": []
        }""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes its root"):
        JsonResearchDatasetRepository(tmp_path).load_all()


def test_dataset_repository_rejects_an_unpinned_content_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = PROJECT_ROOT / "dataset" / "generated"
    repository = JsonResearchDatasetRepository(root)
    original = repository._read_json

    def read_with_future_version(path: Path):
        value = original(path)
        if path.name == "manifest.json":
            value = {**value, "dataset_version": "0.2.0"}
        return value

    monkeypatch.setattr(repository, "_read_json", read_with_future_version)
    with pytest.raises(ValueError, match="unsupported dataset_version"):
        repository.load_all()
