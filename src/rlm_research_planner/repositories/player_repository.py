from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rlm_research_planner.domain.models import (
    PaidItem,
    PaidOffer,
    PaidValuation,
    PlayerSettings,
    PlayerState,
    ResearchPlanTask,
    RESOURCE_KEYS,
    SpeedupInventoryItem,
    max_guild_helps_for_castle,
)
from rlm_research_planner.services.calculation import (
    free_speedup_seconds_for_vip,
    vip_level_for_free_speedup_seconds,
)


SCHEMA_VERSION = 1


def _speedup_inventory_from_raw(
    raw: object,
    legacy_seconds: int = 0,
) -> list[SpeedupInventoryItem]:
    entries: list[SpeedupInventoryItem] = []
    if isinstance(raw, list):
        for value in raw:
            if not isinstance(value, dict):
                continue
            kind = str(value.get("kind", "general")).strip() or "general"
            duration = max(0, int(value.get("duration_seconds", 0)))
            quantity = max(0, int(value.get("quantity", 0)))
            if duration > 0 and quantity > 0:
                entries.append(SpeedupInventoryItem(kind, duration, quantity))
    if not entries and legacy_seconds > 0:
        entries.append(SpeedupInventoryItem("general", 1, legacy_seconds))
    return entries


def _speedup_inventory_payload(
    entries: list[SpeedupInventoryItem],
) -> list[dict[str, object]]:
    return [
        {
            "kind": entry.kind,
            "duration_seconds": max(0, int(entry.duration_seconds)),
            "quantity": max(0, int(entry.quantity)),
        }
        for entry in entries
        if entry.duration_seconds > 0 and entry.quantity > 0
    ]


def _legacy_general_speedup_seconds(entries: list[SpeedupInventoryItem]) -> int:
    return sum(
        max(0, int(entry.duration_seconds)) * max(0, int(entry.quantity))
        for entry in entries
        if entry.kind == "general"
    )


def _effective_speedup_inventory(settings: PlayerSettings) -> list[SpeedupInventoryItem]:
    if settings.speedup_inventory:
        return list(settings.speedup_inventory)
    if settings.speedup_seconds > 0:
        return [SpeedupInventoryItem("general", 1, settings.speedup_seconds)]
    return []


def _paid_item_from_raw(raw: object) -> PaidItem | None:
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind", "custom")).strip() or "custom"
    quantity = max(0, int(raw.get("quantity", 0)))
    return PaidItem(
        kind=kind,
        name=str(raw.get("name", "")).strip()[:200],
        quantity=quantity,
        duration_seconds=max(0, int(raw.get("duration_seconds", 0))),
        gem_value_each=max(0.0, float(raw.get("gem_value_each", 0.0))),
        points_each=max(0.0, float(raw.get("points_each", 0.0))),
    )


def _paid_offer_from_raw(raw: object) -> PaidOffer | None:
    if not isinstance(raw, dict):
        return None
    offer_id = str(raw.get("offer_id", "")).strip()
    if not offer_id:
        return None
    return PaidOffer(
        offer_id=offer_id[:100],
        title=(str(raw.get("title", "")).strip() or "Untitled")[:200],
        goal=str(raw.get("goal", "all_round")).strip() or "all_round",
        memo=str(raw.get("memo", ""))[:2000],
        diamond_cost=max(0, int(raw.get("diamond_cost", 0))),
        included_gems=max(0, int(raw.get("included_gems", 0))),
        bonus_gems=max(0, int(raw.get("bonus_gems", 0))),
        items=tuple(
            item
            for item in (
                _paid_item_from_raw(value)
                for value in raw.get("items", [])
            )
            if item is not None
        ),
        created_at=str(raw.get("created_at", "")),
        updated_at=str(raw.get("updated_at", "")),
    )


