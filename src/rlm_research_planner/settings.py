from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


DEFAULT_OCR_WINDOW_TITLE = "Lords Mobile PC"
DEFAULT_VISUAL_STYLE = "desktop"
VISUAL_STYLES = frozenset(("desktop", "mobile"))
FONT_SIZE_MIN = 8
FONT_SIZE_MAX = 72
DEFAULT_UI_FONT_SIZE = 11
DEFAULT_TABLE_FONT_SIZE = 11
DEFAULT_TREE_FONT_SIZE = 20
DEFAULT_HELP_FONT_SIZE = 12


def normalize_visual_style(value: object) -> str:
    normalized = str(value).strip().lower()
    return normalized if normalized in VISUAL_STYLES else DEFAULT_VISUAL_STYLE


@dataclass
class WindowGeometry:
    x: int = 120
    y: int = 80
    width: int = 1280
    height: int = 820


@dataclass
class AppSettings:
    locale: str = ""
    visual_style: str = DEFAULT_VISUAL_STYLE
    ocr_window_title: str = DEFAULT_OCR_WINDOW_TITLE
    ui_font_size: int = DEFAULT_UI_FONT_SIZE
    table_font_size: int = DEFAULT_TABLE_FONT_SIZE
    tree_font_size: int = DEFAULT_TREE_FONT_SIZE
    help_font_size: int = DEFAULT_HELP_FONT_SIZE
    talent_auto_follow: bool = True
    update_check_on_startup: bool = True
    update_skipped_version: str = ""
    window: WindowGeometry = field(default_factory=WindowGeometry)


class SettingsRepository:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    def load(self) -> AppSettings:
        if self.path is None or not self.path.is_file():
            return AppSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            window = raw.get("window", {})
            return AppSettings(
                locale=str(raw.get("locale", "")),
                visual_style=normalize_visual_style(
                    raw.get("visual_style", DEFAULT_VISUAL_STYLE)
                ),
                ocr_window_title=str(
                    raw.get("ocr_window_title", DEFAULT_OCR_WINDOW_TITLE)
                ),
                ui_font_size=max(
                    FONT_SIZE_MIN,
                    min(
                        FONT_SIZE_MAX,
                        int(
                            raw.get(
                                "ui_font_size",
                                raw.get(
                                    "speedup_font_size",
                                    DEFAULT_UI_FONT_SIZE,
                                ),
                            )
                        ),
                    ),
                ),
                table_font_size=max(
                    FONT_SIZE_MIN,
                    min(
                        FONT_SIZE_MAX,
                        int(raw.get("table_font_size", DEFAULT_TABLE_FONT_SIZE)),
                    ),
                ),
                tree_font_size=max(
                    FONT_SIZE_MIN,
                    min(
                        FONT_SIZE_MAX,
                        int(raw.get("tree_font_size", DEFAULT_TREE_FONT_SIZE)),
                    ),
                ),
                help_font_size=max(
                    FONT_SIZE_MIN,
                    min(
                        FONT_SIZE_MAX,
                        int(raw.get("help_font_size", DEFAULT_HELP_FONT_SIZE)),
                    ),
                ),
                talent_auto_follow=bool(raw.get("talent_auto_follow", True)),
                update_check_on_startup=bool(
                    raw.get("update_check_on_startup", True)
                ),
                update_skipped_version=str(raw.get("update_skipped_version", "")),
                window=WindowGeometry(
                    x=int(window.get("x", 120)),
                    y=int(window.get("y", 80)),
                    width=int(window.get("width", 1280)),
                    height=int(window.get("height", 820)),
                ),
            )
        except (OSError, ValueError, TypeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        if self.path is None:
            return
        self.path.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
