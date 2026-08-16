from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "update_research_catalog.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "rlm_update_research_catalog", _SCRIPT_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
_research_only_wikitext = _MODULE._research_only_wikitext
_apply_guild_duel_level_one_inferences = (
    _MODULE._apply_guild_duel_level_one_inferences
)


def test_lunar_foundry_parser_excludes_building_upgrade_sections() -> None:
    source = """\
== Research ==
{| class="wikitable"
! Level !! Result !! Orig. Time
|-
| 1 || Unlocks Lunar Foundry || 13d 05:00:00
|}
== Construction Results and Requirements ==
{| class="wikitable"
! Level !! Orig. Time
|-
| 1 || 00:02:00
|}
== Mana upgrade ==
{| class="wikitable"
! Level !! Orig. Time
|-
| 1 ||
|-
| 2 ||
|}
"""

    research = _research_only_wikitext("Lunar Foundry", source)

    assert "13d 05:00:00" in research
    assert "Construction Results" not in research
    assert "Mana upgrade" not in research
    assert _research_only_wikitext("Construction Speed", source) == source


def test_guild_duel_level_one_inferences_remain_provisional() -> None:
    category = {
        "level_data": {
            "Stage Incentive": {
                "1": {
                    "requirements": [
                        {"research": "Artifact Incentive", "level": 1}
                    ]
                }
            }
        }
    }

    _apply_guild_duel_level_one_inferences(category)

    gathering = category["level_data"]["Gathering Incentive"]["1"]
    adventure = category["level_data"]["Stage Incentive"]["1"]
    assert gathering["base_time_seconds"] == 7745
    assert gathering["costs"]["special"] == 10
    assert adventure["base_time_seconds"] == 6372
    assert adventure["costs"]["ore"] == 115000
    assert adventure["requirements"] == [
        {"research": "Artifact Incentive", "level": 1}
    ]
    assert adventure["costs_verified"] is False
    assert (
        adventure["verification_status"]
        == "provisional_sibling_level_inference"
    )
