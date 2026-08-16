from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = PROJECT_ROOT / "data" / "research" / "catalog.json"
OBSERVATIONS_ROOT = PROJECT_ROOT / "data" / "research" / "observations"
OUTPUT_ROOT = PROJECT_ROOT / "dataset" / "generated"

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rlm_research_planner.repositories.catalog_repository import (  # noqa: E402
    JsonResearchCatalogRepository,
)


SCHEMA_VERSION = 2
DATASET_VERSION = "0.1.0"
FANDOM_LICENSE = "CC BY-SA 3.0 Unported"
FANDOM_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/3.0/"
REFERENCE_ONLY_LICENSE = "Reference only; no redistribution license asserted"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _stable_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug or "source"


def _source_type(url: str) -> str:
    host = urlparse(url).netloc.casefold()
    if "fandom.com" in host or "gamerch.com" in host:
        return "wiki"
    if "youtube.com" in host or "youtu.be" in host:
        return "video"
    if "igg.com" in host:
        return "official"
    return "community"


def _source_id(name: str, url: str, category_id: str = "") -> str:
    host = urlparse(url).netloc.casefold()
    if category_id and "fandom.com" in host:
        return f"src_fandom_{category_id}"
    known = {
        "https://lordsmobile.fandom.com/wiki/Research": "src_fandom_research",
        "https://lords-mobile.gamerch.com/%E7%A0%94%E7%A9%B6-%E7%A0%94%E7%A9%B6%E4%B8%80%E8%A6%A7": "src_gamerch_research_list",
        "https://retry0907yn.com/%E3%80%90%E3%83%AD%E3%83%BC%E3%83%A2%E3%83%90%E7%A0%94%E7%A9%B6%E3%80%91%E7%A0%94%E7%A9%B6%E3%83%91%E3%83%AF%E3%83%BC%E3%83%87%E3%83%BC%E3%82%BF%E5%AE%8C%E5%85%A8%E3%82%AC%E3%82%A4%E3%83%89-12/": "src_retry_wonder_battles",
        "https://retry0907yn.com/%E3%80%90%E3%83%AD%E3%83%BC%E3%83%A2%E3%83%90%E7%A0%94%E7%A9%B6%E3%80%91%E7%A0%94%E7%A9%B6%E3%83%91%E3%83%AF%E3%83%BC%E3%83%87%E3%83%BC%E3%82%BF%E5%AE%8C%E5%85%A8%E3%82%AC%E3%82%A4%E3%83%89-14/": "src_retry_advanced_wonder_battles",
        "https://www.youtube.com/watch?v=QKP5dGy1IHs": "src_bigsoneca_guild_duel_video",
        "https://neovis99.com/lords-mobile-capture-part151/": "src_neovis_guild_duel_research",
        "https://lordsmobile.fandom.com/wiki/Furious_Defense_%28Infantry%29": "src_fandom_sigils_furious_defense_infantry",
        "https://lordsmobile.fandom.com/wiki/Helmet_Sigil": "src_fandom_sigils_helmet_sigil",
    }
    return known.get(url, f"src_{_stable_slug(name)[:160]}")