def _paid_valuation_from_raw(raw: object) -> PaidValuation:
    value = raw if isinstance(raw, dict) else {}
    return PaidValuation(
        points_per_gem=max(0.0, float(value.get("points_per_gem", 1.0))),
        general_speedup_points_per_hour=max(
            0.0, float(value.get("general_speedup_points_per_hour", 0.0))
        ),
        research_speedup_points_per_hour=max(
            0.0, float(value.get("research_speedup_points_per_hour", 0.0))
        ),
        training_speedup_points_per_hour=max(
            0.0, float(value.get("training_speedup_points_per_hour", 0.0))
        ),
        construction_speedup_points_per_hour=max(
            0.0, float(value.get("construction_speedup_points_per_hour", 0.0))
        ),
        healing_speedup_points_per_hour=max(
            0.0, float(value.get("healing_speedup_points_per_hour", 0.0))
        ),
        merging_speedup_points_per_hour=max(
            0.0, float(value.get("merging_speedup_points_per_hour", 0.0))
        ),
        crafting_speedup_points_per_hour=max(
            0.0, float(value.get("crafting_speedup_points_per_hour", 0.0))
        ),
        use_speedup_gem_presets=bool(value.get("use_speedup_gem_presets", True)),
    )


def _paid_item_payload(item: PaidItem) -> dict[str, object]:
    return {
        "kind": item.kind,
        "name": item.name,
        "quantity": item.quantity,
        "duration_seconds": item.duration_seconds,
        "gem_value_each": item.gem_value_each,
        "points_each": item.points_each,
    }


def _paid_offer_payload(offer: PaidOffer) -> dict[str, object]:
    return {
        "offer_id": offer.offer_id,
        "title": offer.title,
        "goal": offer.goal,
        "memo": offer.memo,
        "diamond_cost": offer.diamond_cost,
        "included_gems": offer.included_gems,
        "bonus_gems": offer.bonus_gems,
        "items": [_paid_item_payload(item) for item in offer.items],
        "created_at": offer.created_at,
        "updated_at": offer.updated_at,
    }


def _paid_valuation_payload(value: PaidValuation) -> dict[str, object]:
    return {
        "points_per_gem": value.points_per_gem,
        "general_speedup_points_per_hour": value.general_speedup_points_per_hour,
        "research_speedup_points_per_hour": value.research_speedup_points_per_hour,
        "training_speedup_points_per_hour": value.training_speedup_points_per_hour,
        "construction_speedup_points_per_hour": (
            value.construction_speedup_points_per_hour
        ),
        "healing_speedup_points_per_hour": (
            value.healing_speedup_points_per_hour
        ),
        "merging_speedup_points_per_hour": (
            value.merging_speedup_points_per_hour
        ),
        "crafting_speedup_points_per_hour": (
            value.crafting_speedup_points_per_hour
        ),
        "use_speedup_gem_presets": value.use_speedup_gem_presets,
    }


