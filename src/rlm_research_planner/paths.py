from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    tool_root: Path
    bundled_root: Path

    @property
    def research_data(self) -> Path:
        return self.bundled_root / "data" / "research"

    @property
    def research_observations(self) -> Path:
        return self.research_data / "observations"

    @property
    def research_catalog(self) -> Path:
        return self.research_data / "catalog.json"

    @property
    def castle_catalog(self) -> Path:
        return self.bundled_root / "data" / "buildings" / "castle_catalog.json"

    @property
    def ocr_profiles(self) -> Path:
        return self.bundled_root / "data" / "ocr" / "profiles"

    @property
    def translations(self) -> Path:
        return self.bundled_root / "resources" / "i18n"

    @property
    def windows_ocr_script(self) -> Path:
        return self.bundled_root / "resources" / "scripts" / "windows_ocr.ps1"

    @property
    def user_data(self) -> Path:
        return self.tool_root / "user_data"

    @property
    def player_database(self) -> Path:
        return self.user_data / "player.sqlite3"

    @property
    def settings_file(self) -> Path:
        return self.tool_root / "settings.json"


def resolve_paths() -> AppPaths:
    if getattr(sys, "frozen", False):
        tool_root = Path(sys.executable).resolve().parent
        bundled_root = Path(getattr(sys, "_MEIPASS", tool_root))
        return AppPaths(tool_root=tool_root, bundled_root=bundled_root)
    tool_root = Path(__file__).resolve().parents[2]
    return AppPaths(tool_root=tool_root, bundled_root=tool_root)
