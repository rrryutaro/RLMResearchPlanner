from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rlm_research_planner.domain.models import PlayerSettings, PlayerState, RESOURCE_KEYS
from rlm_research_planner.services.calculation import (
    free_speedup_seconds_for_vip,
    vip_level_for_free_speedup_seconds,
)


SCHEMA_VERSION = 1


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
        settings = PlayerSettings(
            vip_level=max(1, min(15, vip_level)),
            castle_level=int(values.get("castle_level", 1)),
            academy_level=int(values.get("academy_level", 1)),
            research_speed_percent=float(values.get("research_speed_percent", 0.0)),
            research_speed_boost_percent=float(
                values.get("research_speed_boost_percent", 0.0)
            ),
            max_guild_helps=int(values.get("max_guild_helps", 0)),
            speedup_seconds=int(values.get("speedup_seconds", 0)),
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
            observed_stats={
                str(key): str(value)
                for key, value in values.get("observed_stats", {}).items()
            },
            updated_at=str(values.get("updated_at", "")),
        )

    def save(self, state: PlayerState) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        values: dict[str, object] = {
            "vip_level": state.settings.vip_level,
            "castle_level": state.settings.castle_level,
            "academy_level": state.settings.academy_level,
            "research_speed_percent": state.settings.research_speed_percent,
            "research_speed_boost_percent": (
                state.settings.research_speed_boost_percent
            ),
            "free_speedup_seconds": free_speedup_seconds_for_vip(
                state.settings.vip_level
            ),
            "max_guild_helps": state.settings.max_guild_helps,
            "speedup_seconds": state.settings.speedup_seconds,
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
                    "academy_level": state.settings.academy_level,
                    "research_speed_percent": state.settings.research_speed_percent,
                    "research_speed_boost_percent": (
                        state.settings.research_speed_boost_percent
                    ),
                    "free_speedup_seconds": free_speedup_seconds_for_vip(
                        state.settings.vip_level
                    ),
                    "max_guild_helps": state.settings.max_guild_helps,
                    "speedup_seconds": state.settings.speedup_seconds,
                    "resources": state.settings.resources,
                    "observed_stats": state.observed_stats,
                },
                "research_levels": state.research_levels,
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
        settings = PlayerSettings(
            vip_level=max(1, min(15, vip_level)),
            castle_level=int(raw_settings["castle_level"]),  # type: ignore[index]
            academy_level=int(raw_settings["academy_level"]),  # type: ignore[index]
            research_speed_percent=float(raw_settings["research_speed_percent"]),  # type: ignore[index]
            research_speed_boost_percent=float(
                raw_settings.get("research_speed_boost_percent", 0.0)  # type: ignore[union-attr]
            ),
            max_guild_helps=int(raw_settings["max_guild_helps"]),  # type: ignore[index]
            speedup_seconds=int(raw_settings["speedup_seconds"]),  # type: ignore[index]
            resources={
                key: int(value)
                for key, value in raw_settings["resources"].items()  # type: ignore[index,union-attr]
            },
        )
        state = PlayerState(
            settings=settings,
            research_levels={
                str(key): int(value)
                for key, value in player["research_levels"].items()  # type: ignore[index,union-attr]
            },
            observed_stats={
                str(key): str(value)
                for key, value in raw_settings.get("observed_stats", {}).items()  # type: ignore[union-attr]
            },
            updated_at=str(player.get("updated_at", "")),  # type: ignore[union-attr]
        )
        self.save(state)
        return state