class PlayerRepository:
    def __init__(self, database: Path | str = ":memory:") -> None:
        self.database = database
        self._connection = sqlite3.connect(database)
        self._connection.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self._connection.close()

    def _migrate(self) -> None:
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_info "
                "(id INTEGER PRIMARY KEY CHECK(id = 1), version INTEGER NOT NULL)"
            )
            self._connection.execute(
                "INSERT OR IGNORE INTO schema_info(id, version) VALUES (1, ?)",
                (SCHEMA_VERSION,),
            )
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS player_settings "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS research_progress "
                "(research_id TEXT PRIMARY KEY, level INTEGER NOT NULL CHECK(level >= 0))"
            )

    def load(self) -> PlayerState:
        settings_rows = self._connection.execute(
            "SELECT key, value FROM player_settings"
        ).fetchall()
        values = {row["key"]: json.loads(row["value"]) for row in settings_rows}
        resources = {
            key: int(values.get(f"resource.{key}", 0)) for key in RESOURCE_KEYS
        }
        vip_level = int(
            values.get(
                "vip_level",
                vip_level_for_free_speedup_seconds(
                    int(values.get("free_speedup_seconds", 0))
                ),
            )
        )
        castle_level = max(1, min(25, int(values.get("castle_level", 1))))
        settings = PlayerSettings(
            vip_level=max(1, min(15, vip_level)),
            castle_level=castle_level,
            castle_target_level=max(0, int(values.get("castle_target_level", 0))),
            castle_mana_stage=max(
                0, min(5, int(values.get("castle_mana_stage", 0)))
            ),
            castle_target_mana_stage=max(
                0, min(5, int(values.get("castle_target_mana_stage", 0)))
            ),
            academy_level=int(values.get("academy_level", 1)),
            construction_speed_percent=float(
                values.get("construction_speed_percent", 0.0)
            ),
            construction_speed_boost_percent=float(
                values.get("construction_speed_boost_percent", 0.0)
            ),
            research_speed_percent=float(values.get("research_speed_percent", 0.0)),
            research_speed_boost_percent=float(
                values.get("research_speed_boost_percent", 0.0)
            ),
            max_guild_helps=max(
                0,
                min(
                    max_guild_helps_for_castle(castle_level),
                    int(values.get("max_guild_helps", 0)),
                ),
            ),
            speedup_seconds=0,
            speedup_inventory=_speedup_inventory_from_raw(
                values.get("speedup_inventory"),
                int(values.get("speedup_seconds", 0)),
            ),
            use_gems_for_speedups=bool(
                values.get("use_gems_for_speedups", False)
            ),
            resource_display_mode=(
                "short"
                if values.get("resource_display_mode") == "short"
                else "exact"
            ),
            resources=resources,
        )
        progress_rows = self._connection.execute(
            "SELECT research_id, level FROM research_progress"
        ).fetchall()
        research_levels = {
            str(row["research_id"]): int(row["level"]) for row in progress_rows
        }
        return PlayerState(
            settings=settings,
            research_levels=research_levels,
            building_levels={
                str(key): max(0, int(value))
                for key, value in values.get("building_levels", {}).items()
            },
            plan_tasks=[
                ResearchPlanTask(
                    research_id=str(item.get("research_id", "")),
                    target_level=max(1, int(item.get("target_level", 1))),
                    created_at=str(item.get("created_at", "")),
                    source_name=str(item.get("source_name", "")),
                )
                for item in values.get("plan_tasks", [])
                if isinstance(item, dict) and item.get("research_id")
            ],
            paid_offers=[
                offer
                for offer in (
                    _paid_offer_from_raw(item)
                    for item in values.get("paid_offers", [])
                )
                if offer is not None
            ],
            paid_valuation=_paid_valuation_from_raw(
                values.get("paid_valuation", {})
            ),
            observed_stats={
                str(key): str(value)
                for key, value in values.get("observed_stats", {}).items()
            },
            updated_at=str(values.get("updated_at", "")),
        )

    def save(self, state: PlayerState) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        state.settings.max_guild_helps = max(
            0,
            min(
                max_guild_helps_for_castle(state.settings.castle_level),
                int(state.settings.max_guild_helps),
            ),
        )
        values: dict[str, object] = {
            "vip_level": state.settings.vip_level,
            "castle_level": state.settings.castle_level,
            "castle_target_level": state.settings.castle_target_level,
            "castle_mana_stage": state.settings.castle_mana_stage,
            "castle_target_mana_stage": state.settings.castle_target_mana_stage,
            "academy_level": state.settings.academy_level,
            "construction_speed_percent": (
                state.settings.construction_speed_percent
            ),
            "construction_speed_boost_percent": (
                state.settings.construction_speed_boost_percent
            ),
            "research_speed_percent": state.settings.research_speed_percent,
            "research_speed_boost_percent": (
                state.settings.research_speed_boost_percent
            ),
            "free_speedup_seconds": free_speedup_seconds_for_vip(
                state.settings.vip_level
            ),
            "max_guild_helps": state.settings.max_guild_helps,
            "speedup_seconds": _legacy_general_speedup_seconds(
                _effective_speedup_inventory(state.settings)
            ),
            "speedup_inventory": _speedup_inventory_payload(
                _effective_speedup_inventory(state.settings)
            ),
            "use_gems_for_speedups": state.settings.use_gems_for_speedups,
            "resource_display_mode": state.settings.resource_display_mode,
            "building_levels": state.building_levels,
            "plan_tasks": [
                {
                    "research_id": task.research_id,
                    "target_level": task.target_level,
                    "created_at": task.created_at,
                    "source_name": task.source_name,
                }
                for task in state.plan_tasks
            ],
            "paid_offers": [
                _paid_offer_payload(offer) for offer in state.paid_offers
            ],
            "paid_valuation": _paid_valuation_payload(state.paid_valuation),
            "observed_stats": state.observed_stats,
            "updated_at": updated_at,
        }
        values.update(
            {f"resource.{key}": state.settings.resources.get(key, 0) for key in RESOURCE_KEYS}
        )
        with self._connection:
            self._connection.execute("DELETE FROM player_settings")
            self._connection.executemany(
                "INSERT INTO player_settings(key, value) VALUES (?, ?)",
                ((key, json.dumps(value, ensure_ascii=False)) for key, value in values.items()),
            )
            self._connection.execute("DELETE FROM research_progress")
            self._connection.executemany(
                "INSERT INTO research_progress(research_id, level) VALUES (?, ?)",
                sorted(state.research_levels.items()),
            )
        state.updated_at = updated_at

    def export_json(self, state: PlayerState, path: Path) -> None:
        path.write_text(
            json.dumps(self.backup_payload(state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def backup_payload(self, state: PlayerState) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "player": {
                "settings": {
                    "vip_level": state.settings.vip_level,
                    "castle_level": state.settings.castle_level,
                    "castle_target_level": state.settings.castle_target_level,
                    "castle_mana_stage": state.settings.castle_mana_stage,
                    "castle_target_mana_stage": (
                        state.settings.castle_target_mana_stage
                    ),
                    "academy_level": state.settings.academy_level,
                    "construction_speed_percent": (
                        state.settings.construction_speed_percent
                    ),
                    "construction_speed_boost_percent": (
                        state.settings.construction_speed_boost_percent
                    ),
                    "research_speed_percent": state.settings.research_speed_percent,
                    "research_speed_boost_percent": (
                        state.settings.research_speed_boost_percent
                    ),
                    "free_speedup_seconds": free_speedup_seconds_for_vip(
                        state.settings.vip_level
                    ),
                    "max_guild_helps": max(
                        0,
                        min(
                            max_guild_helps_for_castle(
                                state.settings.castle_level
                            ),
                            int(state.settings.max_guild_helps),
                        ),
                    ),
                    "speedup_seconds": _legacy_general_speedup_seconds(
                        _effective_speedup_inventory(state.settings)
                    ),
                    "speedup_inventory": _speedup_inventory_payload(
                        _effective_speedup_inventory(state.settings)
                    ),
                    "use_gems_for_speedups": (
                        state.settings.use_gems_for_speedups
                    ),
                    "resource_display_mode": state.settings.resource_display_mode,
                    "resources": state.settings.resources,
                    "observed_stats": state.observed_stats,
                },
                "research_levels": state.research_levels,
                "building_levels": state.building_levels,
                "plan_tasks": [
                    {
                        "research_id": task.research_id,
                        "target_level": task.target_level,
                        "created_at": task.created_at,
                        "source_name": task.source_name,
                    }
                    for task in state.plan_tasks
                ],
                "paid_offers": [
                    _paid_offer_payload(offer) for offer in state.paid_offers
                ],
                "paid_valuation": _paid_valuation_payload(
                    state.paid_valuation
                ),
                "updated_at": state.updated_at,
            },
        }

    def import_json(self, path: Path) -> PlayerState:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return self.restore_payload(raw)

    def restore_payload(self, raw: dict[str, object]) -> PlayerState:
        if int(raw.get("schema_version", 0)) != SCHEMA_VERSION:
            raise ValueError("Unsupported backup schema version")
        player = raw["player"]  # type: ignore[index]
        raw_settings = player["settings"]  # type: ignore[index]
        vip_level = int(
            raw_settings.get(  # type: ignore[union-attr]
                "vip_level",
                vip_level_for_free_speedup_seconds(
                    int(raw_settings.get("free_speedup_seconds", 0))  # type: ignore[union-attr]
                ),
            )
        )
        castle_level = max(
            1,
            min(25, int(raw_settings["castle_level"])),  # type: ignore[index]
        )
        settings = PlayerSettings(
            vip_level=max(1, min(15, vip_level)),
            castle_level=castle_level,
            castle_target_level=max(
                0,
                int(raw_settings.get("castle_target_level", 0)),  # type: ignore[union-attr]
            ),
            castle_mana_stage=max(
                0,
                min(
                    5,
                    int(raw_settings.get("castle_mana_stage", 0)),  # type: ignore[union-attr]
                ),
            ),
            castle_target_mana_stage=max(
                0,
                min(
                    5,
                    int(raw_settings.get("castle_target_mana_stage", 0)),  # type: ignore[union-attr]
                ),
            ),
            academy_level=int(raw_settings["academy_level"]),  # type: ignore[index]
            construction_speed_percent=float(
                raw_settings.get("construction_speed_percent", 0.0)  # type: ignore[union-attr]
            ),
            construction_speed_boost_percent=float(
                raw_settings.get("construction_speed_boost_percent", 0.0)  # type: ignore[union-attr]
            ),
            research_speed_percent=float(raw_settings["research_speed_percent"]),  # type: ignore[index]
            research_speed_boost_percent=float(
                raw_settings.get("research_speed_boost_percent", 0.0)  # type: ignore[union-attr]
            ),
            max_guild_helps=max(
                0,
                min(
                    max_guild_helps_for_castle(castle_level),
                    int(raw_settings["max_guild_helps"]),  # type: ignore[index]
                ),
            ),
            speedup_seconds=0,
            speedup_inventory=_speedup_inventory_from_raw(
                raw_settings.get("speedup_inventory"),  # type: ignore[union-attr]
                int(raw_settings.get("speedup_seconds", 0)),  # type: ignore[union-attr]
            ),
            use_gems_for_speedups=bool(
                raw_settings.get("use_gems_for_speedups", False)  # type: ignore[union-attr]
            ),
            resource_display_mode=(
                "short"
                if raw_settings.get("resource_display_mode") == "short"  # type: ignore[union-attr]
                else "exact"
            ),
            resources={
                key: int(raw_settings.get("resources", {}).get(key, 0))  # type: ignore[union-attr]
                for key in RESOURCE_KEYS
            },
        )
        state = PlayerState(
            settings=settings,
            research_levels={
                str(key): int(value)
                for key, value in player["research_levels"].items()  # type: ignore[index,union-attr]
            },
            building_levels={
                str(key): max(0, int(value))
                for key, value in player.get("building_levels", {}).items()  # type: ignore[union-attr]
            },
            plan_tasks=[
                ResearchPlanTask(
                    research_id=str(item.get("research_id", "")),
                    target_level=max(1, int(item.get("target_level", 1))),
                    created_at=str(item.get("created_at", "")),
                    source_name=str(item.get("source_name", "")),
                )
                for item in player.get("plan_tasks", [])  # type: ignore[union-attr]
                if isinstance(item, dict) and item.get("research_id")
            ],
            paid_offers=[
                offer
                for offer in (
                    _paid_offer_from_raw(item)
                    for item in player.get("paid_offers", [])  # type: ignore[union-attr]
                )
                if offer is not None
            ],
            paid_valuation=_paid_valuation_from_raw(
                player.get("paid_valuation", {})  # type: ignore[union-attr]
            ),
            observed_stats={
                str(key): str(value)
                for key, value in raw_settings.get("observed_stats", {}).items()  # type: ignore[union-attr]
            },
            updated_at=str(player.get("updated_at", "")),  # type: ignore[union-attr]
        )
        self.save(state)
        return state
