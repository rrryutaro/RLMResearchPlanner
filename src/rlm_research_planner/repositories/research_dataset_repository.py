from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rlm_research_planner.domain.observations import ResearchTreeObservation
from rlm_research_planner.repositories.research_dataset_adapter import (
    observations_from_research_dataset,
)


SUPPORTED_DATASET_ID = "lords_mobile_research_data"
SUPPORTED_SCHEMA_VERSION = 2
BUNDLED_DATASET_VERSION = "0.1.0"


class JsonResearchDatasetRepository:
    """Load a bundled, generated research dataset through the shared adapter."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def load_all(self) -> tuple[ResearchTreeObservation, ...]:
        manifest_path = self.root / "manifest.json"
        if not manifest_path.is_file():
            return ()
        try:
            manifest = self._read_json(manifest_path)
            self._expect_document(
                manifest,
                "RLMResearchData.manifest",
                manifest_path,
            )
            if manifest.get("dataset_id") != SUPPORTED_DATASET_ID:
                raise ValueError("unsupported dataset_id")
            if manifest.get("dataset_version") != BUNDLED_DATASET_VERSION:
                raise ValueError(
                    "unsupported dataset_version "
                    f"{manifest.get('dataset_version')!r}; expected "
                    f"{BUNDLED_DATASET_VERSION!r}"
                )
            documents: dict[str, Any] = {
                "manifest": manifest,
                "sources": self._read_relative(
                    str(manifest["sources_path"]),
                    "RLMResearchData.sources",
                ),
                "evidence": self._read_relative(
                    str(manifest["evidence_path"]),
                    "RLMResearchData.evidence",
                ),
                "aliases": self._read_relative(
                    str(manifest["aliases_path"]),
                    "RLMResearchData.aliases",
                ),
                "trees": {},
                "locales": {},
            }
            for entry in manifest["trees"]:
                tree_id = str(entry["id"])
                documents["trees"][tree_id] = self._read_relative(
                    str(entry["path"]),
                    "RLMResearchData.tree",
                )
            for entry in manifest["locales"]:
                locale = str(entry["locale"])
                documents["locales"][locale] = self._read_relative(
                    str(entry["path"]),
                    "RLMResearchData.locale",
                )
            return observations_from_research_dataset(documents)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Invalid research dataset {self.root.name}: {exc}"
            ) from exc

    def _read_relative(self, relative: str, document_type: str) -> Any:
        if not relative or "\\" in relative:
            raise ValueError(f"invalid dataset path: {relative!r}")
        root = self.root.resolve()
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"dataset path escapes its root: {relative}")
        value = self._read_json(path)
        self._expect_document(value, document_type, path)
        return value

    @staticmethod
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _expect_document(value: Any, document_type: str, path: Path) -> None:
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}: root must be an object")
        if value.get("document_type") != document_type:
            raise ValueError(
                f"{path.name}: expected document_type {document_type}"
            )
        if value.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
            raise ValueError(f"{path.name}: unsupported schema_version")
