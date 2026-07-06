"""SQLite-backed app registry and display configuration.

Uses WAL mode for safe concurrent reads/writes across multiple processes
(renderer, display, dashboard all hit this).

Connections are opened per-operation and closed immediately to avoid holding
locks or stale state across process boundaries.
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from phoenix.models import AppConfig, DisplayConfig
from phoenix.paths import DB_PATH

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
    name TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    refresh_interval REAL NOT NULL DEFAULT 60.0,
    last_updated TEXT,
    pixlet_config TEXT NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    app_names TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS schedule_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    days TEXT NOT NULL DEFAULT '["mon","tue","wed","thu","fri","sat","sun"]',
    FOREIGN KEY (playlist_id) REFERENCES playlists(id)
);

CREATE TABLE IF NOT EXISTS dashboard_panels (
    id TEXT PRIMARY KEY,
    layout TEXT NOT NULL DEFAULT 'big_number',
    title TEXT NOT NULL DEFAULT '',
    config TEXT NOT NULL DEFAULT '{}',
    data_source TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS display_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    layout_mode TEXT NOT NULL DEFAULT 'cycle',
    cycle_interval INTEGER NOT NULL DEFAULT 10,
    brightness INTEGER NOT NULL DEFAULT 255
);
"""

# Track which db paths have had schema applied this process
_initialized: set[str] = set()


