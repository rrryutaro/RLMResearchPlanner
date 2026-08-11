from __future__ import annotations

import argparse
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FANDOM_API = "https://lordsmobile.fandom.com/api.php"
JAPANESE_CATALOG_URL = (
    "https://lords-mobile.gamerch.com/"
    "%E7%A0%94%E7%A9%B6-%E7%A0%94%E7%A9%B6%E4%B8%80%E8%A6%A7"
)
JAPANESE_WONDER_NAMES_URL = (
    "https://retry0907yn.com/"
    "%E3%80%90%E3%83%AD%E3%83%BC%E3%83%A2%E3%83%90%E7%A0%94%E7%A9%B6%E3%80%91"
    "%E7%A0%94%E7%A9%B6%E3%83%91%E3%83%AF%E3%83%BC%E3%83%87%E3%83%BC%E3%82%BF"
    "%E5%AE%8C%E5%85%A8%E3%82%AC%E3%82%A4%E3%83%89-12/"
)
JAPANESE_ADVANCED_WONDER_NAMES_URL = (
    "https://retry0907yn.com/"
    "%E3%80%90%E3%83%AD%E3%83%BC%E3%83%A2%E3%83%90%E7%A0%94%E7%A9%B6%E3%80%91"
    "%E7%A0%94%E7%A9%B6%E3%83%91%E3%83%AF%E3%83%BC%E3%83%87%E3%83%BC%E3%82%BF"
    "%E5%AE%8C%E5%85%A8%E3%82%AC%E3%82%A4%E3%83%89-14/"
)
USER_AGENT = "RLMResearchPlanner/0.0.13 (research catalog maintenance)"
KNOWN_REQUIREMENT_CORRECTIONS: dict[
    tuple[str, str, int], tuple[tuple[str, int], ...]
] = {
    # The cited page creates an impossible cycle through Monster Hunt IV.
    ("monster_hunt", "Hunter Recovery II", 8): (),
    # The cited infantry page reverses the Defense -> Durability -> Offense tree.
    ("wonder_battles", "Infantry Durability (Wonder) II", 1): (
        ("Infantry Defense (Wonder) II", 1),
    ),
    ("wonder_battles", "Infantry Durability (Wonder) II", 2): (
        ("Infantry Defense (Wonder) II", 2),
    ),
    ("wonder_battles", "Infantry Durability (Wonder) II", 3): (
        ("Infantry Defense (Wonder) II", 3),
    ),
    ("wonder_battles", "Infantry Durability (Wonder) II", 4): (
        ("Infantry Defense (Wonder) II", 4),
    ),
}
UNLOCK_RESEARCH_NAMES = {
    "Spikes",
    "Archer Tower",
    "Spike Boulders",
    "Metal Spikes",
    "Sniper Tower",
    "Rolling Logs",
    "Hot Iron Spikes",
    "Fortified Tower",
    "Flame Boulders",
    "Burning Spikes",
    "Skyscraper",
    "Burning Logs",
    "Gladiator",
    "Catapult",
    "Sharpshooter",
    "Reptilian Rider",
    "Royal Guard",
    "Fire Trebuchet",
    "Stealth Sniper",
    "Royal Cavalry",
    "Heroic Fighter",
    "Destroyer",
    "Heroic Cannoneer",
    "Ancient Drake Rider",
    "Luminary Guard",
    "Luminary Avenger",
    "Luminary Marksman",
    "Luminary Lion Force",
}
MILITARY_CONNECTION_GROUPS = [
    {"prerequisites": ["Training Speed I"], "research": ["Intelligence Report", "Quick Maneuvers I"]},
    {"prerequisites": ["Intelligence Report"], "research": ["Infantry Offense I", "Siege Attack I"]},
    {"prerequisites": ["Quick Maneuvers I"], "research": ["Ranged Offense I", "Cavalry Offense I"]},
    {"prerequisites": ["Infantry Offense I"], "research": ["Infantry Defense I"]},
    {"prerequisites": ["Siege Attack I"], "research": ["Siege Toughness I"]},
    {"prerequisites": ["Ranged Offense I"], "research": ["Ranged Defense I"]},
    {"prerequisites": ["Cavalry Offense I"], "research": ["Cavalry Defense I"]},
    {"prerequisites": ["Infantry Defense I"], "research": ["Gladiator"]},
    {"prerequisites": ["Siege Toughness I"], "research": ["Catapult"]},
    {"prerequisites": ["Ranged Defense I"], "research": ["Sharpshooter"]},
    {"prerequisites": ["Cavalry Defense I"], "research": ["Reptilian Rider"]},
    {"prerequisites": ["Gladiator"], "research": ["Infantry Health I"]},
    {"prerequisites": ["Catapult"], "research": ["Siege Durability I"]},
    {"prerequisites": ["Sharpshooter"], "research": ["Ranged Health I"]},
    {"prerequisites": ["Reptilian Rider"], "research": ["Cavalry Health I"]},
    {"prerequisites": ["Infantry Health I"], "research": ["Royal Guard"]},
    {"prerequisites": ["Siege Durability I"], "research": ["Fire Trebuchet"]},
    {"prerequisites": ["Ranged Health I"], "research": ["Stealth Sniper"]},
    {"prerequisites": ["Cavalry Health I"], "research": ["Royal Cavalry"]},
    {
        "prerequisites": ["Royal Guard", "Fire Trebuchet", "Stealth Sniper", "Royal Cavalry"],
        "research": ["Army Offense I"],
    },
    {
        "prerequisites": ["Army Offense I"],
        "research": ["Army Defense I", "Army Health I"],
    },
    {
        "prerequisites": ["Army Offense I"],
        "research": ["Heroic Fighter", "Destroyer", "Heroic Cannoneer", "Ancient Drake Rider"],
    },
    {
        "prerequisites": ["Heroic Fighter", "Destroyer", "Heroic Cannoneer", "Ancient Drake Rider"],
        "research": ["Furious Defense I", "Furious Durability I"],
    },
    {"prerequisites": ["Furious Defense I", "Furious Durability I"], "research": ["Furious Offense I"]},
    {
        "prerequisites": ["Furious Offense I"],
        "research": ["Infantry-Ranged Counter Boost", "Ranged-Cavalry Counter Boost", "Cavalry-Infantry Counter Boost"],
    },
]
JAPANESE_SECTION_IDS = {
    "economy": "content_2_2",
    "defense": "content_2_3",
    "military": "content_2_4",
    "monster_hunt": "content_2_5",
    "upgrade_defenses": "content_2_6",
    "upgrade_military": "content_2_7",
    "army_leadership": "content_2_8",
    "military_command": "content_2_9",
    "familiars": "content_2_10",
    "familiar_battles": "content_2_11",
    "sigils": "content_2_12",
    "wonder_battles": "content_2_13",
    "gear": "content_2_14",
    "advanced_wonder_battles": "content_2_15",
    "mana_awakening": "content_2_16",
}
JAPANESE_CATEGORY_TITLES = {
    "economy": "経済",
    "defense": "城壁防御",
    "military": "軍事",
    "monster_hunt": "魔獣討伐",
    "upgrade_defenses": "上級防城",
    "upgrade_military": "上級軍事",
    "army_leadership": "軍隊戦術",
    "military_command": "軍事司令",
    "familiars": "召喚獣",
    "familiar_battles": "召喚獣の出陣",
    "sigils": "シギル",
    "wonder_battles": "ワンダー戦争",
    "gear": "部隊武装",
    "advanced_wonder_battles": "上級ワンダー軍事",
    "mana_awakening": "マナ覚醒",
}
JAPANESE_NAME_OVERRIDES = {
    "upgrade_defenses": {
        "Trap Retrieval I": "罠回収 I",
        "Wall Defense I": "城壁防御力 I",
        "Wall Repair I": "城壁修復 I",
        "Wall Durability I": "城壁HP I",
        "Trap Retrieval II": "罠回収 II",
        "Trap Defense II": "罠防御力 II",
        "Trap Strength II": "罠攻撃力 II",
        "Trap Durability II": "罠HP II",
        "Trap Retrieval III": "罠回収 III",
        "Wall Defense II": "城壁防御力 II",
        "Wall Repair II": "城壁修復 II",
        "Wall Durability II": "城壁HP II",
        "Trap Crafting II": "罠配置 II",
        "Trap Retrieval IV": "罠回収 IV",
    },
    "wonder_battles": {
        "Wonder March": "ワンダー戦争進軍速度I",
        "Infantry Offense (Wonder) I": "ワンダー戦争歩兵攻撃力I",
        "Ranged Offense (Wonder) I": "ワンダー戦争弓兵攻撃力I",
        "Cavalry Offense (Wonder) I": "ワンダー戦争騎兵攻撃力I",
        "Infantry Durability (Wonder) I": "ワンダー戦争歩兵HPI",
        "Ranged Durability (Wonder) I": "ワンダー戦争弓兵HPI",
        "Cavalry Durability (Wonder) I": "ワンダー戦争騎兵HPI",
        "Infantry Defense (Wonder) I": "ワンダー戦争歩兵防御力I",
        "Ranged Defense (Wonder) I": "ワンダー戦争弓兵防御力I",
        "Cavalry Defense (Wonder) I": "ワンダー戦争騎兵防御力I",
        "Wonder Rally I": "ワンダー戦争連合軍規模I",
        "Infantry Defense (Wonder) II": "ワンダー戦争歩兵防御力II",
        "Ranged Defense (Wonder) II": "ワンダー戦争弓兵防御力II",
        "Cavalry Defense (Wonder) II": "ワンダー戦争騎兵防御力II",
        "Infantry Durability (Wonder) II": "ワンダー戦争歩兵HPII",
        "Ranged Durability (Wonder) II": "ワンダー戦争弓兵HPII",
        "Cavalry Durability (Wonder) II": "ワンダー戦争騎兵HPII",
        "Infantry Offense (Wonder) II": "ワンダー戦争歩兵攻撃力II",
        "Ranged Offense (Wonder) II": "ワンダー戦争弓兵攻撃力II",
        "Cavalry Offense (Wonder) II": "ワンダー戦争騎兵攻撃力II",
        "Wonder Rally II": "ワンダー戦争連合軍規模II",
    },
    "advanced_wonder_battles": {
        "Wonder Rally Participant": "ワンダー戦争連合軍に参加規模",
        "Leadership (Infantry ATK) II": "ロード出陣歩兵攻撃力II",
        "Leadership (Siege ATK) II": "ロード出陣攻城兵器攻撃力II",
        "Leadership (Ranged ATK) II": "ロード出陣弓兵攻撃力II",
        "Leadership (Cavalry ATK) II": "ロード出陣騎兵攻撃力II",
        "Leadership (Infantry DEF) II": "ロード出陣歩兵防御力II",
        "Leadership (Siege DEF) II": "ロード出陣攻城兵器防御力II",
        "Leadership (Ranged DEF) II": "ロード出陣弓兵防御力II",
        "Leadership (Cavalry DEF) II": "ロード出陣騎兵防御力II",
        "Leadership (Infantry HP) II": "ロード出陣歩兵HPII",
        "Leadership (Siege HP) II": "ロード出陣攻城兵器HPII",
        "Leadership (Ranged HP) II": "ロード出陣弓兵HPII",
        "Leadership (Cavalry HP) II": "ロード出陣騎兵HPII",
        "Wonder March II": "ワンダー戦争進軍速度II",
        "Infantry Durability (Wonder) III": "ワンダー戦争歩兵HPIII",
        "Ranged Durability (Wonder) III": "ワンダー戦争弓兵HPIII",
        "Cavalry Durability (Wonder) III": "ワンダー戦争騎兵HPIII",
        "Infantry Offense (Wonder) III": "ワンダー戦争歩兵攻撃力III",
        "Ranged Offense (Wonder) III": "ワンダー戦争弓兵攻撃力III",
        "Cavalry Offense (Wonder) III": "ワンダー戦争騎兵攻撃力III",
        "Infantry Defense (Wonder) III": "ワンダー戦争歩兵防御力III",
        "Ranged Defense (Wonder) III": "ワンダー戦争弓兵防御力III",
        "Cavalry Defense (Wonder) III": "ワンダー戦争騎兵防御力III",
        "Infantry DEF Curse (Wonder)": "ワンダー戦争歩兵防御力呪詛",
        "Ranged DEF Curse (Wonder)": "ワンダー戦争弓兵防御力呪詛",
        "Cavalry DEF Curse (Wonder)": "ワンダー戦争騎兵防御力呪詛",
        "Infantry HP Curse (Wonder)": "ワンダー戦争歩兵HP呪詛",
        "Ranged HP Curse (Wonder)": "ワンダー戦争弓兵HP呪詛",
        "Cavalry HP Curse (Wonder)": "ワンダー戦争騎兵HP呪詛",
        "Infantry ATK Curse (Wonder)": "ワンダー戦争歩兵攻撃力呪詛",
        "Ranged ATK Curse (Wonder)": "ワンダー戦争弓兵攻撃力呪詛",
        "Cavalry ATK Curse (Wonder)": "ワンダー戦争騎兵攻撃力呪詛",
    },
    "mana_awakening": {
        "Field Triage III": "応急術III",
        "Barracks Expansion III": "兵舎拡張III",
        "Bigger Infirmary IV": "医療所拡張IV",
        "Mana Ore Harvesting II": "マナ鉱石生産量II",
        "Mana Ore Storage II": "マナ鉱石生産上限II",
        "Lunite Harvesting II": "月晶生産量II",
        "Lunite Storage II": "月晶生産上限II",
        "Mana Ore Harvesting III": "マナ鉱石生産量III",
        "Mana Ore Storage III": "マナ鉱石生産上限III",
        "Crafting Speed III": "部隊武装錬成速度III",
        "Crafting Capacity II": "部隊武装錬成数量II",
    },
}

