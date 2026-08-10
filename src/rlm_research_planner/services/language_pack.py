from __future__ import annotations

import json
import re
from string import Formatter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from rlm_research_planner.domain.models import MasterData
from rlm_research_planner.domain.observations import ResearchTreeObservation
from rlm_research_planner.services.castle_planning import CastleCatalog


LANGUAGE_PACK_DOCUMENT_TYPE = "RLMResearchPlanner.language-pack"
LANGUAGE_PACK_SCHEMA_VERSION = 1
LANGUAGE_PACK_SECTIONS = (
    "messages",
    "categories",
    "research",
    "buildings",
    "effects",
    "resources",
)
_LOCALE_PATTERN = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
_RTL_LANGUAGES = frozenset(
    ("ar", "arc", "ckb", "dv", "fa", "he", "ks", "nqo", "ps", "sd", "syr", "ug", "ur", "yi")
)


class LanguagePackError(ValueError):
    pass


@dataclass(frozen=True)
class LanguagePack:
    locale: str
    name: str
    direction: str
    fallback_locale: str
    author: str
    license_name: str
    dataset_id: str
    sections: Mapping[str, Mapping[str, str]]

    def text(self, section: str, key: str) -> str:
        return str(self.sections.get(section, {}).get(key, "")).strip()

    def to_dict(self) -> dict[str, object]:
        return {
            "document_type": LANGUAGE_PACK_DOCUMENT_TYPE,
            "schema_version": LANGUAGE_PACK_SCHEMA_VERSION,
            "locale": self.locale,
            "name": self.name,
            "direction": self.direction,
            "fallback_locale": self.fallback_locale,
            "author": self.author,
            "license": self.license_name,
            "catalog_dataset_id": self.dataset_id,
            **{
                section: {
                    key: {"source": "", "text": value}
                    for key, value in sorted(self.sections.get(section, {}).items())
                }
                for section in LANGUAGE_PACK_SECTIONS
            },
        }


def normalize_locale(value: object) -> str:
    locale = str(value or "").strip().replace("_", "-")
    if not _LOCALE_PATTERN.fullmatch(locale):
        raise LanguagePackError("locale must be a BCP 47 language tag such as fr-FR or ar")
    parts = locale.split("-")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 2 and part.isalpha():
            normalized.append(part.upper())
        elif len(part) == 4 and part.isalpha():
            normalized.append(part.title())
        else:
            normalized.append(part)
    return "-".join(normalized)


def default_direction(locale: str) -> str:
    return "rtl" if locale.split("-", 1)[0].lower() in _RTL_LANGUAGES else "ltr"


def _plain_translation(value: object, *, section: str, key: str) -> str:
    source_text = ""
    if isinstance(value, dict):
        source_text = str(value.get("source", ""))
        value = value.get("text", "")
    text = str(value or "").strip()
    if any(character in text for character in ("<", ">")):
        raise LanguagePackError(
            f"{section}.{key}: translated text must not contain HTML markup"
        )
    if any(ord(character) < 32 and character not in "\t\n\r" for character in text):
        raise LanguagePackError(f"{section}.{key}: translated text contains a control character")
    if len(text) > 20_000:
        raise LanguagePackError(f"{section}.{key}: translated text is too long")
    if section == "messages" and text:
        try:
            translated_fields = {
                field_name
                for _literal, field_name, _format, _conversion in Formatter().parse(text)
                if field_name is not None
            }
            source_fields = {
                field_name
                for _literal, field_name, _format, _conversion in Formatter().parse(source_text)
                if field_name is not None
            }
        except ValueError as exc:
            raise LanguagePackError(
                f"{section}.{key}: translated text contains invalid braces"
            ) from exc
        if source_text and translated_fields != source_fields:
            raise LanguagePackError(
                f"{section}.{key}: translated text must keep the source placeholders"
            )
    return text


