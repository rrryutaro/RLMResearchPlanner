from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from rlm_research_planner.paths import AppPaths
from rlm_research_planner.repositories.catalog_repository import (
    JsonResearchCatalogRepository,
)
from rlm_research_planner.repositories.master_repository import JsonMasterRepository
from rlm_research_planner.repositories.player_repository import PlayerRepository
from rlm_research_planner.services.localization import Translator
from rlm_research_planner.settings import AppSettings, SettingsRepository
from rlm_research_planner.ui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect OCR candidates from a local research-tree screenshot."
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("category")
    parser.add_argument("--locale", default="ja-JP")
    args = parser.parse_args()

    tool_root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=tool_root, bundled_root=tool_root)
    image = QImage(str(args.image))
    if image.isNull():
        parser.error(f"image could not be opened: {args.image}")

    app = QApplication.instance() or QApplication([])
    player_repository = PlayerRepository(":memory:")
    window = MainWindow(
        paths=paths,
        master=JsonMasterRepository(paths.research_data).load(),
        observations=JsonResearchCatalogRepository(paths.research_catalog).load_all(),
        player_repository=player_repository,
        player_state=player_repository.load(),
        settings_repository=SettingsRepository(None),
        app_settings=AppSettings(locale=args.locale),
        translator=Translator(paths.translations, args.locale),
    )
    try:
        row = window._dataset_list_row(f"observation:catalog-{args.category}")
        if row < 0:
            parser.error(f"unknown category: {args.category}")
        window.tree_dataset_list.setCurrentRow(row)
        window._set_ocr_image(image, source="file")
        window._run_ocr()
        meter_regions = {
            (region.x(), region.y(), region.width(), region.height()): fill_ratio
            for region, fill_ratio in window._research_card_meter_regions(image)
        }
        print(
            json.dumps(
                {
                    "candidates": [
                    {
                        "research_id": candidate.research_id,
                        "level": candidate.level,
                        "evidence": candidate.evidence,
                    }
                    for candidate in window._ocr_candidates
                    ],
                    "cards": [
                        {
                            "region": [
                                region.x(),
                                region.y(),
                                region.width(),
                                region.height(),
                            ],
                            "fill_ratio": meter_regions.get(
                                (
                                    region.x(),
                                    region.y(),
                                    region.width(),
                                    region.height(),
                                )
                            ),
                            "lines": [line.text for line in lines],
                        }
                        for region, lines in window._ocr_card_groups
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        window.close()
        player_repository.close()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