GUILD_DUEL_VIDEO_URL = "https://www.youtube.com/watch?v=QKP5dGy1IHs"
GUILD_DUEL_ROWS = [
    [None, None, None, "Gathering Incentive", None, None, None],
    [
        "Hero Incentive",
        None,
        "Construction Incentive",
        None,
        "Research Incentive",
        None,
        "Training Incentive",
    ],
    [None, None, None, "Reward Incentive I", None, None, None],
    [
        None,
        "Army Colosseum DEF I",
        None,
        "Army Colosseum ATK I",
        None,
        "Army Colosseum HP I",
        None,
    ],
    [None, None, None, "Artifact Incentive", None, None, None],
    [
        None,
        "Speed-Up Incentive",
        None,
        "Stage Incentive",
        None,
        "Hunting Incentive",
        None,
    ],
    [None, None, None, "Reward Incentive II", None, None, None],
    [
        None,
        "Army DEF II",
        None,
        "Army ATK II",
        None,
        "Army HP II",
        None,
    ],
    [None, None, None, "Familiar Incentive", None, None, None],
    [
        None,
        "Army Colosseum DEF II",
        None,
        "Army Colosseum ATK II",
        None,
        "Army Colosseum HP II",
        None,
    ],
    [
        None,
        "Army DEF III",
        None,
        "Army ATK III",
        None,
        "Army HP III",
        None,
    ],
    [
        None,
        "Master Incentive",
        None,
        None,
        None,
        "Crafting Incentive",
        None,
    ],
]
GUILD_DUEL_JAPANESE_NAMES = {
    "Gathering Incentive": "採取インセンティブ",
    "Hero Incentive": "ヒーローインセンティブ",
    "Construction Incentive": "建設インセンティブ",
    "Research Incentive": "研究インセンティブ",
    "Training Incentive": "訓練インセンティブ",
    "Reward Incentive I": "報酬インセンティブ I",
    "Army Colosseum DEF I": "軍隊コロシアム防御力 I",
    "Army Colosseum ATK I": "軍隊コロシアム攻撃力 I",
    "Army Colosseum HP I": "軍隊コロシアムHP I",
    "Artifact Incentive": "アーティファクトインセンティブ",
    "Speed-Up Incentive": "加速インセンティブ",
    "Stage Incentive": "冒険インセンティブ",
    "Hunting Incentive": "討伐インセンティブ",
    "Reward Incentive II": "報酬インセンティブ II",
    "Army DEF II": "軍隊防御力 II",
    "Army ATK II": "軍隊攻撃力 II",
    "Army HP II": "軍隊HP II",
    "Familiar Incentive": "召喚獣インセンティブ",
    "Army Colosseum DEF II": "軍隊コロシアム防御力 II",
    "Army Colosseum ATK II": "軍隊コロシアム攻撃力 II",
    "Army Colosseum HP II": "軍隊コロシアムHP II",
    "Army DEF III": "軍隊防御力 III",
    "Army ATK III": "軍隊攻撃力 III",
    "Army HP III": "軍隊HP III",
    "Master Incentive": "マスターインセンティブ",
    "Crafting Incentive": "製作インセンティブ",
}


