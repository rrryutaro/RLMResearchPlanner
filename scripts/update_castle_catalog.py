from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path


API_URL = "https://lordsmobile.fandom.com/api.php"
BUILDINGS = {
    "castle": ("Castle", "城"),
    "castle_wall": ("Castle Wall", "城壁"),
    "workshop": ("Workshop", "鍛造所"),
    "mine": ("Mine", "鉱山"),
    "vault": ("Vault", "保管庫"),
    "infirmary": ("Infirmary", "医療所"),
    "barrack": ("Barrack", "兵舎"),
    "quarry": ("Quarry", "採石場"),
    "academy": ("Academy", "アカデミー"),
    "embassy": ("Embassy", "大使館"),
    "battle_hall": ("Battle Hall", "バトルホール"),
    "prison": ("Prison", "牢獄"),
    "altar": ("Altar", "祭壇"),
    "trading_post": ("Trading Post", "交易所"),
    "manor": ("Manor", "荘園"),
    "farm": ("Farm", "農場"),
    "lumber_mill": ("Lumber Mill", "製材所"),
    "watchtower": ("Watchtower", "監視塔"),
}
NAME_TO_ID = {
    re.sub(r"\s+", " ", english).casefold(): building_id
    for building_id, (english, _japanese) in BUILDINGS.items()
}
NAME_TO_ID["barracks"] = "barrack"

RESOURCE_HEADERS = (
    ("food", "Food"),
    ("stone", "Stone"),
    ("timber", "Timber"),
    ("ore", "Ore"),
    ("war_tome", "War Tome"),
    ("steel_cuffs", "Steel Cuffs"),
    ("soul_crystal", "Soul Crystal"),
)
BASE_BUILDING_COST_KEYS = ("food", "stone", "timber", "ore", "gold_hammer")
GEM_SHOP_PACKS = {
    "gold_hammer": ({"quantity": 1, "gems": 2_000},),
    "war_tome": (
        {"quantity": 1, "gems": 15},
        {"quantity": 10, "gems": 120},
        {"quantity": 100, "gems": 1_100},
        {"quantity": 1_000, "gems": 10_000},
    ),
    "steel_cuffs": (
        {"quantity": 1, "gems": 15},
        {"quantity": 10, "gems": 120},
        {"quantity": 100, "gems": 1_100},
        {"quantity": 1_000, "gems": 10_000},
    ),
    "soul_crystal": (
        {"quantity": 1, "gems": 15},
        {"quantity": 10, "gems": 120},
        {"quantity": 100, "gems": 1_100},
        {"quantity": 1_000, "gems": 10_000},
    ),
}


