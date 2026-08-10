from __future__ import annotations

import argparse
import os
import sys

from rlm_research_planner.paths import resolve_paths
from rlm_research_planner.repositories.master_repository import JsonMasterRepository
from rlm_research_planner.repositories.catalog_repository import (
    JsonResearchCatalogRepository,
)
from rlm_research_planner.repositories.player_repository import PlayerRepository
from rlm_research_planner.services.localization import Translator
from rlm_research_planner.services.language_pack import LanguagePackRepository
from rlm_research_planner.services.validation import MasterDataValidator
from rlm_research_planner.settings import SettingsRepository
from rlm_research_planner.version import version_string


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="RLMResearchPlanner")
    parser.add_argument("--validate-data", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--updated", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = resolve_paths()
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    observations = catalog
    issues = MasterDataValidator().validate(master)
    errors = [issue for issue in issues if issue.severity == "error"]
    if args.validate_data:
        for issue in issues:
            print(f"{issue.severity}: {issue.code}: {issue.message}")
        return 1 if errors else 0
    if errors:
        for issue in errors:
            print(f"Data error: {issue.code}: {issue.message}", file=sys.stderr)
        return 2

    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QLocale, Qt, QTimer
    from PySide6.QtWidgets import QApplication

    from rlm_research_planner.ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("RLMResearchPlanner")
    app.setApplicationVersion(version_string())
    app.setStyle("Fusion")

    settings_repository = SettingsRepository(None if args.smoke_test else paths.settings_file)
    app_settings = settings_repository.load()
    if not args.smoke_test and not paths.settings_file.exists():
        system_locale = QLocale.system().name().replace("_", "-")
        app_settings.locale = "ja-JP" if system_locale.startswith("ja") else "en-US"
    translator = Translator(
        paths.translations,
        app_settings.locale,
        LanguagePackRepository(None if args.smoke_test else paths.language_packs),
    )
    app.setLayoutDirection(
        Qt.LayoutDirection.RightToLeft
        if translator.direction == "rtl"
        else Qt.LayoutDirection.LeftToRight
    )

    if args.smoke_test:
        player_repository = PlayerRepository(":memory:")
    else:
        paths.user_data.mkdir(parents=True, exist_ok=True)
        player_repository = PlayerRepository(paths.player_database)
    player_state = player_repository.load()
    window = MainWindow(
        paths=paths,
        master=master,
        observations=observations,
        player_repository=player_repository,
        player_state=player_state,
        settings_repository=settings_repository,
        app_settings=app_settings,
        translator=translator,
    )
    window.show()
    if args.smoke_test:
        QTimer.singleShot(50, app.quit)
    try:
        return int(app.exec())
    finally:
        player_repository.close()


if __name__ == "__main__":
    raise SystemExit(main())