@contextmanager
def _connect(path: str) -> Iterator[sqlite3.Connection]:
    """Open a short-lived connection, ensure schema exists, yield, then close."""
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        if path not in _initialized:
            conn.executescript(_SCHEMA)
            # Migrations
            cols = [r[1] for r in conn.execute("PRAGMA table_info(apps)").fetchall()]
            if "sort_order" not in cols:
                conn.execute("ALTER TABLE apps ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
            if "source" not in cols:
                conn.execute("ALTER TABLE apps ADD COLUMN source TEXT NOT NULL DEFAULT ''")
            config_cols = [r[1] for r in conn.execute("PRAGMA table_info(display_config)").fetchall()]
            if "brightness" not in config_cols:
                conn.execute("ALTER TABLE display_config ADD COLUMN brightness INTEGER NOT NULL DEFAULT 255")
            _initialized.add(path)
        yield conn
    finally:
        conn.close()


def _row_to_app(row: sqlite3.Row) -> AppConfig:
    keys = row.keys()
    return AppConfig(
        name=row["name"],
        enabled=bool(row["enabled"]),
        active=bool(row["active"]),
        refresh_interval=timedelta(seconds=row["refresh_interval"]),
        last_updated=datetime.fromisoformat(row["last_updated"]) if row["last_updated"] else None,
        pixlet_config=json.loads(row["pixlet_config"]),
        priority=row["priority"],
        sort_order=row["sort_order"] if "sort_order" in keys else 0,
        source=row["source"] if "source" in keys else "",
    )


class AppDatabase:
    def __init__(self, path: str | Path | None = None):
        self._path = str(path or DB_PATH)
        # Ensure schema on first instantiation
        with _connect(self._path):
            pass

    def list_apps(self) -> list[AppConfig]:
        with _connect(self._path) as conn:
            rows = conn.execute("SELECT * FROM apps ORDER BY name").fetchall()
            return [_row_to_app(r) for r in rows]

    def get(self, name: str) -> AppConfig | None:
        with _connect(self._path) as conn:
            row = conn.execute("SELECT * FROM apps WHERE name = ?", (name,)).fetchone()
            if row is None:
                return None
            return _row_to_app(row)

    def create(self, name: str, **kwargs: object) -> AppConfig:
        if self.get(name) is not None:
            raise ValueError(f"App '{name}' already exists")
        config = AppConfig(name=name, **kwargs)
        self._insert(config)
        return config

    def update(self, name: str, **kwargs: object) -> AppConfig:
        existing = self.get(name)
        if existing is None:
            raise ValueError(f"App '{name}' not found")
        merged = existing.model_dump()
        merged.update(kwargs)
        config = AppConfig(**merged)
        self._replace(config)
        return config

    def upsert(self, name: str, **kwargs: object) -> AppConfig:
        existing = self.get(name)
        if existing:
            merged = existing.model_dump()
            merged.update(kwargs)
            config = AppConfig(**merged)
        else:
            config = AppConfig(name=name, **kwargs)
        self._replace(config)
        return config

    def delete(self, name: str) -> None:
        with _connect(self._path) as conn:
            conn.execute("DELETE FROM apps WHERE name = ?", (name,))
            conn.commit()

    def mark_all_stale(self) -> None:
        """Clear last_updated for every app so the renderer treats them as due."""
        with _connect(self._path) as conn:
            conn.execute("UPDATE apps SET last_updated = NULL")
            conn.commit()

    def _insert(self, config: AppConfig) -> None:
        with _connect(self._path) as conn:
            conn.execute(
                """INSERT INTO apps (name, enabled, active, refresh_interval, last_updated, pixlet_config, priority, sort_order, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._config_to_row(config),
            )
            conn.commit()

    def _replace(self, config: AppConfig) -> None:
        with _connect(self._path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO apps (name, enabled, active, refresh_interval, last_updated, pixlet_config, priority, sort_order, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._config_to_row(config),
            )
            conn.commit()

    @staticmethod
    def _config_to_row(config: AppConfig) -> tuple:
        return (
            config.name,
            int(config.enabled),
            int(config.active),
            config.refresh_interval.total_seconds(),
            config.last_updated.isoformat() if config.last_updated else None,
            json.dumps(config.pixlet_config),
            config.priority,
            config.sort_order,
            config.source,
        )


class ConfigDatabase:
    def __init__(self, path: str | Path | None = None):
        self._path = str(path or DB_PATH)
        with _connect(self._path):
            pass

    def get(self) -> DisplayConfig:
        with _connect(self._path) as conn:
            row = conn.execute("SELECT * FROM display_config WHERE id = 1").fetchone()
            if row is None:
                config = DisplayConfig()
                conn.execute(
                    "INSERT INTO display_config (id, layout_mode, cycle_interval, brightness) VALUES (1, ?, ?, ?)",
                    (config.layout_mode, config.cycle_interval, config.brightness),
                )
                conn.commit()
                return config
            return DisplayConfig(
                layout_mode=row["layout_mode"],
                cycle_interval=row["cycle_interval"],
                brightness=row["brightness"] if "brightness" in row.keys() else 255,
            )

    def update(self, **kwargs: object) -> DisplayConfig:
        current = self.get()
        merged = current.model_dump()
        merged.update(kwargs)
        config = DisplayConfig(**merged)
        with _connect(self._path) as conn:
            conn.execute(
                "UPDATE display_config SET layout_mode = ?, cycle_interval = ?, brightness = ? WHERE id = 1",
                (config.layout_mode, config.cycle_interval, config.brightness),
            )
            conn.commit()
        logger.info("Display config updated: %s", config)
        return config


class PanelDatabase:
    """CRUD for dashboard panels."""

    def __init__(self, path: str | Path | None = None):
        self._path = str(path or DB_PATH)
        with _connect(self._path):
            pass

    def list_panels(self) -> list[dict]:
        with _connect(self._path) as conn:
            rows = conn.execute("SELECT * FROM dashboard_panels ORDER BY created_at").fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get(self, panel_id: str) -> dict | None:
        with _connect(self._path) as conn:
            row = conn.execute("SELECT * FROM dashboard_panels WHERE id = ?", (panel_id,)).fetchone()
            return self._row_to_dict(row) if row else None

    def create(self, panel_id: str, layout: str, title: str, config: dict, data_source: dict) -> dict:
        with _connect(self._path) as conn:
            conn.execute(
                "INSERT INTO dashboard_panels (id, layout, title, config, data_source) VALUES (?, ?, ?, ?, ?)",
                (panel_id, layout, title, json.dumps(config), json.dumps(data_source)),
            )
            conn.commit()
        return self.get(panel_id)  # type: ignore

    def update(self, panel_id: str, **kwargs: object) -> dict:
        panel = self.get(panel_id)
        if panel is None:
            raise ValueError(f"Panel '{panel_id}' not found")
        for key in ("layout", "title", "config", "data_source"):
            if key in kwargs:
                val = kwargs[key]
                if isinstance(val, dict):
                    val = json.dumps(val)
                panel[key] = val
        with _connect(self._path) as conn:
            conn.execute(
                """UPDATE dashboard_panels SET layout = ?, title = ?, config = ?, data_source = ?
                   WHERE id = ?""",
                (panel["layout"], panel["title"],
                 json.dumps(panel["config"]) if isinstance(panel["config"], dict) else panel["config"],
                 json.dumps(panel["data_source"]) if isinstance(panel["data_source"], dict) else panel["data_source"],
                 panel_id),
            )
            conn.commit()
        return self.get(panel_id)  # type: ignore

    def delete(self, panel_id: str) -> None:
        with _connect(self._path) as conn:
            conn.execute("DELETE FROM dashboard_panels WHERE id = ?", (panel_id,))
            conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "layout": row["layout"],
            "title": row["title"],
            "config": json.loads(row["config"]),
            "data_source": json.loads(row["data_source"]),
            "created_at": row["created_at"],
        }


class PlaylistDatabase:
    """CRUD for playlists and schedule rules."""

    def __init__(self, path: str | Path | None = None):
        self._path = str(path or DB_PATH)
        with _connect(self._path):
            pass

    # -- Playlists --

    def list_playlists(self) -> list[dict]:
        with _connect(self._path) as conn:
            rows = conn.execute("SELECT * FROM playlists ORDER BY name").fetchall()
            return [{"id": r["id"], "name": r["name"], "app_names": json.loads(r["app_names"])} for r in rows]

    def get_playlist(self, playlist_id: str) -> dict | None:
        with _connect(self._path) as conn:
            row = conn.execute("SELECT * FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
            if row is None:
                return None
            return {"id": row["id"], "name": row["name"], "app_names": json.loads(row["app_names"])}

    def create_playlist(self, playlist_id: str, name: str, app_names: list[str]) -> dict:
        with _connect(self._path) as conn:
            conn.execute(
                "INSERT INTO playlists (id, name, app_names) VALUES (?, ?, ?)",
                (playlist_id, name, json.dumps(app_names)),
            )
            conn.commit()
        return self.get_playlist(playlist_id)  # type: ignore

    def update_playlist(self, playlist_id: str, **kwargs: object) -> dict:
        playlist = self.get_playlist(playlist_id)
        if playlist is None:
            raise ValueError(f"Playlist '{playlist_id}' not found")
        if "name" in kwargs:
            playlist["name"] = kwargs["name"]
        if "app_names" in kwargs:
            playlist["app_names"] = kwargs["app_names"]
        with _connect(self._path) as conn:
            conn.execute(
                "UPDATE playlists SET name = ?, app_names = ? WHERE id = ?",
                (playlist["name"], json.dumps(playlist["app_names"]), playlist_id),
            )
            conn.commit()
        return self.get_playlist(playlist_id)  # type: ignore

    def delete_playlist(self, playlist_id: str) -> None:
        with _connect(self._path) as conn:
            conn.execute("DELETE FROM schedule_rules WHERE playlist_id = ?", (playlist_id,))
            conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
            conn.commit()

    # -- Schedule rules --

    def list_rules(self) -> list[dict]:
        with _connect(self._path) as conn:
            rows = conn.execute(
                "SELECT r.*, p.name as playlist_name FROM schedule_rules r "
                "JOIN playlists p ON r.playlist_id = p.id ORDER BY r.start_time"
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "playlist_id": r["playlist_id"],
                    "playlist_name": r["playlist_name"],
                    "start_time": r["start_time"],
                    "end_time": r["end_time"],
                    "days": json.loads(r["days"]),
                }
                for r in rows
            ]

    def create_rule(self, playlist_id: str, start_time: str, end_time: str, days: list[str]) -> dict:
        with _connect(self._path) as conn:
            conn.execute(
                "INSERT INTO schedule_rules (playlist_id, start_time, end_time, days) VALUES (?, ?, ?, ?)",
                (playlist_id, start_time, end_time, json.dumps(days)),
            )
            conn.commit()
        return self.list_rules()[-1]

    def delete_rule(self, rule_id: int) -> None:
        with _connect(self._path) as conn:
            conn.execute("DELETE FROM schedule_rules WHERE id = ?", (rule_id,))
            conn.commit()

    def get_active_playlist(self) -> dict | None:
        """Get the playlist that should be active right now based on schedule rules."""
        from datetime import datetime
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        current_day = day_names[now.weekday()]

        with _connect(self._path) as conn:
            rows = conn.execute(
                "SELECT r.*, p.name, p.app_names FROM schedule_rules r "
                "JOIN playlists p ON r.playlist_id = p.id"
            ).fetchall()

        for r in rows:
            days = json.loads(r["days"])
            if current_day not in days:
                continue

            start = r["start_time"]
            end = r["end_time"]

            # Handle overnight ranges (e.g., 22:00 - 07:00)
            if start <= end:
                if start <= current_time < end:
                    return {
                        "id": r["playlist_id"],
                        "name": r["name"],
                        "app_names": json.loads(r["app_names"]),
                    }
            else:
                # Wraps midnight
                if current_time >= start or current_time < end:
                    return {
                        "id": r["playlist_id"],
                        "name": r["name"],
                        "app_names": json.loads(r["app_names"]),
                    }

        return None
