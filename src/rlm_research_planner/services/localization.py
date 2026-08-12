from __future__ import annotations

import json
from pathlib import Path

from rlm_research_planner.services.language_pack import (
    LanguagePack,
    LanguagePackRepository,
    default_direction,
)


class Translator:
    def __init__(
        self,
        resources_directory: Path,
        locale: str = "ja-JP",
        language_pack_repository: LanguagePackRepository | None = None,
    ) -> None:
        self.resources_directory = Path(resources_directory)
        self.language_pack_repository = language_pack_repository
        self.locale = locale
        self._messages: dict[str, str] = {}
        self._effect_labels: dict[str, str] = {}
        self._packs: dict[str, LanguagePack] = {}
        self._active_pack: LanguagePack | None = None
        self.reload_language_packs()
        self.set_locale(locale)

    def reload_language_packs(self) -> None:
        self._packs = (
            self.language_pack_repository.load_all()
            if self.language_pack_repository is not None
            else {}
        )

    def available_locales(self) -> tuple[tuple[str, str, str, bool], ...]:
        locales = {
            "ja-JP": ("日本語", "ltr", False),
            "en-US": ("English", "ltr", False),
        }
        locales.update(
            {
                locale: (pack.name, pack.direction, True)
                for locale, pack in self._packs.items()
            }
        )
        return tuple(
            (locale, name, direction, custom)
            for locale, (name, direction, custom) in locales.items()
        )

    @property
    def direction(self) -> str:
        return (
            self._active_pack.direction
            if self._active_pack is not None
            else default_direction(self.locale)
        )

    @property
    def content_locale(self) -> str:
        return (
            self._active_pack.fallback_locale
            if self._active_pack is not None
            else self.locale
        )

    def set_locale(self, locale: str) -> None:
        normalized = locale.replace("_", "-")
        active_pack = self._packs.get(normalized)
        candidates = [
            normalized,
            normalized.split("-", 1)[0],
            active_pack.fallback_locale if active_pack is not None else "en-US",
            "en-US",
        ]
        messages: dict[str, str] = {}
        effect_labels: dict[str, str] = {}
        selected = "en-US"
        for candidate in reversed(list(dict.fromkeys(candidates))):
            path = self.resources_directory / f"{candidate}.json"
            if not path.is_file():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
            messages.update({str(key): str(value) for key, value in raw["messages"].items()})
            effect_labels.update(
                {
                    str(key): str(value)
                    for key, value in raw.get("effect_labels", {}).items()
                    if str(value).strip()
                }
            )
            selected = candidate if candidate == normalized else selected
        if active_pack is not None:
            messages.update(active_pack.sections.get("messages", {}))
        self.locale = normalized if messages else selected
        self._messages = messages
        self._effect_labels = effect_labels
        self._active_pack = active_pack

    def text(self, key: str, **values: object) -> str:
        template = self._messages.get(key, key)
        return template.format(**values) if values else template

    def effect_label(self, source_label: str) -> str:
        return self._effect_labels.get(source_label.strip(), "")

    def term(self, section: str, key: str, fallback: str) -> str:
        if self._active_pack is None:
            return fallback
        return self._active_pack.text(section, key) or fallback

    def research_name(self, research_id: str, fallback: str) -> str:
        return self.term("research", research_id, fallback)

    def category_name(self, category_id: str, fallback: str) -> str:
        return self.term("categories", category_id, fallback)

    def building_name(self, building_id: str, fallback: str) -> str:
        return self.term("buildings", building_id, fallback)

    def research_effect(self, research_id: str, fallback: str) -> str:
        return self.term("effects", research_id, fallback)

    def resource_name(self, key: str, fallback: str) -> str:
        return self.term("resources", key, fallback)

    def talent_name(self, talent_id: str, fallback: str) -> str:
        return self.term("talents", talent_id, fallback)

    def english_messages(self) -> dict[str, str]:
        path = self.resources_directory / "en-US.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in raw.get("messages", {}).items()}
