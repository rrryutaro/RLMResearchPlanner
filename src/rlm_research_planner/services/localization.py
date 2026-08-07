from __future__ import annotations

import json
from pathlib import Path


class Translator:
    def __init__(self, resources_directory: Path, locale: str = "ja-JP") -> None:
        self.resources_directory = Path(resources_directory)
        self.locale = locale
        self._messages: dict[str, str] = {}
        self._effect_labels: dict[str, str] = {}
        self.set_locale(locale)

    def set_locale(self, locale: str) -> None:
        normalized = locale.replace("_", "-")
        candidates = [normalized, normalized.split("-", 1)[0], "en-US"]
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
        self.locale = normalized if messages else selected
        self._messages = messages
        self._effect_labels = effect_labels

    def text(self, key: str, **values: object) -> str:
        template = self._messages.get(key, key)
        return template.format(**values) if values else template

    def effect_label(self, source_label: str) -> str:
        return self._effect_labels.get(source_label.strip(), "")
