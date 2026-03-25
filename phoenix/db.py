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
    sort_order INTEGER NOT NULL DEFAULT 0
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
            config_cols = [r[1] for r in conn.execute("PRAGMA table_info(display_config)").fetchall()]
            if "brightness" not in config_cols:
                conn.execute("ALTER TABLE display_config ADD COLUMN brightness INTEGER NOT NULL DEFAULT 255")
            _initialized.add(path)
        yield conn
    finally:
        conn.close()


def _row_to_app(row: sqlite3.Row) -> AppConfig:
    return AppConfig(
        name=row["name"],
        enabled=bool(row["enabled"]),
        active=bool(row["active"]),
        refresh_interval=timedelta(seconds=row["refresh_interval"]),
        last_updated=datetime.fromisoformat(row["last_updated"]) if row["last_updated"] else None,
        pixlet_config=json.loads(row["pixlet_config"]),
        priority=row["priority"],
        sort_order=row["sort_order"] if "sort_order" in row.keys() else 0,
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

    def _insert(self, config: AppConfig) -> None:
        with _connect(self._path) as conn:
            conn.execute(
                """INSERT INTO apps (name, enabled, active, refresh_interval, last_updated, pixlet_config, priority, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                self._config_to_row(config),
            )
            conn.commit()

    def _replace(self, config: AppConfig) -> None:
        with _connect(self._path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO apps (name, enabled, active, refresh_interval, last_updated, pixlet_config, priority, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
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