def _source_record(
    name: str,
    url: str,
    checked_on: str,
    *,
    category_id: str = "",
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = raw or {}
    is_fandom = "fandom.com" in urlparse(url).netloc.casefold()
    if is_fandom:
        license_name = FANDOM_LICENSE
        license_url = FANDOM_LICENSE_URL
        attribution = (
            f"Contributors to {name} on the Lords Mobile Wiki (Fandom); "
            "adapted and normalized by RLMResearchPlanner."
        )
    else:
        license_name = str(
            raw.get("license")
            or raw.get("license_name")
            or REFERENCE_ONLY_LICENSE
        )
        license_url = str(raw.get("license_url") or "")
        attribution = name
    result: dict[str, Any] = {
        "id": _source_id(name, url, category_id),
        "type": _source_type(url),
        "name": name,
        "url": url,
        "retrieved_on": checked_on,
        "license": {
            "name": license_name,
            "attribution": attribution,
        },
    }
    if license_url:
        result["license"]["url"] = license_url
    notes = str(
        raw.get("scope")
        or raw.get("changes")
        or raw.get("licensing_terms_url")
        or ""
    ).strip()
    retrieval_note = (
        "retrieved_on is inherited from the legacy catalog checked_on date; "
        "the original per-source retrieval date was not recorded."
    )
    notes = f"{notes} {retrieval_note}".strip()
    if notes:
        result["notes"] = notes
    return result


def _build_sources(catalog: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    checked_on = str(catalog.get("checked_on") or "1970-01-01")
    records_by_url: dict[str, dict[str, Any]] = {}
    for raw in catalog.get("sources", []):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "Reference source")
        url = str(raw.get("url") or "")
        if url:
            records_by_url[url] = _source_record(name, url, checked_on, raw=raw)
    for category in catalog.get("categories", []):
        if not isinstance(category, dict):
            continue
        category_id = str(category.get("id") or "")
        url = str(category.get("source_url") or "")
        if not url:
            continue
        if url in records_by_url:
            legacy_license_name = str(category.get("license_name") or "").strip()
            if legacy_license_name:
                records_by_url[url]["license"]["name"] = legacy_license_name
            continue
        title = category.get("titles", {})
        english_title = (
            str(title.get("en-US") or category_id)
            if isinstance(title, dict)
            else category_id
        )
        host = urlparse(url).netloc.casefold()
        if "fandom.com" in host:
            name = f"Lords Mobile Wiki (Fandom): {english_title}"
        else:
            name = f"{english_title} research reference"
        records_by_url[url] = _source_record(
            name,
            url,
            checked_on,
            category_id=category_id,
            raw=category,
        )
    records = sorted(records_by_url.values(), key=lambda item: item["id"])
    ids = [str(item["id"]) for item in records]
    if len(ids) != len(set(ids)):
        raise ValueError("legacy sources do not map to unique stable source IDs")
    return (
        {
            "document_type": "RLMResearchData.sources",
            "schema_version": SCHEMA_VERSION,
            "sources": records,
        },
        {url: str(record["id"]) for url, record in records_by_url.items()},
    )


def _build_evidence(catalog: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    if OBSERVATIONS_ROOT.is_dir():
        for path in sorted(OBSERVATIONS_ROOT.glob("*.json")):
            raw = _read_json(path)
            observation_id = _stable_slug(str(raw.get("observation_id") or path.stem))
            record: dict[str, Any] = {
                "id": f"evidence_{observation_id}",
                "type": "game_capture",
                "captured_on": str(
                    raw.get("captured_on") or catalog.get("checked_on") or "1970-01-01"
                ),
                "game_version": str(raw.get("game_version") or "unknown"),
                "locale": str(raw.get("locale") or "ja-JP"),
                "scope": str(raw.get("scope") or "Legacy direct observation"),
                "redistribution_allowed": bool(
                    raw.get("image_redistribution") is True
                ),
            }
            notes = str(raw.get("notes") or "").strip()
            if notes:
                record["notes"] = notes
            records.append(record)
    return {
        "document_type": "RLMResearchData.evidence",
        "schema_version": SCHEMA_VERSION,
        "evidence": records,
    }


def _tree_source_ids(
    source_url: str,
    source_ids_by_url: dict[str, str],
) -> list[str]:
    source_id = source_ids_by_url.get(source_url)
    return [source_id] if source_id else []


def _verification(
    legacy_status: str,
    source_ids: Iterable[str],
    checked_on: str,
) -> dict[str, Any]:
    sources = sorted(set(source_ids))
    status = "provisional"
    notes = "Migrated from the legacy catalog without changing its values."
    if legacy_status == "sourced_partial":
        notes = "Legacy source data is partial; migrated values remain provisional."
    elif legacy_status == "sourced_conflict_corrected":
        status = "disputed"
        notes = (
            "Legacy references conflicted; the catalog's selected correction was "
            "preserved for review."
        )
    elif legacy_status == "sourced_conflict_omitted":
        status = "disputed"
        notes = (
            "Legacy references conflicted and the disputed value was omitted; the "
            "unknown value was preserved for review."
        )
    result: dict[str, Any] = {
        "status": status,
        "checked_on": checked_on,
        "notes": notes,
    }
    if sources:
        result["source_ids"] = sources
    return result


def _coverage(nodes: Iterable[Any]) -> str:
    node_list = list(nodes)
    if not any(node.levels for node in node_list):
        return "structure_only"
    if all(
        node.max_level is not None
        and set(node.levels) == set(range(1, int(node.max_level) + 1))
        for node in node_list
    ):
        return "complete"
    return "partial"


def _level_payload(level: Any, source_ids: list[str], checked_on: str) -> dict[str, Any]:
    costs: dict[str, int] | None
    if level.costs or level.costs_verified:
        costs = dict(sorted(level.costs.items()))
    else:
        costs = None
    result: dict[str, Any] = {
        "level": level.level,
        "academy_level": level.academy_level,
        "base_time_seconds": level.base_time_seconds,
        "technolabe_count": level.technolabe_count,
        "power": level.power,
        "costs": costs,
        "costs_complete": bool(level.costs_verified),
        "prerequisites": [
            {
                "research_id": requirement.research_id,
                "level": requirement.level,
            }
            for requirement in level.requirements
        ],
        "buildings": dict(sorted(level.building_requirements.items())),
        "legacy_verification_status": level.verification_status,
    }
    if level.verification_status != "sourced":
        result["verification"] = _verification(
            level.verification_status,
            source_ids,
            checked_on,
        )
    return result


def _fact_source_ids(
    raw_level: dict[str, Any],
    fact_name: str,
    source_ids_by_url: dict[str, str],
) -> list[str]:
    raw_sources = raw_level.get("source_urls", {})
    if not isinstance(raw_sources, dict):
        raise ValueError("legacy level source_urls must be an object")
    raw_urls = raw_sources.get(fact_name, [])
    if isinstance(raw_urls, str):
        raw_urls = [raw_urls]
    if not isinstance(raw_urls, list) or not all(
        isinstance(url, str) and url for url in raw_urls
    ):
        raise ValueError(
            f"legacy level source_urls.{fact_name} must be a URL string or list"
        )
    missing = sorted(url for url in raw_urls if url not in source_ids_by_url)
    if missing:
        raise ValueError(
            "legacy level references source URLs that are not declared in sources: "
            + ", ".join(missing)
        )
    return sorted({source_ids_by_url[url] for url in raw_urls})


def _level_payload_with_provenance(
    level: Any,
    source_ids: list[str],
    checked_on: str,
    raw_level: dict[str, Any],
    source_ids_by_url: dict[str, str],
) -> dict[str, Any]:
    result = _level_payload(level, source_ids, checked_on)
    raw_evidence_ids = raw_level.get("evidence_ids", [])
    if isinstance(raw_evidence_ids, str):
        raw_evidence_ids = [raw_evidence_ids]
    if not isinstance(raw_evidence_ids, list) or not all(
        isinstance(evidence_id, str) and evidence_id
        for evidence_id in raw_evidence_ids
    ):
        raise ValueError("legacy level evidence_ids must be a string or list")
    if raw_evidence_ids:
        result["verification"] = {
            "status": "provisional",
            "evidence_ids": sorted(set(raw_evidence_ids)),
            "checked_on": str(raw_level.get("checked_on") or checked_on),
            "notes": str(
                raw_level.get("verification_notes")
                or "Direct game evidence is retained, but rounded or inferred values remain provisional."
            ),
        }
    overrides: dict[str, Any] = {}
    for fact_name in ("time", "costs", "requirements"):
        fact_sources = _fact_source_ids(
            raw_level,
            fact_name,
            source_ids_by_url,
        )
        if not fact_sources:
            continue
        overrides[fact_name] = {
            "status": "provisional",
            "source_ids": fact_sources,
            "checked_on": checked_on,
            "notes": (
                "Fact-specific source retained from the legacy transition catalog; "
                "the source reference alone does not promote the value to verified."
            ),
        }
    if overrides:
        result["verification_overrides"] = overrides
    return result


def _node_payload(
    node: Any,
    source_ids: list[str],
    checked_on: str,
    raw_levels: dict[str, Any],
    source_ids_by_url: dict[str, str],
) -> dict[str, Any]:
    effects: list[dict[str, Any]] = []
    if node.effect_values:
        effects.append(
            {
                "metric_id": node.id,
                "unit": "text",
                "parsed": False,
                "values": [
                    {
                        "level": level,
                        "value": value,
                        "display_fallback": value,
                    }
                    for level, value in sorted(node.effect_values.items())
                ],
            }
        )
    return {
        "id": node.id,
        "max_level": int(node.max_level),
        "layout": {"row": node.row, "column": node.column},
        "levels": [
            _level_payload_with_provenance(
                level,
                source_ids,
                checked_on,
                raw_levels.get(str(level.level), {}),
                source_ids_by_url,
            )
            for _, level in sorted(node.levels.items())
        ],
        "effects": effects,
        "lifecycle": {"state": "active"},
    }


def _tree_payload(
    observation: Any,
    source_ids: list[str],
    checked_on: str,
    raw_category: dict[str, Any],
    source_ids_by_url: dict[str, str],
) -> dict[str, Any]:
    tree_verification = _verification(
        observation.verification_status,
        source_ids,
        checked_on,
    )
    tree_verification["notes"] = (
        "Imported from the frozen legacy catalog during the versioned dataset migration. Display connections "
        "remain provisional until checked against direct game evidence."
    )
    connection_verification = {
        "status": "provisional",
        "checked_on": checked_on,
        "notes": (
            "Preserved from the current desktop loader's visual connection groups; "
            "not yet accepted as canonical game evidence."
        ),
    }
    if source_ids:
        connection_verification["source_ids"] = source_ids
    source_edge_verification = {
        "status": "provisional",
        "checked_on": checked_on,
        "notes": (
            "Preserved verbatim from the legacy category edge list because the "
            "desktop UI consumes it independently from planning prerequisites and "
            "display connection groups."
        ),
    }
    if source_ids:
        source_edge_verification["source_ids"] = source_ids
    return {
        "document_type": "RLMResearchData.tree",
        "schema_version": SCHEMA_VERSION,
        "tree_id": observation.category_id,
        "coverage": _coverage(observation.nodes),
        "default_verification": tree_verification,
        "legacy_compatibility": {
            "source_type": observation.source_type,
            "verification_status": observation.verification_status,
            "scope": observation.scope,
            "notes": observation.notes,
        },
        "nodes": [
            _node_payload(
                node,
                source_ids,
                checked_on,
                (
                    raw_category.get("level_data", {}).get(
                        str(node.names.get("en-US") or ""),
                        {},
                    )
                ),
                source_ids_by_url,
            )
            for node in sorted(
                observation.nodes,
                key=lambda item: (item.row, item.column, item.id),
            )
        ],
        "source_edges": [
            {
                "prerequisite_id": edge.prerequisite_id,
                "research_id": edge.research_id,
                "verification": dict(source_edge_verification),
            }
            for edge in observation.edges
        ],
        "display_connections": [
            {
                "from_ids": list(group.prerequisite_ids),
                "to_ids": list(group.research_ids),
                "verification": dict(connection_verification),
            }
            for group in observation.connection_groups
        ],
    }


def build_generated_dataset() -> dict[str, Any]:
    catalog = _read_json(CATALOG_PATH)
    observations = JsonResearchCatalogRepository(CATALOG_PATH).load_all()
    sources, source_ids_by_url = _build_sources(catalog)
    checked_on = str(catalog.get("checked_on") or "1970-01-01")
    category_raw = {
        str(item.get("id")): item
        for item in catalog.get("categories", [])
        if isinstance(item, dict)
    }
    trees: dict[str, Any] = {}
    locale_documents = {
        locale: {
            "document_type": "RLMResearchData.locale",
            "schema_version": SCHEMA_VERSION,
            "locale": locale,
            "direction": "ltr",
            "fallback_locale": "en-US",
            "trees": {},
            "research": {},
            "metrics": {},
        }
        for locale in ("en-US", "ja-JP")
    }
    for observation in observations:
        raw = category_raw[observation.category_id]
        source_ids = _tree_source_ids(
            observation.source_url,
            source_ids_by_url,
        )
        trees[observation.category_id] = _tree_payload(
            observation,
            source_ids,
            checked_on,
            raw,
            source_ids_by_url,
        )
        for locale, document in locale_documents.items():
            document["trees"][observation.category_id] = str(
                observation.titles.get(locale)
                or observation.titles.get("en-US")
                or observation.category_id
            )
            for node in observation.nodes:
                display_name = str(
                    node.names.get(locale)
                    or node.names.get("en-US")
                    or node.id
                )
                document["research"][node.id] = display_name
                if node.effect_values:
                    raw_effects = raw.get("effects", {})
                    raw_effect = (
                        raw_effects.get(node.names.get("en-US", ""), {})
                        if isinstance(raw_effects, dict)
                        else {}
                    )
                    label = (
                        str(raw_effect.get("label") or "")
                        if isinstance(raw_effect, dict)
                        else ""
                    )
                    localized_labels = (
                        raw_effect.get("localized_labels", {})
                        if isinstance(raw_effect, dict)
                        else {}
                    )
                    localized_label = (
                        str(localized_labels.get(locale) or "")
                        if isinstance(localized_labels, dict)
                        else ""
                    )
                    document["metrics"][node.id] = (
                        localized_label
                        or (label if locale == "en-US" and label else display_name)
                    )
    tree_entries = [
        {"id": tree_id, "path": f"trees/{tree_id}.json"}
        for tree_id in trees
    ]
    manifest = {
        "document_type": "RLMResearchData.manifest",
        "schema_version": SCHEMA_VERSION,
        "dataset_id": "lords_mobile_research_data",
        "dataset_version": DATASET_VERSION,
        "game_version": str(catalog.get("game_version") or "unknown"),
        "checked_on": checked_on,
        "sources_path": "sources.json",
        "evidence_path": "evidence.json",
        "aliases_path": "id-aliases.json",
        "trees": tree_entries,
        "locales": [
            {
                "locale": locale,
                "path": f"locales/{locale}.json",
                "required": True,
            }
            for locale in locale_documents
        ],
        "license": {
            "name": FANDOM_LICENSE,
            "url": FANDOM_LICENSE_URL,
            "attribution": (
                "Fandom-derived portions credit contributors to the Lords Mobile "
                "Wiki. Project normalization and arrangement are offered under "
                "CC BY-SA 3.0; see DATA_LICENSE.md for source-by-source details."
            ),
        },
    }
    return {
        "manifest": manifest,
        "sources": sources,
        "evidence": _build_evidence(catalog),
        "aliases": {
            "document_type": "RLMResearchData.aliases",
            "schema_version": SCHEMA_VERSION,
            "aliases": {},
        },
        "trees": trees,
        "locales": locale_documents,
    }


def write_generated_dataset(dataset: dict[str, Any], root: Path = OUTPUT_ROOT) -> None:
    _write_json(root / "manifest.json", dataset["manifest"])
    _write_json(root / "sources.json", dataset["sources"])
    _write_json(root / "evidence.json", dataset["evidence"])
    _write_json(root / "id-aliases.json", dataset["aliases"])
    for tree_id, tree in dataset["trees"].items():
        _write_json(root / "trees" / f"{tree_id}.json", tree)
    for locale, document in dataset["locales"].items():
        _write_json(root / "locales" / f"{locale}.json", document)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the Phase 2 dataset from the authoritative legacy catalog."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_ROOT,
        help="Output dataset root (defaults to dataset/generated).",
    )
    args = parser.parse_args()
    dataset = build_generated_dataset()
    write_generated_dataset(dataset, args.output)
    research_count = sum(len(tree["nodes"]) for tree in dataset["trees"].values())
    level_count = sum(
        len(node["levels"])
        for tree in dataset["trees"].values()
        for node in tree["nodes"]
    )
    print(
        f"Generated {len(dataset['trees'])} trees, {research_count} research IDs, "
        f"and {level_count} level records."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