def _percentage_levels(step: int) -> dict[str, str]:
    return {str(level): f"+{level * step}%" for level in range(1, 11)}


def _guild_duel_edges() -> list[list[str]]:
    groups = [
        ["Gathering Incentive"],
        [
            "Hero Incentive",
            "Construction Incentive",
            "Research Incentive",
            "Training Incentive",
        ],
        ["Reward Incentive I"],
        [
            "Army Colosseum DEF I",
            "Army Colosseum ATK I",
            "Army Colosseum HP I",
        ],
        ["Artifact Incentive"],
        ["Speed-Up Incentive", "Stage Incentive", "Hunting Incentive"],
        ["Reward Incentive II"],
        ["Army DEF II", "Army ATK II", "Army HP II"],
        ["Familiar Incentive"],
        [
            "Army Colosseum DEF II",
            "Army Colosseum ATK II",
            "Army Colosseum HP II",
        ],
        ["Army DEF III", "Army ATK III", "Army HP III"],
        ["Master Incentive", "Crafting Incentive"],
    ]
    return [
        [prerequisite, research]
        for parents, children in zip(groups, groups[1:])
        for prerequisite in parents
        for research in children
    ]


def _apply_guild_duel_video_data(categories: list[dict[str, object]]) -> None:
    category = next(
        item for item in categories if str(item.get("id", "")) == "guild_duel"
    )
    names = [str(value) for row in GUILD_DUEL_ROWS for value in row if value]
    point_names = {
        "Gathering Incentive",
        "Hero Incentive",
        "Construction Incentive",
        "Research Incentive",
        "Training Incentive",
        "Artifact Incentive",
        "Speed-Up Incentive",
        "Stage Incentive",
        "Hunting Incentive",
        "Familiar Incentive",
        "Master Incentive",
        "Crafting Incentive",
    }
    colosseum_names = {name for name in names if name.startswith("Army Colosseum")}
    army_names = {name for name in names if name.startswith("Army ")} - colosseum_names
    effects: dict[str, dict[str, object]] = {}
    for name in point_names:
        effects[name] = {
            "label": f"{name.removesuffix(' Incentive')} Guild Duel points",
            "levels": _percentage_levels(5),
        }
    for name in colosseum_names:
        effects[name] = {
            "label": re.sub(r" (?:I|II|III)$", "", name),
            "levels": _percentage_levels(5),
        }
    for name in army_names:
        effects[name] = {
            "label": re.sub(r" (?:I|II|III)$", "", name),
            "levels": _percentage_levels(1),
        }
    for name in ("Reward Incentive I", "Reward Incentive II"):
        effects[name] = {
            "label": "Guild Duel reward boost",
            "levels": {"1": "Unlocked"},
        }
    category["rows"] = GUILD_DUEL_ROWS
    category["localized_names"] = {
        name: {"ja-JP": translated}
        for name, translated in GUILD_DUEL_JAPANESE_NAMES.items()
    }
    category["max_levels"] = {
        name: 1 if name.startswith("Reward Incentive") else 10 for name in names
    }
    category["effects"] = effects
    category["edges"] = _guild_duel_edges()
    category["verification_status"] = "video_verified_layout_levels_effects"
    category["scope"] = "full_tree_from_public_gameplay_video"
    category["source_url"] = GUILD_DUEL_VIDEO_URL
    category["license_name"] = "Public gameplay reference (facts transcribed)"
    category["notes"] = (
        "公開プレイ映像で全26ノードの配置、接続、最大レベル、効果を確認。"
        "英語・日本語名は映像内ポルトガル語名からの表示用翻訳。"
    )


