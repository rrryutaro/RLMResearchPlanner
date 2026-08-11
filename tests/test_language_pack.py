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
