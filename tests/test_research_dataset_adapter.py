from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from rlm_research_planner.repositories.research_dataset_adapter import (
    observations_from_research_dataset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = PROJECT_ROOT / "dataset"
GENERATED_ROOT = DATASET_ROOT / "generated"
EXAMPLE_ROOT = DATASET_ROOT / "examples" / "minimal"


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _documents(root: Path) -> dict[str, object]:
    manifest = _read_json(root / "manifest.json")
    return {
        "manifest": manifest,
        "sources": _read_json(root / "sources.json"),
        "trees": {
            item["id"]: _read_json(root / item["path"])
            for item in manifest["trees"]
        },
        "locales": {
            item["locale"]: _read_json(root / item["path"])
            for item in manifest["locales"]
        },
    }


def test_shared_adapter_preserves_current_observation_behavior() -> None:
    observations = observations_from_research_dataset(_documents(GENERATED_ROOT))

    assert len(observations) == 16
    assert sum(len(item.nodes) for item in observations) == 399
    assert sum(len(item.edges) for item in observations) == 619
    assert all(
        item.observation_id == f"catalog-{item.category_id}"
        for item in observations
    )
    assert all(item.connection_groups for item in observations)

    guild_duel = next(
        item for item in observations if item.category_id == "guild_duel"
    )
    assert guild_duel.source_url == "https://www.youtube.com/watch?v=QKP5dGy1IHs"
    assert guild_duel.license_name == "Public gameplay reference (facts transcribed)"
    gathering = guild_duel.node_by_id()["guild_duel_gathering_incentive"].level_data(1)
    assert gathering is not None
    assert gathering.costs == {
        "food": 78_600,
        "stone": 32_600,
        "timber": 39_100,
        "ore": 19_600,
        "gold": 32_600,
        "special": 10,
    }
    assert gathering.base_time_seconds == 7_745
    assert gathering.power == 2_306
    assert gathering.costs_verified is False
    speed_up = guild_duel.node_by_id()["guild_duel_speed_up_incentive"].level_data(1)
    assert speed_up is not None
    assert speed_up.costs["special"] == 20
    assert speed_up.costs_verified is True


def test_shared_adapter_uses_explicit_display_fallback() -> None:
    documents = _documents(EXAMPLE_ROOT)
    effect_value = documents["trees"]["economy"]["nodes"][0]["effects"][0][
        "values"
    ][0]
    effect_value["value"] = "canonical value"
    effect_value["display_fallback"] = "Visible legacy value"

    observations = observations_from_research_dataset(documents)
    assert observations[0].nodes[0].effect_at(1) == "Visible legacy value"


def test_shared_adapter_rejects_effect_loss_in_compatibility_model() -> None:
    documents = _documents(EXAMPLE_ROOT)
    effects = documents["trees"]["economy"]["nodes"][0]["effects"]
    effects.append(copy.deepcopy(effects[0]))
    effects[1]["metric_id"] = "economy_second_effect"

    with pytest.raises(ValueError, match="supports at most one effect"):
        observations_from_research_dataset(documents)