def _request_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def _batched(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _normalize_title(value: str) -> str:
    return " ".join(value.replace("_", " ").split()).casefold()


def _fetch_wikitexts(titles: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for batch in _batched(titles, 30):
        parameters = urlencode(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(batch),
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            }
        )
        raw = json.loads(_request_text(f"{FANDOM_API}?{parameters}"))
        query = raw.get("query", {})
        replacements: dict[str, str] = {}
        for key in ("normalized", "redirects"):
            for item in query.get(key, []):
                replacements[_normalize_title(str(item["from"]))] = str(item["to"])
        pages = {
            _normalize_title(str(page.get("title", ""))): page
            for page in query.get("pages", [])
        }
        for requested in batch:
            resolved = requested
            visited: set[str] = set()
            while _normalize_title(resolved) in replacements:
                normalized = _normalize_title(resolved)
                if normalized in visited:
                    break
                visited.add(normalized)
                resolved = replacements[normalized]
            page = pages.get(_normalize_title(resolved))
            revisions = page.get("revisions", []) if page else []
            if not revisions:
                result[requested] = ""
                continue
            result[requested] = str(
                revisions[0].get("slots", {}).get("main", {}).get("content", "")
            )
    return result


def _strip_wikitext(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    value = re.sub(r"<br\s*/?>", " / ", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\{\{Pic(?: 2)?\|.*?\}\}", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\{\{[^{}]*\}\}", "", value)
    value = re.sub(
        r"\[\[(?:File|Image):[^\]]+\]\]", "", value, flags=re.IGNORECASE
    )
    value = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", value)
    value = re.sub(r"\[\[([^\]]+)\]\]", r"\1", value)
    value = value.replace("'''", "").replace("''", "")
    value = html.unescape(value)
    return " ".join(value.split()).strip(" |")


def _header_label(value: str) -> str:
    picture = re.search(r"\{\{Pic(?: 2)?\|([^{}]+)\}\}", value, re.IGNORECASE)
    if picture:
        parts = [part.strip() for part in picture.group(1).split("|")]
        named = [part.split("=", 1)[1] for part in parts if "=" in part]
        candidates = named or parts
        for candidate in reversed(candidates):
            if candidate and not candidate.isdigit():
                return _strip_wikitext(candidate)
    return _strip_wikitext(value)


def _integer(value: str) -> int | None:
    text = _strip_wikitext(value).strip()
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None


def _duration_seconds(value: str) -> int | None:
    text = _strip_wikitext(value).strip().replace(".", ":")
    if not text:
        return None
    match = re.fullmatch(
        r"(?:(\d+)\s*d\s*)?(\d+)\s*:\s*(\d+)\s*:\s*(\d+)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    days, hours, minutes, seconds = (
        int(value or 0) for value in match.groups()
    )
    return days * 86_400 + hours * 3_600 + minutes * 60 + seconds


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _column_index(headers: list[str], *names: str) -> int:
    normalized = [_normalized_header(header) for header in headers]
    candidates = {_normalized_header(name) for name in names}
    return next(
        (index for index, header in enumerate(normalized) if header in candidates),
        -1,
    )


def _table_cells(row: str, marker: str = "|") -> list[str]:
    cells: list[str] = []
    for raw_line in row.splitlines():
        line = raw_line.rstrip()
        if (
            line.startswith(marker)
            and not line.startswith(marker + "-")
            and not line.startswith("|}")
        ):
            parts = line[1:].split(marker * 2)
            for part in parts:
                part = part.strip()
                style_match = re.match(r"(?:[^|]+)\|\s*(.*)", part)
                if style_match and ("style=" in part or "rowspan=" in part):
                    part = style_match.group(1)
                cells.append(part)
        elif cells and line and not line.startswith(("!", "{|", "|}")):
            cells[-1] += "\n" + line
    return cells


def _upgrade_table(wikitext: str) -> tuple[list[str], list[list[str]]]:
    for table in re.findall(r"\{\|.*?\n\|\}", wikitext, flags=re.DOTALL):
        if not re.search(r"(?m)^!\s*Level\s*$", table, flags=re.IGNORECASE):
            continue
        if "Orig. Time" not in table:
            continue
        first_data_row = re.search(r"(?m)^\|-\s*\n\|\s*\d+\s*$", table)
        before_rows = table[: first_data_row.start()] if first_data_row else table
        headers = [_header_label(cell) for cell in _table_cells(before_rows, marker="!")]
        rows: list[list[str]] = []
        for raw_row in re.split(r"(?m)^\|-\s*$", table)[1:]:
            cells = _table_cells(raw_row)
            if not cells:
                continue
            level_text = _strip_wikitext(cells[0])
            if not level_text.isdigit():
                continue
            rows.append(cells)
        if rows:
            rows_by_level = {
                int(_strip_wikitext(row[0])): row
                for row in rows
                if _strip_wikitext(row[0]).isdigit()
            }
            consecutive_rows: list[list[str]] = []
            expected_level = 1
            while expected_level in rows_by_level:
                consecutive_rows.append(rows_by_level[expected_level])
                expected_level += 1
            if consecutive_rows:
                return headers, consecutive_rows
    return [], []


def _research_only_wikitext(name: str, wikitext: str) -> str:
    """Exclude same-named building upgrade tables from research parsing.

    The Lunar Foundry page contains the one-level unlock research as well as
    the building's construction and mana-upgrade tables.  Parsing the whole
    page can select the six-row mana-upgrade table and turn those building
    stages into research levels.
    """

    if name != "Lunar Foundry":
        return wikitext
    match = re.search(
        r"(?ims)^==\s*Research\s*==\s*(.*?)(?=^==\s*[^=].*?\s*==\s*$|\Z)",
        wikitext,
    )
    return match.group(1) if match else wikitext


MATERIAL_HEADERS = {
    "food": "food",
    "stone": "stone",
    "timber": "timber",
    "ore": "ore",
    "gold": "gold",
    "archaic tome": "ancient_tomes",
    "ancient tome": "ancient_tomes",
    "mana ore": "mana_ore",
    "lunite": "lunite",
}


def _resource_costs(wikitext: str) -> dict[int, dict[str, int]]:
    result: dict[int, dict[str, int]] = {}
    for table in re.findall(r"\{\|.*?\n\|\}", wikitext, flags=re.DOTALL):
        if "Orig. Time" in table:
            continue
        first_data_row = re.search(r"(?m)^\|-\s*\n\|\s*\d+\s*$", table)
        before_rows = table[: first_data_row.start()] if first_data_row else table
        headers = [_header_label(cell) for cell in _table_cells(before_rows, marker="!")]
        material_columns = {
            index: MATERIAL_HEADERS[_normalized_header(header)]
            for index, header in enumerate(headers)
            if _normalized_header(header) in MATERIAL_HEADERS
        }
        if not material_columns or _column_index(headers, "Level") < 0:
            continue
        for raw_row in re.split(r"(?m)^\|-\s*$", table)[1:]:
            cells = _table_cells(raw_row)
            if not cells:
                continue
            level = _integer(cells[0])
            if level is None:
                continue
            costs = result.setdefault(level, {})
            for index, material in material_columns.items():
                if index >= len(cells):
                    continue
                amount = _integer(cells[index])
                if amount is not None:
                    costs[material] = amount
    return result


def _plain_research_requirements(
    value: str,
    research_names: list[str],
    current_name: str,
) -> list[dict[str, object]]:
    text = _strip_wikitext(value)
    requirements: list[dict[str, object]] = []
    occupied: list[tuple[int, int]] = []
    for research_name in sorted(research_names, key=len, reverse=True):
        if research_name == current_name:
            continue
        aliases = [research_name]
        without_one = re.sub(r"\s+I$", "", research_name)
        if without_one != research_name:
            aliases.append(without_one)
        found = None
        for alias in aliases:
            match = re.search(
                rf"(?<![A-Za-z0-9]){re.escape(alias)}\s+Lv\.?\s*(\d+)",
                text,
                re.IGNORECASE,
            )
            if match and not any(
                match.start() < end and match.end() > start
                for start, end in occupied
            ):
                found = match
                break
        if found:
            requirements.append(
                {"research": research_name, "level": int(found.group(1))}
            )
            occupied.append(found.span())
    return requirements


def _mixed_table_cells(row: str) -> list[str]:
    cells: list[str] = []
    for raw_line in row.splitlines():
        line = raw_line.rstrip()
        if line.startswith(("|", "!")) and not line.startswith(("|-", "|}")):
            marker = line[0]
            parts = line[1:].split(marker * 2)
            for part in parts:
                part = part.strip()
                style_match = re.match(r"(?:[^|]+)\|\s*(.*)", part)
                if style_match and ("style=" in part or "rowspan=" in part):
                    part = style_match.group(1)
                cells.append(part)
        elif cells and line and not line.startswith(("{|", "|}")):
            cells[-1] += "\n" + line
    return cells


def _unlock_level_data(
    trap_wikitext: str,
    troop_wikitext: str,
    research_names: list[str],
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    known_unlocks = set(UNLOCK_RESEARCH_NAMES)
    for wikitext in (trap_wikitext, troop_wikitext):
        for table in re.findall(r"\{\|.*?\n\|\}", wikitext, flags=re.DOTALL):
            first_data_row = re.search(r"(?m)^\|-\s*\n[|!]", table)
            before_rows = table[: first_data_row.start()] if first_data_row else table
            headers = [
                _header_label(cell) for cell in _table_cells(before_rows, marker="!")
            ]
            normalized_headers = {_normalized_header(header) for header in headers}
            if not {
                "might",
                "requirements",
                "clock",
                "food",
                "stone",
                "timber",
                "ore",
                "gold",
            }.issubset(normalized_headers):
                continue
            has_tomes = "archaic tome" in normalized_headers
            shared_power: int | None = None
            shared_time: int | None = None
            shared_tomes: int | None = None
            for raw_row in re.split(r"(?m)^\|-\s*$", table)[1:]:
                cells = _mixed_table_cells(raw_row)
                if not cells:
                    continue
                unlock_name = ""
                for cell in cells:
                    plain = _strip_wikitext(cell)
                    match = re.match(r"^Unlocks?\s+(.+)$", plain, re.IGNORECASE)
                    candidate = match.group(1).strip() if match else ""
                    if candidate in known_unlocks:
                        unlock_name = candidate
                        break
                if not unlock_name:
                    for cell in cells:
                        candidate = _header_label(cell).strip()
                        if candidate in known_unlocks:
                            unlock_name = candidate
                            break
                if not unlock_name:
                    continue
                requirement_index = next(
                    (
                        index
                        for index, cell in enumerate(cells)
                        if re.search(r"(?:Mana\s+)?Academy\s+Lv", _strip_wikitext(cell), re.IGNORECASE)
                    ),
                    -1,
                )
                requirement_text = cells[requirement_index] if requirement_index >= 0 else ""
                explicit_power = next(
                    (
                        _integer(cells[index])
                        for index in range(max(0, requirement_index))
                        if _integer(cells[index]) is not None
                    ),
                    None,
                )
                explicit_time = next(
                    (
                        parsed
                        for cell in cells
                        if (parsed := _duration_seconds(cell)) is not None
                    ),
                    None,
                )
                if explicit_power is not None:
                    shared_power = explicit_power
                if explicit_time is not None:
                    shared_time = explicit_time
                material_count = (
                    6 if has_tomes and len(cells) >= len(headers) else 5
                )
                material_cells = cells[-material_count:]
                material_names = ["food", "stone", "timber", "ore", "gold"]
                costs = {
                    material: amount
                    for material, cell in zip(material_names, material_cells[:5])
                    if (amount := _integer(cell)) is not None
                }
                if has_tomes:
                    explicit_tomes = (
                        _integer(material_cells[5])
                        if len(material_cells) > 5
                        else None
                    )
                    if explicit_tomes is not None:
                        shared_tomes = explicit_tomes
                    if shared_tomes is not None:
                        costs["ancient_tomes"] = shared_tomes
                academy = re.search(
                    r"(?<!Mana )Academy\s+Lv\.?\s*(\d+)",
                    _strip_wikitext(requirement_text),
                    re.IGNORECASE,
                )
                complete = (
                    shared_power is not None
                    and shared_time is not None
                    and all(material in costs for material in material_names)
                )
                result[unlock_name] = {
                    "academy_level": int(academy.group(1)) if academy else None,
                    "base_time_seconds": shared_time,
                    "power": shared_power,
                    "costs": costs,
                    "costs_verified": len(costs) >= 5,
                    "requirements": _plain_research_requirements(
                        requirement_text, research_names, unlock_name
                    ),
                    "buildings": {},
                    "verification_status": "sourced" if complete else "sourced_partial",
                }
    return result


def _level_data_from_page(
    name: str,
    wikitext: str,
    research_names: list[str],
) -> dict[str, dict[str, object]]:
    headers, rows = _upgrade_table(wikitext)
    if not rows:
        return {}
    might_index = _column_index(headers, "Might")
    requirement_index = next(
        (
            index
            for index, header in enumerate(headers)
            if _normalized_header(header).startswith(("requirement", "require"))
        ),
        -1,
    )
    time_index = _column_index(headers, "Orig. Time")
    technolabe_index = next(
        (
            index
            for index, header in enumerate(headers)
            if _normalized_header(header) in {"technolabe", "technolabes"}
        ),
        -1,
    )
    embedded_material_columns = {
        index: MATERIAL_HEADERS[_normalized_header(header)]
        for index, header in enumerate(headers)
        if _normalized_header(header) in MATERIAL_HEADERS
    }
    resource_costs = _resource_costs(wikitext)
    level_data: dict[str, dict[str, object]] = {}
    for row in rows:
        level = _integer(row[0])
        if level is None:
            continue
        requirement_text = (
            row[requirement_index]
            if 0 <= requirement_index < len(row)
            else ""
        )
        buildings: dict[str, int] = {}
        academy = re.search(
            r"(?<!Mana )Academy\s+Lv\.?\s*(\d+)",
            _strip_wikitext(requirement_text),
            re.IGNORECASE,
        )
        mana_academy = re.search(
            r"Mana\s+Academy\s+Lv\.?\s*(\d+)",
            _strip_wikitext(requirement_text),
            re.IGNORECASE,
        )
        if mana_academy:
            buildings["mana_academy"] = int(mana_academy.group(1))
        costs = dict(resource_costs.get(level, {}))
        for index, material in embedded_material_columns.items():
            if index < len(row):
                amount = _integer(row[index])
                if amount is not None:
                    costs[material] = amount
        base_time = (
            _duration_seconds(row[time_index])
            if 0 <= time_index < len(row)
            else None
        )
        power = _integer(row[might_index]) if 0 <= might_index < len(row) else None
        technolabe_count = (
            _integer(row[technolabe_index])
            if 0 <= technolabe_index < len(row)
            else None
        )
        costs_verified = level in resource_costs or bool(embedded_material_columns)
        complete = base_time is not None and power is not None and costs_verified
        level_data[str(level)] = {
            "academy_level": int(academy.group(1)) if academy else None,
            "base_time_seconds": base_time,
            "technolabe_count": technolabe_count,
            "power": power,
            "costs": costs,
            "costs_verified": costs_verified,
            "requirements": _plain_research_requirements(
                requirement_text, research_names, name
            ),
            "buildings": buildings,
            "verification_status": "sourced" if complete else "sourced_partial",
        }
    return level_data


def _research_links(value: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r"\[\[([^\]]+)\]\]", value):
        parts = match.group(1).split("|", 1)
        target = parts[0].split("#", 1)[0]
        display = parts[1] if len(parts) > 1 else target
        for candidate in (display, target):
            normalized = " ".join(candidate.replace("_", " ").split())
            if normalized and normalized not in links:
                links.append(normalized)
    return links


def _research_tree_rows(wikitext: str) -> list[list[str | None]]:
    match = re.search(
        r"==\s*Available Research\s*==.*?(\{\|.*?\n\|\})",
        wikitext,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return []
    rows: list[list[str | None]] = []
    table = match.group(1)
    table_body = table.split("\n", 1)[1]
    for raw_row in re.split(r"(?m)^\|-\s*$", table_body):
        cells = _table_cells(raw_row)
        if not cells:
            continue
        row: list[str | None] = []
        for cell in cells:
            links = _research_links(cell)
            value = links[0] if links else _strip_wikitext(cell)
            row.append(value or None)
        if any(value is not None for value in row):
            rows.append(row)
    return rows


class _JapaneseNameParser(HTMLParser):
    def __init__(self, section_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.section_id = section_id
        self.in_section = False
        self.in_table = False
        self.table_depth = 0
        self.cell_tag = ""
        self.cell_text: list[str] = []
        self.names: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "div" and values.get("id") == self.section_id:
            self.in_section = True
            return
        if (
            self.in_section
            and not self.in_table
            and tag == "div"
            and str(values.get("id", "")).startswith("content_2_")
        ):
            self.in_section = False
            return
        if not self.in_section:
            return
        if tag == "table":
            if not self.in_table:
                self.in_table = True
                self.table_depth = 1
            else:
                self.table_depth += 1
            return
        if self.in_table and tag == "th":
            self.cell_tag = tag
            self.cell_text = []

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and tag == "th" and self.cell_tag == "th":
            text = "".join(self.cell_text)
            text = " ".join(text.replace("アップ", "").split())
            if text:
                self.names.append(text)
            self.cell_tag = ""
            self.cell_text = []
            return
        if self.in_table and tag == "table":
            self.table_depth -= 1
            if self.table_depth <= 0:
                self.in_table = False
                self.in_section = False

    def handle_data(self, data: str) -> None:
        if self.cell_tag:
            self.cell_text.append(data)


def _fetch_japanese_names(catalog: dict[str, object]) -> dict[str, list[str]]:
    source = _request_text(JAPANESE_CATALOG_URL)
    result: dict[str, list[str]] = {}
    for category in catalog["categories"]:
        category_id = str(category["id"])
        section_id = JAPANESE_SECTION_IDS.get(category_id)
        if not section_id:
            continue
        parser = _JapaneseNameParser(section_id)
        parser.feed(source)
        result[category_id] = parser.names
    return result


def _catalog_names(category: dict[str, object]) -> list[str]:
    return [
        str(value)
        for row in category.get("rows", [])
        for value in row
        if value is not None
    ]


def _apply_known_requirement_corrections(
    categories: list[dict[str, object]],
) -> None:
    categories_by_id = {str(category.get("id", "")): category for category in categories}
    for (category_id, research_name, level), requirements in (
        KNOWN_REQUIREMENT_CORRECTIONS.items()
    ):
        category = categories_by_id.get(category_id)
        if category is None:
            continue
        level_data = category.get("level_data", {})
        if not isinstance(level_data, dict):
            continue
        research_levels = level_data.get(research_name, {})
        if not isinstance(research_levels, dict):
            continue
        record = research_levels.get(str(level))
        if not isinstance(record, dict):
            continue
        record["requirements"] = [
            {"research": prerequisite, "level": prerequisite_level}
            for prerequisite, prerequisite_level in requirements
        ]
        record["verification_status"] = (
            "sourced_conflict_corrected"
            if requirements
            else "sourced_conflict_omitted"
        )


def _add_layout_fallback_edges(
    rows: list[list[str | None]], edges: set[tuple[str, str]]
) -> None:
    incoming = {research for _prerequisite, research in edges}
    nonempty_rows = [
        (row_index, [(column, name) for column, name in enumerate(row) if name])
        for row_index, row in enumerate(rows)
        if any(row)
    ]
    for index, (_row_index, current) in enumerate(nonempty_rows):
        if index == 0:
            continue
        _previous_row_index, previous = nonempty_rows[index - 1]
        for column, name in current:
            if name in incoming:
                continue
            if len(previous) == 1:
                parents = previous
            elif len(current) == 1:
                parents = previous
            else:
                distance = min(abs(parent_column - column) for parent_column, _ in previous)
                parents = [
                    parent
                    for parent in previous
                    if abs(parent[0] - column) == distance
                ]
            for _parent_column, parent_name in parents:
                if parent_name != name:
                    edges.add((str(parent_name), str(name)))
            incoming.add(str(name))


def enrich_catalog(catalog: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    categories = list(catalog["categories"])
    _apply_guild_duel_video_data(categories)
    for category in categories:
        japanese_title = JAPANESE_CATEGORY_TITLES.get(str(category["id"]))
        if japanese_title:
            category.setdefault("titles", {})["ja-JP"] = japanese_title
    category_titles = [
        str(category.get("titles", {}).get("en-US", ""))
        for category in categories
        if category.get("rows")
    ]
    category_pages = _fetch_wikitexts(category_titles)
    layout_mismatches: dict[str, tuple[int, int]] = {}
    for category in categories:
        old_names = _catalog_names(category)
        title = str(category.get("titles", {}).get("en-US", ""))
        rows = _research_tree_rows(category_pages.get(title, ""))
        new_names = [str(value) for row in rows for value in row if value]
        if rows and set(new_names) == set(old_names):
            category["rows"] = rows
        elif rows:
            layout_mismatches[str(category["id"])] = (
                len(old_names),
                len(new_names),
            )
    names = [name for category in categories for name in _catalog_names(category)]
    pages = _fetch_wikitexts(names)
    shared_unlock_pages = _fetch_wikitexts(["Trap", "Troop"])
    unlock_level_data = _unlock_level_data(
        shared_unlock_pages.get("Trap", ""),
        shared_unlock_pages.get("Troop", ""),
        names,
    )
    japanese_names = _fetch_japanese_names(catalog)

    name_lookup: dict[str, str] = {}
    for name in names:
        variants = {name, re.sub(r"\s+I$", "", name)}
        for variant in variants:
            key = _normalize_title(variant)
            if key not in name_lookup:
                name_lookup[key] = name
            elif name_lookup[key] != name:
                name_lookup[key] = ""

    missing_pages: list[str] = []
    missing_values: list[str] = []
    partial_level_data: list[str] = []
    japanese_mismatches: dict[str, tuple[int, int]] = {}
    total_edges = 0
    total_level_rows = 0
    for category in categories:
        category_names = _catalog_names(category)
        if str(category["id"]) == "military":
            category["connection_groups"] = MILITARY_CONNECTION_GROUPS
        if str(category["id"]) == "guild_duel":
            total_edges += len(category.get("edges", []))
            continue
        row_by_name = {
            str(name): row_index
            for row_index, row in enumerate(category.get("rows", []))
            for name in row
            if name
        }
        translated = japanese_names.get(str(category["id"]), [])
        if translated and (
            len(translated) == len(category_names)
            or str(category["id"]) == "wonder_battles"
        ):
            category["localized_names"] = {
                name: {"ja-JP": translated[index]}
                for index, name in enumerate(category_names[: len(translated)])
            }
        if translated and len(translated) != len(category_names):
            japanese_mismatches[str(category["id"])] = (
                len(category_names),
                len(translated),
            )
        overrides = JAPANESE_NAME_OVERRIDES.get(str(category["id"]), {})
        if overrides:
            localized_names = category.setdefault("localized_names", {})
            for name, translated_name in overrides.items():
                localized_names[name] = {"ja-JP": translated_name}

        max_levels: dict[str, int] = {}
        effects: dict[str, dict[str, object]] = {}
        level_data_by_name: dict[str, dict[str, dict[str, object]]] = {}
        edge_pairs: set[tuple[str, str]] = set()
        for name in category_names:
            wikitext = pages.get(name, "")
            if not wikitext:
                if name in UNLOCK_RESEARCH_NAMES:
                    max_levels[name] = 1
                    effects[name] = {
                        "label": "Unlock",
                        "levels": {"1": f"Unlocks {name}"},
                    }
                    sourced_unlock = unlock_level_data.get(name)
                    if sourced_unlock:
                        level_data_by_name[name] = {"1": sourced_unlock}
                        total_level_rows += 1
                        if sourced_unlock["verification_status"] != "sourced":
                            partial_level_data.append(name)
                else:
                    missing_pages.append(name)
                continue
            research_wikitext = _research_only_wikitext(name, wikitext)
            headers, rows = _upgrade_table(research_wikitext)
            if not rows:
                missing_values.append(name)
                continue
            levels = [int(_strip_wikitext(row[0])) for row in rows]
            max_levels[name] = max(levels)
            metadata_headers = {
                "level",
                "might",
                "requirements",
                "requirement",
                "requires",
                "orig time",
                "technolabe",
                "technolabes",
                *MATERIAL_HEADERS,
            }
            effect_index = next(
                (
                    index
                    for index, header in enumerate(headers)
                    if index > 0 and _normalized_header(header) not in metadata_headers
                ),
                -1,
            )
            if effect_index >= 0:
                label = headers[effect_index] or "Effect"
                level_values = {
                    str(int(_strip_wikitext(row[0]))): _strip_wikitext(
                        row[effect_index]
                    )
                    for row in rows
                    if effect_index < len(row)
                }
                effects[name] = {"label": label, "levels": level_values}
            elif max(levels) == 1:
                effects[name] = {
                    "label": "Unlock",
                    "levels": {"1": f"Unlocks {name}"},
                }
            parsed_level_data = _level_data_from_page(
                name, research_wikitext, names
            )
            if parsed_level_data:
                level_data_by_name[name] = parsed_level_data
                total_level_rows += len(parsed_level_data)
                if any(
                    level["verification_status"] != "sourced"
                    for level in parsed_level_data.values()
                ):
                    partial_level_data.append(name)
            requirement_index = next(
                (
                    index
                    for index, header in enumerate(headers)
                    if header.casefold().startswith(("requirement", "require"))
                ),
                -1,
            )
            if requirement_index >= 0:
                for row in rows:
                    if requirement_index >= len(row):
                        continue
                    for linked in _research_links(row[requirement_index]):
                        prerequisite = name_lookup.get(_normalize_title(linked), "")
                        if (
                            prerequisite in row_by_name
                            and prerequisite != name
                            and row_by_name[prerequisite] < row_by_name[name]
                        ):
                            edge_pairs.add((prerequisite, name))
        _add_layout_fallback_edges(category.get("rows", []), edge_pairs)
        if str(category["id"]) == "military":
            edge_pairs = {
                (str(prerequisite), str(research))
                for group in MILITARY_CONNECTION_GROUPS
                for prerequisite in group["prerequisites"]
                for research in group["research"]
            }
        if max_levels:
            category["max_levels"] = max_levels
        if effects:
            category["effects"] = effects
        if level_data_by_name:
            category["level_data"] = level_data_by_name
        category["edges"] = [list(pair) for pair in sorted(edge_pairs)]
        total_edges += len(edge_pairs)
        if (
            category_names
            and len(max_levels) == len(category_names)
            and len(effects) == len(category_names)
        ):
            category["verification_status"] = "sourced_layout_levels_effects_prerequisites"
        elif category_names:
            category["verification_status"] = "sourced_layout_partial_values"

    _apply_known_requirement_corrections(categories)
    catalog["dataset_id"] = "lords-mobile-research-name-catalog-2026-08-07"
    catalog["checked_on"] = "2026-08-07"
    catalog["notes"] = (
        "研究名・配置・接続・最大レベル・レベル別効果を参照元から収録する。"
        "日本語名はGamerchと公開の日本語研究一覧、その他の値はCC BY-SAの"
        "Lords Mobile Wikiを参照。"
    )
    existing_sources = list(catalog.get("sources", []))
    primary_source = catalog.pop("source", None)
    if primary_source is None:
        primary_source = next(
            (
                source
                for source in existing_sources
                if source.get("name") == "Lords Mobile Wiki (Fandom)"
            ),
            {
                "name": "Lords Mobile Wiki (Fandom)",
                "url": "https://lordsmobile.fandom.com/wiki/Research",
                "license": "CC BY-SA 3.0 Unported",
                "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
                "licensing_terms_url": "https://www.fandom.com/licensing",
                "changes": "Normalized and adapted into project-specific structured records.",
            },
        )
    primary_source.update(
        {
            "license": "CC BY-SA 3.0 Unported",
            "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
            "licensing_terms_url": "https://www.fandom.com/licensing",
            "changes": "Normalized and adapted into project-specific structured records.",
        }
    )
    catalog["data_license"] = {
        "document": "DATA_LICENSE.md",
        "fandom_adapted_portions": "CC BY-SA 3.0 Unported",
    }
    catalog["sources"] = [
        primary_source,
        {
            "name": "Gamerch ロードモバイル攻略Wiki 研究一覧",
            "url": JAPANESE_CATALOG_URL,
            "scope": "Japanese research names and tree layout",
        },
        {
            "name": "Retry YN ワンダー戦争研究一覧",
            "url": JAPANESE_WONDER_NAMES_URL,
            "scope": "Wonder Battles Japanese research names",
        },
        {
            "name": "Retry YN 上級ワンダー軍事研究一覧",
            "url": JAPANESE_ADVANCED_WONDER_NAMES_URL,
            "scope": "Advanced Wonder Battles Japanese research names",
        },
        {
            "name": "BigSoneca Guild Duel gameplay video",
            "url": GUILD_DUEL_VIDEO_URL,
            "scope": "Guild Duel tree layout, levels, and effects",
        },
    ]
    report = {
        "categories": len(categories),
        "nodes": len(names),
        "edges": total_edges,
        "missing_pages": missing_pages,
        "missing_values": missing_values,
        "partial_level_data": partial_level_data,
        "level_rows": total_level_rows,
        "japanese_mismatches": japanese_mismatches,
        "layout_mismatches": layout_mismatches,
    }
    return catalog, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    catalog, report = enrich_catalog(catalog)
    if args.write:
        args.catalog.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["missing_pages"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
