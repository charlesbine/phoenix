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

from phoenix.models import AppConfig, BrightnessSchedule, DisplayConfig, DisplaySettings, display_settings_from_json
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
    source TEXT NOT NULL DEFAULT '',
    runtime TEXT NOT NULL DEFAULT ''
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

-- Each physical panel is a device. app definitions stay global (one render per
-- app); per-device rotation membership lives in device_apps. mirror_of points a
-- device at another so its loop just follows it (cheap mirroring).
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    backend TEXT NOT NULL DEFAULT 'web',
    brightness INTEGER NOT NULL DEFAULT 128,
    layout_mode TEXT NOT NULL DEFAULT 'cycle',
    cycle_interval INTEGER NOT NULL DEFAULT 10,
    mirror_of TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    content_mode TEXT NOT NULL DEFAULT 'apps',   -- 'apps' rotation | 'audio' | 'nowplaying'
    audio_mode TEXT NOT NULL DEFAULT 'bars',     -- bars | vu | spectrogram
    address TEXT NOT NULL DEFAULT ''             -- wled IP / serial port (empty = env default)
);

CREATE TABLE IF NOT EXISTS device_apps (
    device_id TEXT NOT NULL,
    app_name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (device_id, app_name)
);

CREATE TABLE IF NOT EXISTS display_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    config TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_brightness_schedules (
    device_id TEXT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
    config TEXT NOT NULL
);
"""

# Track which db paths have had schema applied this process
_initialized: set[str] = set()

_BUILTIN_APPS: tuple[dict, ...] = (
    {
        "name": "nowplaying",
        "runtime": "live_nowplaying",
        "pixlet_config": {},
    },
    {
        "name": "audio_bars",
        "runtime": "live_audio",
        "pixlet_config": {
            "mode": "bars",
            "bar_width": "2",
            "bar_spacing": "solid",
            "floor_db": "-55",
            "noise_gate": "0.08",
            "tilt_db": "0",
            "gain_db": "8",
        },
    },
    {
        "name": "audio_vu",
        "runtime": "live_audio",
        "pixlet_config": {"mode": "vu", "floor_db": "-55", "noise_gate": "0.06"},
    },
    {
        "name": "audio_spectrogram",
        "runtime": "live_audio",
        "pixlet_config": {
            "mode": "spectrogram",
            "bar_width": "2",
            "palette": "hue",
            "contrast": "high",
            "floor_db": "-66",
            "noise_gate": "0.02",
            "tilt_db": "4.5",
            "gain_db": "10",
            "onset_boost": "1.4",
        },
        "previous_pixlet_config": {
            "mode": "spectrogram",
            "bar_width": "2",
            "palette": "hue",
            "contrast": "high",
            "floor_db": "-62",
            "noise_gate": "0.03",
            "tilt_db": "1.5",
            "gain_db": "8",
        },
    },
)


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
            if "runtime" not in cols:
                conn.execute("ALTER TABLE apps ADD COLUMN runtime TEXT NOT NULL DEFAULT ''")
            config_cols = [r[1] for r in conn.execute("PRAGMA table_info(display_config)").fetchall()]
            if "brightness" not in config_cols:
                conn.execute("ALTER TABLE display_config ADD COLUMN brightness INTEGER NOT NULL DEFAULT 255")
            device_cols = [r[1] for r in conn.execute("PRAGMA table_info(devices)").fetchall()]
            if "content_mode" not in device_cols:
                conn.execute("ALTER TABLE devices ADD COLUMN content_mode TEXT NOT NULL DEFAULT 'apps'")
            if "audio_mode" not in device_cols:
                conn.execute("ALTER TABLE devices ADD COLUMN audio_mode TEXT NOT NULL DEFAULT 'bars'")
            if "address" not in device_cols:
                conn.execute("ALTER TABLE devices ADD COLUMN address TEXT NOT NULL DEFAULT ''")
            with conn:
                conn.execute("""
                    INSERT OR IGNORE INTO display_settings (id, config)
                    SELECT 1, json_object('timezone', json_extract(config, '$.timezone'))
                    FROM device_brightness_schedules
                    WHERE json_type(config, '$.timezone') = 'text'
                    ORDER BY json_extract(config, '$.enabled') DESC, device_id LIMIT 1
                """)
                conn.execute("""
                    UPDATE device_brightness_schedules SET config = json_remove(config, '$.timezone')
                    WHERE json_type(config, '$.timezone') = 'text'
                """)
            _seed_builtin_apps(conn)
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
        runtime=row["runtime"] if "runtime" in keys else "",
    )


def _seed_builtin_apps(conn: sqlite3.Connection) -> None:
    """Ensure built-in live apps exist as normal app rows."""
    for app in _BUILTIN_APPS:
        existing = conn.execute(
            "SELECT pixlet_config FROM apps WHERE name = ?", (app["name"],)
        ).fetchone()
        pixlet_config = dict(app["pixlet_config"])
        if existing is not None:
            try:
                current = json.loads(existing["pixlet_config"])
                if isinstance(current, dict):
                    previous = app.get("previous_pixlet_config", {})
                    for key, value in current.items():
                        if key in previous and key in pixlet_config and str(value) == str(previous[key]):
                            continue
                        pixlet_config[key] = value
            except (TypeError, json.JSONDecodeError):
                pass
        conn.execute(
            """
            INSERT INTO apps
                (name, enabled, active, refresh_interval, pixlet_config, priority, sort_order, source, runtime)
            VALUES (?, 0, 1, 30.0, ?, 0, 0, 'builtin', ?)
            ON CONFLICT(name) DO UPDATE SET
                pixlet_config = excluded.pixlet_config,
                source = CASE WHEN apps.source = '' THEN 'builtin' ELSE apps.source END,
                runtime = excluded.runtime
            """,
            (app["name"], json.dumps(pixlet_config), app["runtime"]),
        )
    conn.commit()


class AppDatabase:
    def __init__(self, path: str | Path | None = None):
        self._path = str(path or DB_PATH)
        # Ensure schema on first instantiation
        with _connect(self._path):
            pass

    @property
    def path(self) -> str:
        return self._path

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
            conn.execute("DELETE FROM device_apps WHERE app_name = ?", (name,))
            rows = conn.execute("SELECT id, app_names FROM playlists").fetchall()
            for row in rows:
                app_names = json.loads(row["app_names"])
                updated = [app for app in app_names if app != name]
                if updated != app_names:
                    conn.execute(
                        "UPDATE playlists SET app_names = ? WHERE id = ?",
                        (json.dumps(updated), row["id"]),
                    )
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
                """INSERT INTO apps (name, enabled, active, refresh_interval, last_updated, pixlet_config, priority, sort_order, source, runtime)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._config_to_row(config),
            )
            conn.commit()

    def _replace(self, config: AppConfig) -> None:
        with _connect(self._path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO apps (name, enabled, active, refresh_interval, last_updated, pixlet_config, priority, sort_order, source, runtime)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            config.runtime,
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


class DeviceDatabase:
    """CRUD for panels (devices) and their per-device rotation membership."""

    _DEVICE_FIELDS = (
        "name", "backend", "brightness", "layout_mode", "cycle_interval",
        "mirror_of", "sort_order", "enabled", "content_mode", "audio_mode", "address",
    )
    _MEMBER_FIELDS = ("enabled", "priority", "sort_order")
    _SELECT_DEVICE = """
        SELECT devices.*, device_brightness_schedules.config AS brightness_schedule,
            display_settings.config AS display_settings
        FROM devices LEFT JOIN device_brightness_schedules ON device_brightness_schedules.device_id = devices.id
        LEFT JOIN display_settings ON display_settings.id = 1
    """

    def __init__(self, path: str | Path | None = None):
        self._path = str(path or DB_PATH)
        with _connect(self._path):
            pass

    def list_devices(self) -> list[dict]:
        with _connect(self._path) as conn:
            rows = conn.execute(self._SELECT_DEVICE + "ORDER BY sort_order, name").fetchall()
            return [dict(r) for r in rows]

    def enabled_app_names(self) -> set[str]:
        """App names enabled in the rotation of at least one enabled device.

        The renderer renders the union of these with the globally-enabled apps,
        so a panel's content stays fresh even if the app is off globally.
        """
        with _connect(self._path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT da.app_name FROM device_apps da "
                "JOIN devices d ON d.id = da.device_id "
                "WHERE da.enabled = 1 AND d.enabled = 1"
            ).fetchall()
            return {r["app_name"] for r in rows}

    def get(self, device_id: str) -> dict | None:
        with _connect(self._path) as conn:
            row = conn.execute(self._SELECT_DEVICE + "WHERE devices.id = ?", (device_id,)).fetchone()
            return dict(row) if row else None

    def create(self, device_id: str, name: str, backend: str, **kwargs: object) -> dict:
        cols = {k: kwargs[k] for k in self._DEVICE_FIELDS if k in kwargs}
        cols.update(name=name, backend=backend)
        keys = ["id", *cols.keys()]
        vals = [device_id, *cols.values()]
        placeholders = ", ".join("?" for _ in keys)
        with _connect(self._path) as conn:
            conn.execute(
                f"INSERT OR IGNORE INTO devices ({', '.join(keys)}) VALUES ({placeholders})",
                vals,
            )
            conn.commit()
        return self.get(device_id)  # type: ignore[return-value]

    def update(self, device_id: str, **kwargs: object) -> dict | None:
        fields = {k: v for k, v in kwargs.items() if k in self._DEVICE_FIELDS}
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            with _connect(self._path) as conn:
                conn.execute(f"UPDATE devices SET {sets} WHERE id = ?", (*fields.values(), device_id))
                conn.commit()
        return self.get(device_id)

    def delete(self, device_id: str) -> None:
        with _connect(self._path) as conn:
            conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            conn.execute("DELETE FROM device_apps WHERE device_id = ?", (device_id,))
            conn.execute("DELETE FROM device_brightness_schedules WHERE device_id = ?", (device_id,))
            conn.commit()

    def get_display_settings(self) -> DisplaySettings:
        with _connect(self._path) as conn:
            row = conn.execute("SELECT config FROM display_settings WHERE id = 1").fetchone()
        return display_settings_from_json(row["config"] if row else None)

    @staticmethod
    def _write_display_settings(conn: sqlite3.Connection, settings: DisplaySettings) -> None:
        conn.execute("INSERT OR REPLACE INTO display_settings (id, config) VALUES (1, ?)",
                     (settings.model_dump_json(),))

    def set_display_settings(self, settings: DisplaySettings) -> None:
        with _connect(self._path) as conn, conn:
            self._write_display_settings(conn, settings)

    def set_brightness_schedule(self, device_id: str, schedule: BrightnessSchedule) -> bool:
        with _connect(self._path) as conn, conn:
            result = conn.execute(
                """
                INSERT INTO device_brightness_schedules (device_id, config)
                SELECT id, ? FROM devices WHERE id = ?
                ON CONFLICT(device_id) DO UPDATE SET config = excluded.config
                """,
                (schedule.model_dump_json(), device_id),
            )
            return result.rowcount == 1

    def apply_node_rotation(self, device_id: str, config: dict, schedule: BrightnessSchedule | None,
                            apps: list[AppConfig], settings: DisplaySettings | None = None) -> None:
        """Install a complete cached rotation before the local player sees it."""
        with _connect(self._path) as conn, conn:
            if settings is not None:
                self._write_display_settings(conn, settings)
            conn.execute(
                "UPDATE devices SET layout_mode = ?, cycle_interval = ?, brightness = ?, enabled = ? WHERE id = ?",
                (config["layout_mode"], config["cycle_interval"], config["brightness"], config["enabled"], device_id),
            )
            conn.execute("DELETE FROM device_brightness_schedules WHERE device_id = ?", (device_id,))
            if schedule is not None:
                conn.execute("INSERT INTO device_brightness_schedules VALUES (?, ?)",
                             (device_id, schedule.model_dump_json()))
            conn.execute("DELETE FROM device_apps WHERE device_id = ?", (device_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO apps (name, enabled, active, refresh_interval, last_updated,
                   pixlet_config, priority, sort_order, source, runtime) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [AppDatabase._config_to_row(app) for app in apps],
            )
            conn.executemany("INSERT INTO device_apps (device_id, app_name, enabled, priority, sort_order) VALUES (?, ?, ?, ?, ?)",
                             [(device_id, app.name, app.enabled, app.priority, app.sort_order) for app in apps])

    # -- per-device rotation membership --

    def list_apps(self, device_id: str) -> list[dict]:
        with _connect(self._path) as conn:
            rows = conn.execute(
                "SELECT * FROM device_apps WHERE device_id = ? ORDER BY sort_order, app_name",
                (device_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def set_app(self, device_id: str, app_name: str, **kwargs: object) -> None:
        fields = {k: v for k, v in kwargs.items() if k in self._MEMBER_FIELDS}
        with _connect(self._path) as conn:
            exists = conn.execute(
                "SELECT 1 FROM device_apps WHERE device_id = ? AND app_name = ?",
                (device_id, app_name),
            ).fetchone()
            if exists and fields:
                sets = ", ".join(f"{k} = ?" for k in fields)
                conn.execute(
                    f"UPDATE device_apps SET {sets} WHERE device_id = ? AND app_name = ?",
                    (*fields.values(), device_id, app_name),
                )
            elif not exists:
                conn.execute(
                    "INSERT INTO device_apps (device_id, app_name, enabled, priority, sort_order) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        device_id,
                        app_name,
                        int(bool(fields.get("enabled", True))),
                        int(fields.get("priority", 0)),  # type: ignore[arg-type]
                        int(fields.get("sort_order", 0)),  # type: ignore[arg-type]
                    ),
                )
            conn.commit()

    def remove_app(self, device_id: str, app_name: str) -> None:
        with _connect(self._path) as conn:
            conn.execute(
                "DELETE FROM device_apps WHERE device_id = ? AND app_name = ?", (device_id, app_name)
            )
            conn.commit()

    def reorder(self, device_id: str, app_names: list[str]) -> None:
        with _connect(self._path) as conn:
            for i, name in enumerate(app_names):
                conn.execute(
                    "UPDATE device_apps SET sort_order = ? WHERE device_id = ? AND app_name = ?",
                    (i, device_id, name),
                )
            conn.commit()


def seed_default_device(
    device_id: str = "main",
    name: str = "Main",
    backend: str = "web",
    path: str | Path | None = None,
) -> str | None:
    """If no devices exist yet, migrate the current single-device state into one
    device (config + the whole global rotation). Idempotent and non-destructive —
    it only reads the legacy tables and writes the new ones.

    Returns the seeded device id, or None if devices already existed.
    """
    ddb = DeviceDatabase(path)
    if ddb.list_devices():
        return None
    cfg = ConfigDatabase(path).get()
    ddb.create(
        device_id,
        name,
        backend,
        brightness=cfg.brightness,
        layout_mode=cfg.layout_mode,
        cycle_interval=cfg.cycle_interval,
    )
    for app in AppDatabase(path).list_apps():
        if app.source == "builtin":
            continue
        ddb.set_app(
            device_id,
            app.name,
            enabled=app.enabled,
            priority=app.priority,
            sort_order=app.sort_order,
        )
    logger.info("Seeded default device %r from existing single-device state", device_id)
    return device_id


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
        with _connect(self._path) as conn:
            settings = conn.execute("SELECT config FROM display_settings WHERE id = 1").fetchone()
            rows = conn.execute(
                "SELECT r.*, p.name, p.app_names FROM schedule_rules r "
                "JOIN playlists p ON r.playlist_id = p.id"
            ).fetchall()
        now = display_settings_from_json(settings["config"]).local_time() if settings else datetime.now()
        current_time = now.strftime("%H:%M")
        day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        current_day = day_names[now.weekday()]

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
