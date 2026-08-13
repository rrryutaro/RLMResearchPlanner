from __future__ import annotations

from pathlib import Path

from rlm_research_planner.services.language_pack import (
    BundledLocaleManifest,
    LanguagePack,
    LanguagePackRepository,
    default_direction,
    load_bundled_locale_manifest,
    normalize_locale,
)


class Translator:
    def __init__(
        self,
        resources_directory: Path,
        locale: str = "",
        language_pack_repository: LanguagePackRepository | None = None,
    ) -> None:
        self.resources_directory = Path(resources_directory)
        self._manifest: BundledLocaleManifest = load_bundled_locale_manifest(
            self.resources_directory
        )
        self._bundled_locales = self._manifest.by_locale
        self.language_pack_repository = language_pack_repository
        self.locale = locale or self._manifest.fallback_locale
        self._messages: dict[str, str] = {}
        self._effect_labels: dict[str, str] = {}
        self._packs: dict[str, LanguagePack] = {}
        self._bundled_pack: LanguagePack | None = None
        self._active_pack: LanguagePack | None = None
        self._term_layers: tuple[LanguagePack, ...] = ()
        self.reload_language_packs()
        self.set_locale(self.locale)

    def reload_language_packs(self) -> None:
        self._packs = (
            self.language_pack_repository.load_all()
            if self.language_pack_repository is not None
            else {}
        )

    def available_locales(self) -> tuple[tuple[str, str, str, bool], ...]:
        locales = {
            entry.locale: (entry.name, entry.direction, entry.locale in self._packs)
            for entry in self._manifest.locales
        }
        for locale, pack in self._packs.items():
            if locale in locales:
                _name, _direction, _custom = locales[locale]
                locales[locale] = (pack.name, pack.direction, True)
            else:
                locales[locale] = (pack.name, pack.direction, True)
        return tuple(
            (locale, name, direction, custom)
            for locale, (name, direction, custom) in locales.items()
        )

    @property
    def direction(self) -> str:
        return (
            self._active_pack.direction
            if self._active_pack is not None
            else self._bundled_locales.get(
                self.locale,
                None,
            ).direction
            if self.locale in self._bundled_locales
            else default_direction(self.locale)
        )

    @property
    def content_locale(self) -> str:
        return (
            self.locale
            if self.locale in self._bundled_locales
            else self._active_pack.fallback_locale
            if self._active_pack is not None
            else self._manifest.fallback_locale
        )

    @property
    def fallback_locale(self) -> str:
        return self._manifest.fallback_locale

    def available_locale_ids(self) -> tuple[str, ...]:
        return tuple(locale for locale, _name, _direction, _custom in self.available_locales())

    def set_locale(self, locale: str) -> None:
        requested = normalize_locale(locale)
        available = (*self._bundled_locales, *self._packs)
        normalized = (
            requested
            if requested in available
            else next(
                (
                    candidate
                    for candidate in available
                    if candidate.split("-", 1)[0]
                    == requested.split("-", 1)[0]
                ),
                self._manifest.fallback_locale,
            )
        )
        active_pack = self._packs.get(normalized)
        bundled_pack = (
            self._bundled_locales[normalized].pack
            if normalized in self._bundled_locales
            else None
        )
        layers: list[LanguagePack] = []
        visiting: set[str] = set()

        def add_locale(candidate: str) -> None:
            if candidate in visiting:
                return
            visiting.add(candidate)
            custom = self._packs.get(candidate)
            bundled = self._bundled_locales.get(candidate)
            selected = custom or (bundled.pack if bundled is not None else None)
            if selected is not None and selected.fallback_locale != candidate:
                add_locale(selected.fallback_locale)
            if bundled is not None and bundled.pack not in layers:
                layers.append(bundled.pack)
            if custom is not None and custom not in layers:
                layers.append(custom)

        add_locale(self._manifest.fallback_locale)
        add_locale(normalized)
        messages: dict[str, str] = {}
        for layer in layers:
            messages.update(layer.sections.get("messages", {}))
        self.locale = normalized
        self._messages = messages
        self._effect_labels = {}
        self._bundled_pack = bundled_pack
        self._active_pack = active_pack
        self._term_layers = tuple(layers)

    def text(self, key: str, **values: object) -> str:
        template = self._messages.get(key, key)
        return template.format(**values) if values else template

    def effect_label(self, source_label: str) -> str:
        return self.term("effect_labels", source_label.strip(), "")

    def term(self, section: str, key: str, fallback: str) -> str:
        return next(
            (
                value
                for layer in reversed(self._term_layers)
                if (value := layer.text(section, key))
            ),
            fallback,
        )

    @property
    def effect_separator(self) -> str:
        return next(
            (
                layer.effect_separator
                for layer in reversed(self._term_layers)
                if layer.effect_separator is not None
            ),
            " ",
        )

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

    def talent_effect(self, talent_id: str, fallback: str) -> str:
        return self.term("talent_effects", talent_id, fallback)

    def talent_preset(self, preset_id: str, fallback: str) -> str:
        return self.term("talent_presets", preset_id, fallback)

    def talent_preset_description(self, preset_id: str, fallback: str) -> str:
        return self.term("talent_preset_descriptions", preset_id, fallback)

    def effect_value(self, key: str, fallback: str, **values: object) -> str:
        template = self.term("effect_values", key, fallback)
        return template.format(**values) if values else template

    def english_messages(self) -> dict[str, str]:
        return dict(
            self._bundled_locales[self._manifest.fallback_locale].pack.sections.get(
                "messages", {}
            )
        )

    def fallback_terms(self, section: str) -> dict[str, str]:
        return dict(
            self._bundled_locales[self._manifest.fallback_locale].pack.sections.get(
                section, {}
            )
        )

    def fallback_term(self, section: str, key: str, fallback: str = "") -> str:
        return self._bundled_locales[self._manifest.fallback_locale].pack.text(
            section, key
        ) or fallback
