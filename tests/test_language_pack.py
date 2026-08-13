from __future__ import annotations

from pathlib import Path

import pytest

from rlm_research_planner.paths import resolve_paths
from rlm_research_planner.repositories.catalog_repository import (
    JsonResearchCatalogRepository,
)
from rlm_research_planner.services.castle_planning import CastleCatalog
from rlm_research_planner.services.language_pack import (
    LANGUAGE_PACK_DOCUMENT_TYPE,
    LanguagePackError,
    build_language_pack_template,
    default_direction,
    language_pack_from_dict,
    load_bundled_locale_manifest,
    normalize_locale,
    select_preferred_locale,
)
from rlm_research_planner.services.localization import Translator


def _pack(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "document_type": LANGUAGE_PACK_DOCUMENT_TYPE,
        "schema_version": 1,
        "locale": "ar",
        "name": "العربية",
        "direction": "rtl",
        "fallback_locale": "en-US",
        "messages": {
            "tab.tree": {"source": "Research Tree", "text": "شجرة الأبحاث"}
        },
        "categories": {},
        "research": {
            "economy_construction_speed": {
                "source": "Construction Speed",
                "text": "سرعة البناء",
            }
        },
        "buildings": {},
        "effects": {},
        "resources": {},
        "talents": {},
    }
    value.update(overrides)
    return value


def test_language_pack_normalizes_locale_and_supports_rtl() -> None:
    pack = language_pack_from_dict(_pack(locale="AR_sa"))

    assert pack.locale == "ar-SA"
    assert pack.direction == "rtl"
    assert pack.text("messages", "tab.tree") == "شجرة الأبحاث"
    assert pack.text("research", "economy_construction_speed") == "سرعة البناء"
    assert normalize_locale("pt_br") == "pt-BR"
    assert default_direction("he-IL") == "rtl"
    assert default_direction("fr-FR") == "ltr"


def test_initial_locale_follows_system_preferences_and_available_packs() -> None:
    available = ("ja-JP", "en-US", "ar", "fr-FR")
    assert select_preferred_locale(("ja-JP",), available) == "ja-JP"
    assert select_preferred_locale(("en-GB",), available) == "en-US"
    assert select_preferred_locale(("ar-SA",), available) == "ar"
    assert select_preferred_locale(("fr-CA",), available) == "fr-FR"
    assert select_preferred_locale(("de-DE",), available) == "en-US"


def test_language_pack_rejects_markup_in_user_translation() -> None:
    raw = _pack(messages={"help.title": {"source": "Help", "text": "<b>Help</b>"}})

    with pytest.raises(LanguagePackError, match="HTML"):
        language_pack_from_dict(raw)


def test_language_pack_rejects_changed_message_placeholders() -> None:
    raw = _pack(
        messages={
            "plan.count": {
                "source": "{count} research tasks",
                "text": "Research tasks: {total}",
            }
        }
    )

    with pytest.raises(LanguagePackError, match="placeholders"):
        language_pack_from_dict(raw)


def test_language_pack_cannot_override_official_disclaimer() -> None:
    raw = _pack(
        messages={
            "tab.tree": {"source": "Research Tree", "text": "شجرة الأبحاث"},
            "app.disclaimer": {
                "source": "Official disclaimer",
                "text": "Replacement disclaimer",
            },
        }
    )
    pack = language_pack_from_dict(raw)

    class StubLanguagePackRepository:
        @staticmethod
        def load_all():
            return {pack.locale: pack}

    translator = Translator(
        resolve_paths().translations,
        pack.locale,
        StubLanguagePackRepository(),
    )

    assert pack.text("messages", "app.disclaimer") == ""
    assert translator.text("app.disclaimer").startswith("This is a free, unofficial tool.")


def test_translator_applies_custom_messages_terms_and_english_fallback() -> None:
    pack = language_pack_from_dict(_pack())

    class StubLanguagePackRepository:
        @staticmethod
        def load_all():
            return {pack.locale: pack}

    translator = Translator(
        resolve_paths().translations,
        pack.locale,
        StubLanguagePackRepository(),
    )

    assert translator.direction == "rtl"
    assert translator.content_locale == "en-US"
    assert translator.text("tab.tree") == pack.text("messages", "tab.tree")
    assert translator.text("tab.help") == "Help"
    assert translator.research_name(
        "economy_construction_speed", "Construction Speed"
    ) == pack.text("research", "economy_construction_speed")


def test_template_contains_all_catalog_terms(master) -> None:
    paths = resolve_paths()
    observations = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    castle_catalog = CastleCatalog.load(paths.castle_catalog)
    translator = Translator(paths.translations, "en-US")

    template = build_language_pack_template(
        messages=translator.english_messages(),
        master=master,
        observations=observations,
        castle_catalog=castle_catalog,
    )

    assert template["document_type"] == LANGUAGE_PACK_DOCUMENT_TYPE
    assert len(template["categories"]) == 16
    assert len(template["research"]) == 399
    assert len(template["buildings"]) == len(castle_catalog.buildings)
    assert template["research"]["economy_construction_speed"]["source"] == "Construction Speed"
    assert template["research"]["economy_construction_speed"]["text"] == ""
    assert "tab.tree" in template["messages"]
    assert "app.disclaimer" not in template["messages"]
    assert "talent_effects" in template
    assert "talent_presets" in template
    assert "talent_preset_descriptions" in template
    assert "effect_labels" in template
    assert "effect_values" in template


def test_bundled_locale_manifest_registers_complete_language_packs() -> None:
    paths = resolve_paths()
    manifest = load_bundled_locale_manifest(paths.translations)

    assert manifest.fallback_locale == "en-US"
    assert {entry.locale for entry in manifest.locales} == {"ja-JP", "en-US"}
    for entry in manifest.locales:
        assert entry.pack.locale == entry.locale
        assert entry.pack.name == entry.name
        assert entry.pack.text("research", "economy_construction_speed")
        assert entry.pack.text("talents", "construction_speed_i")
        assert entry.pack.text("talent_effects", "construction_speed_i")


def test_custom_same_locale_overlays_bundled_pack_without_erasing_terms() -> None:
    raw = _pack(
        locale="ja-JP",
        name="日本語（利用者修正）",
        direction="ltr",
        messages={"tab.tree": {"source": "Research Tree", "text": "研究一覧"}},
        research={},
    )
    pack = language_pack_from_dict(raw)

    class StubLanguagePackRepository:
        @staticmethod
        def load_all():
            return {pack.locale: pack}

    translator = Translator(
        resolve_paths().translations,
        "ja-JP",
        StubLanguagePackRepository(),
    )

    assert translator.text("tab.tree") == "研究一覧"
    assert translator.text("tab.help") == "ヘルプ"
    assert translator.research_name("economy_construction_speed", "") == "建設速度"
    assert translator.talent_effect("construction_speed_i", "") == "建設速度"


def test_translator_uses_manifest_fallback_chain_for_arbitrary_locale() -> None:
    french = language_pack_from_dict(
        _pack(
            locale="fr-FR",
            name="Français",
            direction="ltr",
            fallback_locale="en-US",
            messages={"tab.tree": {"source": "Research Tree", "text": "Recherches"}},
            research={},
        )
    )

    class StubLanguagePackRepository:
        @staticmethod
        def load_all():
            return {french.locale: french}

    translator = Translator(
        resolve_paths().translations,
        "fr-CA",
        StubLanguagePackRepository(),
    )

    assert translator.locale == "fr-FR"
    assert translator.text("tab.tree") == "Recherches"
    assert translator.text("tab.help") == "Help"
    assert translator.research_name("economy_construction_speed", "") == "Construction Speed"