def language_pack_from_dict(raw: object) -> LanguagePack:
    if not isinstance(raw, dict):
        raise LanguagePackError("language pack must be a JSON object")
    if raw.get("document_type") != LANGUAGE_PACK_DOCUMENT_TYPE:
        raise LanguagePackError("unsupported language pack document_type")
    if int(raw.get("schema_version", 0)) != LANGUAGE_PACK_SCHEMA_VERSION:
        raise LanguagePackError("unsupported language pack schema_version")
    locale = normalize_locale(raw.get("locale"))
    direction = str(raw.get("direction") or default_direction(locale)).strip().lower()
    if direction not in ("ltr", "rtl"):
        raise LanguagePackError("direction must be ltr or rtl")
    fallback_locale = normalize_locale(raw.get("fallback_locale") or "en-US")
    name = str(raw.get("name") or locale).strip()
    if not name or len(name) > 100:
        raise LanguagePackError("name is required and must be at most 100 characters")
    sections: dict[str, dict[str, str]] = {}
    for section in LANGUAGE_PACK_SECTIONS:
        source = raw.get(section, {})
        if not isinstance(source, dict):
            raise LanguagePackError(f"{section} must be an object")
        translations: dict[str, str] = {}
        for raw_key, raw_value in source.items():
            key = str(raw_key).strip()
            if not key or len(key) > 300:
                raise LanguagePackError(f"{section} contains an invalid key")
            text = _plain_translation(raw_value, section=section, key=key)
            if text:
                translations[key] = text
        sections[section] = translations
    return LanguagePack(
        locale=locale,
        name=name,
        direction=direction,
        fallback_locale=fallback_locale,
        author=str(raw.get("author", "")).strip()[:200],
        license_name=str(raw.get("license", "")).strip()[:200],
        dataset_id=str(raw.get("catalog_dataset_id", "")).strip()[:200],
        sections=sections,
    )


class LanguagePackRepository:
    def __init__(self, directory: Path | None) -> None:
        self.directory = Path(directory) if directory is not None else None

    def load_all(self) -> dict[str, LanguagePack]:
        if self.directory is None or not self.directory.is_dir():
            return {}
        packs: dict[str, LanguagePack] = {}
        for path in sorted(self.directory.glob("*.json")):
            try:
                pack = language_pack_from_dict(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except (OSError, json.JSONDecodeError, LanguagePackError):
                continue
            packs[pack.locale] = pack
        return packs

    def install(self, raw: object) -> LanguagePack:
        if self.directory is None:
            raise LanguagePackError("language pack storage is unavailable")
        pack = language_pack_from_dict(raw)
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{pack.locale}.json"
        target.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return pack

    def remove(self, locale: str) -> bool:
        if self.directory is None:
            return False
        normalized = normalize_locale(locale)
        target = self.directory / f"{normalized}.json"
        if not target.is_file():
            return False
        target.unlink()
        return True


def _entry(source: str, text: str = "") -> dict[str, str]:
    return {"source": str(source), "text": str(text)}


def build_language_pack_template(
    *,
    messages: Mapping[str, str],
    master: MasterData,
    observations: Iterable[ResearchTreeObservation],
    castle_catalog: CastleCatalog,
) -> dict[str, object]:
    category_sources: dict[str, str] = {}
    research_sources: dict[str, str] = {}
    effect_sources: dict[str, str] = {}
    for observation in observations:
        category_sources.setdefault(
            observation.category_id,
            observation.localized_title("en-US"),
        )
        for node in observation.nodes:
            research_sources.setdefault(node.id, node.localized_name("en-US"))
            if node.effect_label:
                effect_sources.setdefault(node.id, node.effect_label)
    for category in master.categories:
        category_sources.setdefault(
            category.id, master.localized_category(category.id, "en-US").name
        )
    for research in master.research:
        research_sources.setdefault(
            research.id, master.localized_research(research.id, "en-US").name
        )
        effect = master.localized_research(research.id, "en-US").effect_label
        if effect:
            effect_sources.setdefault(research.id, effect)
    resource_sources = {
        key.removeprefix("resource."): value
        for key, value in messages.items()
        if key.startswith("resource.")
    }
    return {
        "document_type": LANGUAGE_PACK_DOCUMENT_TYPE,
        "schema_version": LANGUAGE_PACK_SCHEMA_VERSION,
        "locale": "xx",
        "name": "New language",
        "direction": "ltr",
        "fallback_locale": "en-US",
        "author": "",
        "license": "",
        "catalog_dataset_id": master.dataset_id,
        "messages": {
            key: _entry(value) for key, value in sorted(messages.items())
        },
        "categories": {
            key: _entry(value) for key, value in sorted(category_sources.items())
        },
        "research": {
            key: _entry(value) for key, value in sorted(research_sources.items())
        },
        "buildings": {
            key: _entry(building.localized_name("en-US"))
            for key, building in sorted(castle_catalog.buildings.items())
        },
        "effects": {
            key: _entry(value) for key, value in sorted(effect_sources.items())
        },
        "resources": {
            key: _entry(value) for key, value in sorted(resource_sources.items())
        },
    }