def fetch_wikitext(page: str) -> str:
    query = urllib.parse.urlencode(
        {"action": "parse", "page": page, "prop": "wikitext", "format": "json"}
    )
    request = urllib.request.Request(
        f"{API_URL}?{query}", headers={"User-Agent": "RLMResearchPlanner data updater"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return str(payload["parse"]["wikitext"]["*"])


def first_upgrade_table(wikitext: str, page: str) -> str:
    headings = (
        r"==\s*Upgrade Results(?:(?:/| and )Requirements)?\s*==",
        r"==\s*Upgrade Requirements\s*&\s*Results\s*==",
        r"==\s*Requirements\s*==",
    )
    for heading in headings:
        sections = re.split(heading, wikitext, maxsplit=1, flags=re.IGNORECASE)
        if len(sections) < 2:
            continue
        section = sections[1]
        start = section.index("{|")
        end = section.index("|}", start)
        return section[start + 2 : end]
    raise ValueError(f"Upgrade Results section not found: {page}")


def tables_in_section(wikitext: str, heading: str) -> list[str]:
    sections = re.split(heading, wikitext, maxsplit=1, flags=re.IGNORECASE)
    if len(sections) < 2:
        return []
    section = sections[1]
    tables: list[str] = []
    offset = 0
    while True:
        start = section.find("{|", offset)
        if start < 0:
            break
        end = section.find("|}", start)
        if end < 0:
            break
        tables.append(section[start + 2 : end])
        offset = end + 2
    return tables


def parse_cells(block: str) -> list[str]:
    cells: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith(("!", "|")):
            marker = line[0]
            body = line[1:]
            separator = "!!" if marker == "!" else "||"
            parts = body.split(separator)
            cells.extend(part.strip() for part in parts)
        elif cells:
            cells[-1] = f"{cells[-1]}\n{line.strip()}"
    return cells


def clean_wiki(value: str) -> str:
    value = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"\{\{[^{}]*\}\}", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("'''", "").replace("''", "")
    return re.sub(r"[ \t]+", " ", value).strip()


def parse_integer(value: str) -> int:
    match = re.search(r"-?\d[\d,]*", clean_wiki(value))
    return int(match.group(0).replace(",", "")) if match else 0


def parse_duration(value: str) -> int | None:
    normalized = clean_wiki(value).strip()
    if not normalized or normalized.casefold() in {"n/a", "na"}:
        return None
    match = re.fullmatch(r"(?:(\d+)d\s*)?(\d+):(\d+):(\d+)", normalized)
    if not match:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def parse_requirements(value: str) -> tuple[list[dict[str, int | str]], int]:
    normalized = clean_wiki(value)
    requirements: list[dict[str, int | str]] = []
    for name, level in re.findall(
        r"([A-Za-z][A-Za-z ]*?)\s*[:,]?\s*Lv\.?\s*(\d+)",
        normalized,
        flags=re.IGNORECASE,
    ):
        building_id = NAME_TO_ID.get(re.sub(r"\s+", " ", name).strip().casefold())
        if building_id:
            requirements.append({"building_id": building_id, "level": int(level)})
    hammer = 0
    if "gold hammer" in normalized.casefold():
        match = re.search(r"Gold Hammer\s*(?:x|×)?\s*(\d+)", normalized, re.I)
        hammer = int(match.group(1)) if match else 1
    unique = {
        (str(item["building_id"]), int(item["level"])): item for item in requirements
    }
    return list(unique.values()), hammer


def parse_building(building_id: str, page: str, japanese_name: str) -> dict[str, object]:
    wikitext = fetch_wikitext(page)
    table = first_upgrade_table(wikitext, page)
    blocks = re.split(r"(?m)^\|-.*$", table)
    rows = [parse_cells(block) for block in blocks if parse_cells(block)]
    header_row = next(
        (
            index
            for index, row in enumerate(rows)
            if any(
                "Level" in value
                or re.fullmatch(r"Lvl?\.?", clean_wiki(value), re.I)
                for value in row
            )
            and any(re.search(r"\bReq", value, re.I) for value in row)
            and any("Time" in value for value in row)
        ),
        None,
    )
    if header_row is None:
        raise ValueError(f"Header row not found: {page}")
    headers = rows[header_row]
    level_index = next(
        (
            index
            for index, value in enumerate(headers)
            if "Level" in value
            or re.fullmatch(r"Lvl?\.?", clean_wiki(value), re.I)
        ),
        None,
    )
    if level_index is None:
        raise ValueError(f"Level column not found: {page}: {headers!r}")
    requirement_index = next(
        (
            index
            for index, value in enumerate(headers)
            if re.search(r"\bReq", value, flags=re.IGNORECASE)
        ),
        None,
    )
    if requirement_index is None:
        raise ValueError(f"Requirement column not found: {page}: {headers!r}")
    time_index = next(
        (index for index, value in enumerate(headers) if "Time" in value), None
    )
    if time_index is None:
        raise ValueError(f"Time column not found: {page}: {headers!r}")
    resource_columns: list[tuple[int, tuple[str, ...]]] = []
    for index, header in enumerate(headers):
        keys = tuple(
            key
            for key, label in RESOURCE_HEADERS
            if label.casefold() in header.casefold()
        )
        if keys:
            resource_columns.append((index, keys))
    levels: dict[str, object] = {}
    for cells in rows[header_row + 1 :]:
        if len(cells) <= level_index:
            continue
        level_text = clean_wiki(cells[level_index])
        if not re.fullmatch(r"\d+", level_text):
            continue
        level = int(level_text)
        if level < 1 or level > 25:
            continue
        costs = {key: 0 for key in BASE_BUILDING_COST_KEYS}
        if len(cells) <= max(requirement_index, time_index):
            levels[str(level)] = {
                "base_time_seconds": 0,
                "costs": costs,
                "requirements": [],
            }
            continue
        for index, keys in resource_columns:
            amount = parse_integer(cells[index]) if index < len(cells) else 0
            for key in keys:
                costs[key] = amount
        requirements, hammer = parse_requirements(cells[requirement_index])
        costs["gold_hammer"] = hammer
        levels[str(level)] = {
            "base_time_seconds": parse_duration(cells[time_index]),
            "costs": costs,
            "requirements": requirements,
        }
    if page == "Battle Hall":
        resource_tables = tables_in_section(
            wikitext,
            r"==\s*Resource Requirements\s*==",
        )
        resource_rows = []
        for resource_table in resource_tables:
            candidate_rows = [
                parse_cells(block)
                for block in re.split(r"(?m)^\|-.*$", resource_table)
                if parse_cells(block)
            ]
            if candidate_rows and any(
                "Level" in value for value in candidate_rows[0]
            ):
                resource_rows = candidate_rows
                break
        if not resource_rows:
            raise ValueError("Battle Hall resource table not found")
        resource_headers = resource_rows[0]
        resource_indexes = {
            key: index
            for index, header in enumerate(resource_headers)
            for key, label in RESOURCE_HEADERS
            if label.casefold() in header.casefold()
        }
        for cells in resource_rows[1:]:
            level_text = clean_wiki(cells[0]) if cells else ""
            if not re.fullmatch(r"\d+", level_text):
                continue
            level_source = levels.get(level_text)
            if not isinstance(level_source, dict):
                continue
            costs = level_source["costs"]
            assert isinstance(costs, dict)
            for key, index in resource_indexes.items():
                costs[key] = parse_integer(cells[index]) if index < len(cells) else 0
    return {
        "id": building_id,
        "names": {"ja-JP": japanese_name, "en-US": page},
        "max_level": 25,
        "levels": levels,
        "source_url": f"https://lordsmobile.fandom.com/wiki/{page.replace(' ', '_')}",
    }


def build_catalog() -> dict[str, object]:
    buildings = [
        parse_building(building_id, page, japanese)
        for building_id, (page, japanese) in BUILDINGS.items()
    ]
    # Every facility upgrade to Lv.25 consumes one Gold Hammer. Some wiki
    # tables omit the icon/cell, so do not interpret that presentation gap as
    # a zero cost.
    for building in buildings:
        level_25 = building["levels"].get("25")
        if level_25 is not None:
            level_25["costs"]["gold_hammer"] = max(
                1,
                int(level_25["costs"].get("gold_hammer", 0)),
            )
    return {
        "schema_version": 3,
        "dataset_id": "lords-mobile-castle-plan",
        "checked_on": date.today().isoformat(),
        "notes": "城Lv.1-25と到達経路上の施設について、公開WikiのUpgrade Resultsを収録。建設速度適用前の時間。",
        "sources": [
            "https://lordsmobile.fandom.com/wiki/Castle",
            "https://www.gamesguideinfo.com/lords-mobile/overview/buildings",
            "https://lm-harus.com/mana/",
            "https://lordsmobile.igg.com/project/game_tool/index.php?action=play_content&cate=7&lang=tha",
            "https://lordsgems.com/gem-calculator/",
        ],
        "source_licenses": [
            {
                "url": "https://lordsmobile.fandom.com/wiki/Castle",
                "license": "CC BY-SA 3.0 Unported",
                "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
                "licensing_terms_url": "https://www.fandom.com/licensing",
                "changes": "Normalized and adapted into project-specific structured records.",
            },
            {
                "url": "https://www.gamesguideinfo.com/lords-mobile/overview/buildings",
                "scope": "Factual verification reference; no redistribution license asserted.",
            },
            {
                "url": "https://lm-harus.com/mana/",
                "scope": "Factual verification reference; no redistribution license asserted.",
            },
            {
                "url": "https://lordsmobile.igg.com/project/game_tool/index.php?action=play_content&cate=7&lang=tha",
                "scope": "Official factual verification reference for advanced-building item quantities.",
            },
            {
                "url": "https://lordsgems.com/gem-calculator/",
                "scope": "Factual verification reference for in-game gem-shop item prices; no redistribution license asserted.",
            },
        ],
        "gem_shop_packs": GEM_SHOP_PACKS,
        "buildings": buildings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "data"
        / "buildings"
        / "castle_catalog.json",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog()
    if args.output.exists():
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        mana_progression = existing.get("castle_mana_progression")
        if mana_progression:
            catalog["castle_mana_progression"] = mana_progression
            catalog["notes"] = (
                "城Lv.1-25、個別施設Lv.1-25、特殊施設・特殊素材、および"
                "城Lv.25後のマナ強化について、公開資料の値を収録。"
                "建設時間は建設速度適用前。"
            )
    args.output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
