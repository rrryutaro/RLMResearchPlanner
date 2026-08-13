from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
I18N_ROOT = ROOT / "resources" / "i18n"


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def translations(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key, entry in value.items():
        text = entry.get("text", "") if isinstance(entry, Mapping) else entry
        if str(text or "").strip():
            result[str(key)] = str(text)
    return result


def localized(value: object, locale: str) -> str:
    if not isinstance(value, Mapping):
        return ""
    return str(value.get(locale, "") or "").strip()


def canonical_sections(locale: str, current: Mapping[str, object]) -> dict[str, dict[str, str]]:
    dataset_manifest = read_json(ROOT / "dataset" / "generated" / "manifest.json")
    dataset_locale_entry = next(
        (
            entry
            for entry in dataset_manifest.get("locales", [])
            if isinstance(entry, Mapping) and entry.get("locale") == locale
        ),
        None,
    )
    dataset_locale = (
        read_json(ROOT / "dataset" / "generated" / str(dataset_locale_entry["path"]))
        if dataset_locale_entry is not None
        else {}
    )

    sections = {
        key: translations(current.get(key, {}))
        for key in (
            "messages",
            "categories",
            "research",
            "buildings",
            "effects",
            "effect_labels",
            "effect_values",
            "resources",
            "talents",
            "talent_effects",
            "talent_presets",
            "talent_preset_descriptions",
        )
    }
    messages = sections["messages"]
    sections["resources"].update(
        {
            key.removeprefix("resource."): value
            for key, value in messages.items()
            if key.startswith("resource.")
        }
    )
    sections["categories"].update(translations(dataset_locale.get("trees", {})))
    sections["research"].update(translations(dataset_locale.get("research", {})))
    metrics = translations(dataset_locale.get("metrics", {}))
    legacy_catalog = read_json(ROOT / "data" / "research" / "catalog.json")
    legacy_effect_labels: dict[str, str] = {}
    for category in legacy_catalog.get("categories", []):
        if not isinstance(category, Mapping):
            continue
        for source_name, effect in (category.get("effects", {}) or {}).items():
            if not isinstance(effect, Mapping):
                continue
            research_id = str((category.get("id_overrides", {}) or {}).get(source_name, ""))
            if not research_id:
                continue
            translated = sections["effect_labels"].get(str(effect.get("label", "")), "")
            if translated:
                legacy_effect_labels[research_id] = translated
    for tree_entry in dataset_manifest.get("trees", []):
        if not isinstance(tree_entry, Mapping):
            continue
        tree = read_json(ROOT / "dataset" / "generated" / str(tree_entry["path"]))
        for node in tree.get("nodes", []):
            if not isinstance(node, Mapping):
                continue
            effects = node.get("effects", [])
            effect = effects[0] if isinstance(effects, list) and effects else {}
            metric_id = str(effect.get("metric_id", "")) if isinstance(effect, Mapping) else ""
            source_label = legacy_effect_labels.get(str(node.get("id", "")), "")
            if source_label:
                sections["effects"][str(node.get("id", ""))] = source_label
            elif metric_id in metrics:
                sections["effects"][str(node.get("id", ""))] = metrics[metric_id]

    castle = read_json(ROOT / "data" / "buildings" / "castle_catalog.json")
    for building in castle.get("buildings", []):
        if not isinstance(building, Mapping):
            continue
        name = localized(building.get("names"), locale)
        if name:
            sections["buildings"][str(building.get("id", ""))] = name
    mana = castle.get("castle_mana_progression", {})
    mana_name = localized(mana.get("names"), locale) if isinstance(mana, Mapping) else ""
    if mana_name:
        sections["buildings"]["castle_mana"] = mana_name

    talents = read_json(ROOT / "data" / "talents" / "catalog.json")
    for talent in talents.get("talents", []):
        if not isinstance(talent, Mapping):
            continue
        talent_id = str(talent.get("id", ""))
        name = localized(talent.get("name"), locale)
        effect = localized(talent.get("effect"), locale)
        if name:
            sections["talents"][talent_id] = name
        if effect:
            sections["talent_effects"][talent_id] = effect
    for preset in talents.get("presets", []):
        if not isinstance(preset, Mapping):
            continue
        preset_id = str(preset.get("id", ""))
        name = localized(preset.get("name"), locale)
        description = localized(preset.get("description"), locale)
        if name:
            sections["talent_presets"][preset_id] = name
        if description:
            sections["talent_preset_descriptions"][preset_id] = description
    return sections


def main() -> int:
    manifest = read_json(I18N_ROOT / "manifest.json")
    fallback_locale = str(manifest.get("fallback_locale", "en-US"))
    for entry in manifest.get("locales", []):
        if not isinstance(entry, Mapping):
            continue
        path = I18N_ROOT / str(entry["path"])
        current = read_json(path)
        locale = str(entry["locale"])
        sections = canonical_sections(locale, current)
        document: dict[str, object] = {
            "document_type": "RLMResearchPlanner.language-pack",
            "schema_version": 1,
            "locale": locale,
            "name": str(entry["name"]),
            "direction": str(entry.get("direction", "ltr")),
            "fallback_locale": fallback_locale,
            "effect_separator": str(current.get("effect_separator", " "))[:20],
            "author": str(current.get("author", "RLMResearchPlanner contributors")),
            "license": str(current.get("license", "MIT AND CC BY-SA 3.0")),
            "catalog_dataset_id": str(dataset_id()),
            **sections,
        }
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Updated {path.relative_to(ROOT)}")
    return 0


def dataset_id() -> str:
    return str(read_json(ROOT / "dataset" / "generated" / "manifest.json").get("dataset_id", ""))


if __name__ == "__main__":
    raise SystemExit(main())
