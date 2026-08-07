from __future__ import annotations

import json
from pathlib import Path

from rlm_research_planner.domain.models import (
    LocaleData,
    LocalizedCategory,
    LocalizedResearch,
    MasterData,
    Prerequisite,
    Research,
    ResearchCategory,
    ResearchLevel,
)


class JsonMasterRepository:
    def __init__(self, data_directory: Path) -> None:
        self.data_directory = Path(data_directory)

    def load(self) -> MasterData:
        master_path = self.data_directory / "master.json"
        raw = json.loads(master_path.read_text(encoding="utf-8"))
        locales = self._load_locales()
        return MasterData(
            dataset_id=str(raw["metadata"]["dataset_id"]),
            dataset_status=str(raw["metadata"]["dataset_status"]),
            game_version=str(raw["metadata"]["game_version"]),
            categories=tuple(ResearchCategory(**item) for item in raw["categories"]),
            research=tuple(
                Research(
                    **{
                        **item,
                        "tags": tuple(item.get("tags", [])),
                        "purposes": tuple(item.get("purposes", [])),
                    }
                )
                for item in raw["research"]
            ),
            levels=tuple(
                ResearchLevel(
                    research_id=item["research_id"],
                    level=int(item["level"]),
                    academy_level=int(item["academy_level"]),
                    base_time_seconds=int(item["base_time_seconds"]),
                    resources={key: int(value) for key, value in item["resources"].items()},
                    ancient_tomes=int(item.get("ancient_tomes", 0)),
                    power=int(item["power"]),
                    effect_value=float(item["effect_value"]),
                    cumulative_effect=float(item["cumulative_effect"]),
                    source=str(item["source"]),
                    checked_on=str(item["checked_on"]),
                    game_version=str(item["game_version"]),
                    verification_status=str(item["verification_status"]),
                    notes=str(item.get("notes", "")),
                )
                for item in raw["levels"]
            ),
            prerequisites=tuple(Prerequisite(**item) for item in raw["prerequisites"]),
            locales=locales,
        )

    def _load_locales(self) -> dict[str, LocaleData]:
        result: dict[str, LocaleData] = {}
        locale_directory = self.data_directory / "locales"
        for path in sorted(locale_directory.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            locale = str(raw["locale"])
            result[locale] = LocaleData(
                categories={
                    key: LocalizedCategory(**value)
                    for key, value in raw.get("categories", {}).items()
                },
                research={
                    key: LocalizedResearch(**value)
                    for key, value in raw.get("research", {}).items()
                },
            )
        return result
