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
