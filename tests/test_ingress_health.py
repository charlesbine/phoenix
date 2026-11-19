"""Tests for data-ingress health detection, skip-when-unhealthy rotation, and dashboard surfacing."""

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from phoenix.cache import cache_get_meta
from phoenix.db import AppDatabase, ConfigDatabase, DeviceDatabase, PanelDatabase, _initialized
from phoenix.display import manager as manager_mod
from phoenix.display.manager import DisplayManager
from phoenix.models import AppConfig, AppStatus, DataIngressError, PreprocessorResult
from phoenix.preprocessors import dashboard_panel as dp
from phoenix.render import _render_one, render_preview, run_app
from phoenix.settings import Settings


class FakeBackend:
    def __init__(self) -> None:
        self.shown: list[tuple[Path, int]] = []
        self.cleared = 0

    def display_image(self, image_path: Path, duration: int) -> None:
        self.shown.append((image_path, duration))

    def clear(self) -> None:
        self.cleared += 1


def _isolate_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenix.cache as cache_mod

    monkeypatch.setattr(cache_mod, "CACHE_DB", tmp_path / "cache.db")
    monkeypatch.setattr(cache_mod, "_initialized", False)


def _isolate_mqtt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenix.mqtt as mqtt_mod

    monkeypatch.setattr(mqtt_mod, "MQTT_DB", tmp_path / "mqtt.db")
    monkeypatch.setattr(mqtt_mod, "_schema_initialized", False)


class TestModelAndMigration:
    def test_app_config_health_defaults_and_skip_property(self):
        app = AppConfig(name="panel_amoura_mrr")
        assert app.skip_when_unhealthy is False
        assert app.health_status == "unknown"
        assert app.health_reason == ""
        assert app.last_healthy is None
        assert app.health_checked_at is None
        assert app.is_skipped_unhealthy is False

        unhealthy_no_skip = app.model_copy(update={"health_status": "unhealthy"})
        assert unhealthy_no_skip.is_skipped_unhealthy is False

        healthy_with_skip = app.model_copy(update={"skip_when_unhealthy": True, "health_status": "healthy"})
        assert healthy_with_skip.is_skipped_unhealthy is False

        unknown_with_skip = app.model_copy(update={"skip_when_unhealthy": True, "health_status": "unknown"})
        assert unknown_with_skip.is_skipped_unhealthy is False

        skipped = app.model_copy(update={"skip_when_unhealthy": True, "health_status": "unhealthy"})
        assert skipped.is_skipped_unhealthy is True

    def test_legacy_apps_table_migrates_health_and_skip_columns(self, tmp_path):
        db_path = tmp_path / "legacy.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE apps (
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
                )
                """
            )
            conn.execute("INSERT INTO apps (name, enabled) VALUES ('panel_amoura_mrr', 1)")
            conn.commit()
        _initialized.discard(str(db_path))

        adb = AppDatabase(db_path)
        app = adb.get("panel_amoura_mrr")
        assert app is not None
        assert app.skip_when_unhealthy is False
        assert app.health_status == "unknown"

        now = datetime.now()
        adb.upsert(
            "panel_amoura_mrr",
            skip_when_unhealthy=True,
            health_status="unhealthy",
            health_reason="HTTP 502 from api.amoura.app/metrics",
            last_healthy=now - timedelta(minutes=20),
            health_checked_at=now,
        )
        updated = adb.get("panel_amoura_mrr")
        assert updated is not None
        assert updated.skip_when_unhealthy is True
        assert updated.health_status == "unhealthy"
        assert updated.health_reason == "HTTP 502 from api.amoura.app/metrics"
        assert updated.last_healthy is not None
        assert updated.is_skipped_unhealthy is True


class TestCacheMeta:
    def test_non_2xx_response_is_not_cached_and_recovery_fetches_fresh(self, tmp_path, monkeypatch):
        import phoenix.cache as cache_mod

        _isolate_cache(tmp_path, monkeypatch)
        responses = iter([
            httpx.Response(502, content=b"Bad Gateway", headers={"content-type": "text/plain"}),
            httpx.Response(200, content=b'{"mrr": 641}', headers={"content-type": "application/json"}),
        ])

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, headers=None):
                return next(responses)

        monkeypatch.setattr(cache_mod.httpx, "Client", FakeClient)

        first = cache_get_meta("https://api.example.com/metrics", ttl=300)
        assert first.status_code == 502
        assert first.stale is False

        # Second call must NOT serve cached 502; it fetches the recovered 200.
        second = cache_get_meta("https://api.example.com/metrics", ttl=300)
        assert second.status_code == 200
        assert second.from_cache is False

    def test_stale_fallback_reports_stale_and_error(self, tmp_path, monkeypatch):
        import phoenix.cache as cache_mod

        _isolate_cache(tmp_path, monkeypatch)
        now = 1_700_000_000.0
        monkeypatch.setattr(cache_mod.time, "time", lambda: now)

        fail_fetch = False

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, headers=None):
                if fail_fetch:
                    raise httpx.ConnectError("connection refused")
                return httpx.Response(200, content=b'{"mrr": 641}', headers={"content-type": "application/json"})

        monkeypatch.setattr(cache_mod.httpx, "Client", FakeClient)

        fresh = cache_get_meta("https://api.example.com/metrics", ttl=60)
        assert fresh.status_code == 200
        assert fresh.stale is False

        now += 120.0
        fail_fetch = True
        stale = cache_get_meta("https://api.example.com/metrics", ttl=60)
        assert stale.status_code == 200
        assert stale.from_cache is True
        assert stale.stale is True
        assert stale.error == "ConnectError"
        assert stale.age_seconds == pytest.approx(120.0)


class TestPanelIngressHealth:
    def _make_panel(self, db_path: Path, panel_id: str, layout: str, data_source: dict, config: dict | None = None):
        pdb = PanelDatabase(db_path)
        pdb.create(panel_id, layout, panel_id.title(), config or {}, data_source)

    def test_static_panel_is_always_healthy(self, tmp_path, monkeypatch):
        db_path = tmp_path / "p.db"
        monkeypatch.setattr(dp, "data_path", lambda name: tmp_path / f"{name}.json")
        self._make_panel(db_path, "note", "big_number", {"type": "static"}, {"value": "42"})

        res = dp.run_panel("note", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is True
        assert res.health_reason == ""

    def test_http_errors_and_sanitized_url(self, tmp_path, monkeypatch):
        import phoenix.cache as cache_mod

        _isolate_cache(tmp_path, monkeypatch)
        db_path = tmp_path / "p.db"
        monkeypatch.setattr(dp, "data_path", lambda name: tmp_path / f"{name}.json")

        self._make_panel(
            db_path,
            "amoura_mrr",
            "big_number",
            {
                "type": "http",
                "url": "https://api.amoura.app/v1/metrics?api_key=super_secret_token",
                "ttl": 60,
                "mappings": {"value": "mrr_cents"},
            },
        )

        # 502 error
        monkeypatch.setattr(
            cache_mod,
            "cache_get_meta",
            lambda url, ttl=300, headers=None, **kw: cache_mod.CacheResponse(
                status_code=502, body=b"Bad Gateway", content_type="text/plain", fetched_at=time.time()
            ),
        )
        monkeypatch.setattr(dp, "cache_get_meta", cache_mod.cache_get_meta)
        res = dp.run_panel("amoura_mrr", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is False
        assert "HTTP 502" in res.health_reason
        assert "api.amoura.app/v1/metrics" in res.health_reason
        assert "super_secret_token" not in res.health_reason

        # Network error
        def boom(*args, **kwargs):
            raise httpx.ConnectError("failed connecting to https://api.amoura.app/v1/metrics?api_key=super_secret_token")

        monkeypatch.setattr(dp, "cache_get_meta", boom)
        res = dp.run_panel("amoura_mrr", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is False
        assert "ConnectError" in res.health_reason
        assert "super_secret_token" not in res.health_reason

    def test_empty_and_missing_mapped_payloads_across_layouts(self, tmp_path, monkeypatch):
        import phoenix.cache as cache_mod

        db_path = tmp_path / "p.db"
        monkeypatch.setattr(dp, "data_path", lambda name: tmp_path / f"{name}.json")

        # 1. key_value with all mapped fields missing (mirrors Amoura LLM Costs / Sessions outage)
        self._make_panel(
            db_path,
            "amoura_costs",
            "key_value",
            {
                "type": "http",
                "url": "https://api.amoura.app/costs",
                "mappings": {
                    "items": [
                        {"key": "Spend:", "value_path": "spend_usd"},
                        {"key": "Errors:", "value_path": "error_count"},
                    ]
                },
            },
        )
        monkeypatch.setattr(
            dp,
            "cache_get_meta",
            lambda *a, **kw: cache_mod.CacheResponse(
                status_code=200, body=b'{"other": 1}', content_type="application/json", fetched_at=time.time()
            ),
        )
        res = dp.run_panel("amoura_costs", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is False
        assert "missing" in res.health_reason.lower()

        # 2. sparkline with empty points array
        self._make_panel(
            db_path,
            "amoura_mrr_chart",
            "sparkline",
            {
                "type": "http",
                "url": "https://api.amoura.app/mrr-chart",
                "mappings": {"points": "daily_mrr", "point_value": "mrr_cents"},
            },
        )
        monkeypatch.setattr(
            dp,
            "cache_get_meta",
            lambda *a, **kw: cache_mod.CacheResponse(
                status_code=200, body=b'{"daily_mrr": []}', content_type="application/json", fetched_at=time.time()
            ),
        )
        res = dp.run_panel("amoura_mrr_chart", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is False
        assert "data points" in res.health_reason.lower()

        # 3. multi_stat with all stats missing
        self._make_panel(
            db_path,
            "amoura_growth",
            "multi_stat",
            {
                "type": "http",
                "url": "https://api.amoura.app/growth",
                "mappings": {
                    "stats": [
                        {"label": "Users", "value_path": "users.total"},
                        {"label": "Today", "value_path": "users.today"},
                    ]
                },
            },
        )
        monkeypatch.setattr(
            dp,
            "cache_get_meta",
            lambda *a, **kw: cache_mod.CacheResponse(
                status_code=200, body=b'{"status": "ok"}', content_type="application/json", fetched_at=time.time()
            ),
        )
        res = dp.run_panel("amoura_growth", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is False
        assert "missing" in res.health_reason.lower()

        # 4. marquee with blank string
        self._make_panel(
            db_path,
            "ticker",
            "marquee",
            {"type": "http", "url": "https://api.example.com/news", "mappings": {"text": "headline"}},
        )
        monkeypatch.setattr(
            dp,
            "cache_get_meta",
            lambda *a, **kw: cache_mod.CacheResponse(
                status_code=200, body=b'{"headline": "   "}', content_type="application/json", fetched_at=time.time()
            ),
        )
        res = dp.run_panel("ticker", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is False
        assert "headline" in res.health_reason

        # 5. Valid Amoura payload -> healthy
        monkeypatch.setattr(
            dp,
            "cache_get_meta",
            lambda *a, **kw: cache_mod.CacheResponse(
                status_code=200,
                body=b'{"spend_usd": 12.5, "error_count": 0}',
                content_type="application/json",
                fetched_at=time.time(),
            ),
        )
        res = dp.run_panel("amoura_costs", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is True
        assert res.health_reason == ""

    def test_stale_detection_via_payload_timestamp_and_cache_fallback(self, tmp_path, monkeypatch):
        import phoenix.cache as cache_mod

        db_path = tmp_path / "p.db"
        monkeypatch.setattr(dp, "data_path", lambda name: tmp_path / f"{name}.json")
        now = 1_750_000_000.0
        monkeypatch.setattr(dp.time, "time", lambda: now)

        self._make_panel(
            db_path,
            "amoura_mrr",
            "big_number",
            {
                "type": "http",
                "url": "https://api.amoura.app/mrr",
                "stale_after": 600,
                "timestamp_path": "updated_at",
                "mappings": {"value": "mrr"},
            },
        )

        # Fresh ISO-8601 timestamp -> healthy
        fresh_iso = datetime.fromtimestamp(now - 120, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        monkeypatch.setattr(
            dp,
            "cache_get_meta",
            lambda *a, **kw: cache_mod.CacheResponse(
                status_code=200,
                body=json.dumps({"mrr": 641, "updated_at": fresh_iso}).encode(),
                content_type="application/json",
                fetched_at=now,
            ),
        )
        res = dp.run_panel("amoura_mrr", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is True

        # Stale ISO-8601 timestamp (30m old, limit 10m) -> unhealthy
        stale_iso = datetime.fromtimestamp(now - 1800, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        monkeypatch.setattr(
            dp,
            "cache_get_meta",
            lambda *a, **kw: cache_mod.CacheResponse(
                status_code=200,
                body=json.dumps({"mrr": 641, "updated_at": stale_iso}).encode(),
                content_type="application/json",
                fetched_at=now,
            ),
        )
        res = dp.run_panel("amoura_mrr", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is False
        assert "stale" in res.health_reason.lower()

        # Stale cache fallback with no explicit stale_after -> immediately unhealthy
        self._make_panel(
            db_path,
            "amoura_subs",
            "big_number",
            {"type": "http", "url": "https://api.amoura.app/subs", "mappings": {"value": "subs"}},
        )
        monkeypatch.setattr(
            dp,
            "cache_get_meta",
            lambda *a, **kw: cache_mod.CacheResponse(
                status_code=200,
                body=b'{"subs": 42}',
                content_type="application/json",
                fetched_at=now - 400,
                from_cache=True,
                stale=True,
                error="ConnectError",
            ),
        )
        res = dp.run_panel("amoura_subs", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is False
        assert "unreachable" in res.health_reason.lower()

    def test_mqtt_and_ha_sources_health_checks(self, tmp_path, monkeypatch):
        import phoenix.cache as cache_mod
        import phoenix.mqtt as mqtt_mod

        _isolate_mqtt(tmp_path, monkeypatch)
        db_path = tmp_path / "p.db"
        monkeypatch.setattr(dp, "data_path", lambda name: tmp_path / f"{name}.json")

        # MQTT missing message -> unhealthy
        self._make_panel(
            db_path,
            "sensor_mqtt",
            "big_number",
            {"type": "mqtt", "topic": "home/temp", "stale_after": 300, "mappings": {"value": "temp"}},
        )
        res = dp.run_panel("sensor_mqtt", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is False
        assert "No MQTT message" in res.health_reason

        # MQTT fresh message -> healthy
        now = 1_750_000_000.0
        monkeypatch.setattr(mqtt_mod.time, "time", lambda: now)
        monkeypatch.setattr(dp.time, "time", lambda: now)
        mqtt_mod.store_message("home/temp", json.dumps({"temp": 72}))
        res = dp.run_panel("sensor_mqtt", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is True

        # MQTT message ages past stale_after -> unhealthy
        monkeypatch.setattr(dp.time, "time", lambda: now + 900)
        res = dp.run_panel("sensor_mqtt", Settings(_env_file=None), db_path=db_path)
        assert res.healthy is False
        assert "stale" in res.health_reason.lower()

        # Home Assistant entity unavailable -> unhealthy
        self._make_panel(
            db_path,
            "ha_temp",
            "big_number",
            {"type": "ha", "entity_id": "sensor.office_temp", "mappings": {"value": "state"}},
        )
        settings = Settings(_env_file=None, ha_url="http://ha.local:8123", ha_token="tok")
        monkeypatch.setattr(
            dp,
            "cache_get_meta",
            lambda *a, **kw: cache_mod.CacheResponse(
                status_code=200,
                body=json.dumps({"entity_id": "sensor.office_temp", "state": "unavailable"}).encode(),
                content_type="application/json",
                fetched_at=now,
            ),
        )
        res = dp.run_panel("ha_temp", settings, db_path=db_path)
        assert res.healthy is False
        assert "unavailable" in res.health_reason.lower()

        # Home Assistant entity healthy
        monkeypatch.setattr(
            dp,
            "cache_get_meta",
            lambda *a, **kw: cache_mod.CacheResponse(
                status_code=200,
                body=json.dumps({"entity_id": "sensor.office_temp", "state": "21.5"}).encode(),
                content_type="application/json",
                fetched_at=now,
            ),
        )
        res = dp.run_panel("ha_temp", settings, db_path=db_path)
        assert res.healthy is True


class TestRenderAndRecovery:
    def test_panel_render_tracks_health_preserves_last_healthy_and_recovers(self, tmp_path, monkeypatch):
        from phoenix import render as render_mod

        db_path = tmp_path / "r.db"
        adb = AppDatabase(db_path)
        adb.upsert("panel_amoura_mrr", enabled=True, skip_when_unhealthy=True)

        results = iter([
            PreprocessorResult(data={"layout": "big_number", "value": "$641"}, healthy=True),
            PreprocessorResult(data={"layout": "big_number", "value": "—"}, healthy=False, health_reason="HTTP 502 from api.amoura.app"),
            PreprocessorResult(data={"layout": "big_number", "value": "$650"}, healthy=True),
        ])
        monkeypatch.setattr(dp, "run_panel", lambda pid, settings, db_path=None: next(results))
        monkeypatch.setattr(render_mod, "_render_dispatch", lambda app, settings: None)

        # 1. Healthy render sets last_healthy
        run_app("panel_amoura_mrr", Settings(_env_file=None), adb)
        healthy = adb.get("panel_amoura_mrr")
        assert healthy is not None
        assert healthy.health_status == "healthy"
        assert healthy.health_reason == ""
        assert healthy.last_healthy is not None
        first_healthy_ts = healthy.last_healthy

        # 2. Outage marks unhealthy WITHOUT disabling and preserves last_healthy
        run_app("panel_amoura_mrr", Settings(_env_file=None), adb)
        down = adb.get("panel_amoura_mrr")
        assert down is not None
        assert down.enabled is True
        assert down.health_status == "unhealthy"
        assert down.health_reason == "HTTP 502 from api.amoura.app"
        assert down.last_healthy == first_healthy_ts
        assert down.is_skipped_unhealthy is True

        # 3. Recovery clears reason and updates last_healthy
        run_app("panel_amoura_mrr", Settings(_env_file=None), adb)
        recovered = adb.get("panel_amoura_mrr")
        assert recovered is not None
        assert recovered.health_status == "healthy"
        assert recovered.health_reason == ""
        assert recovered.last_healthy is not None
        assert recovered.last_healthy >= first_healthy_ts
        assert recovered.is_skipped_unhealthy is False

    def test_python_app_data_ingress_error_marks_unhealthy_without_disabling(self, tmp_path, monkeypatch):
        from phoenix import render as render_mod
        from phoenix.apps import home_climate

        db_path = tmp_path / "r.db"
        adb = AppDatabase(db_path)
        adb.upsert("home_climate", enabled=True, skip_when_unhealthy=True)

        # All sensors fail -> home_climate raises DataIngressError
        monkeypatch.setattr(home_climate, "_fetch_entity", lambda entity, settings: {})
        with pytest.raises(DataIngressError, match="climate sensors unavailable"):
            home_climate.render(
                Settings(_env_file=None, ha_url="http://ha.local:8123", ha_token="tok"),
                {},
                tmp_path / "out.webp",
                tmp_path / "out.large.webp",
            )

        # Through _render_one (the renderer loop entrypoint), it catches and records unhealthy
        monkeypatch.setattr(
            render_mod,
            "_render_dispatch",
            lambda app, settings: (_ for _ in ()).throw(DataIngressError("All Home Assistant climate sensors unavailable")),
        )
        _render_one("home_climate", Settings(_env_file=None), adb)
        state = adb.get("home_climate")
        assert state is not None
        assert state.enabled is True
        assert state.health_status == "unhealthy"
        assert "climate sensors unavailable" in state.health_reason
        assert state.is_skipped_unhealthy is True

    def test_conditional_skip_stays_healthy(self, tmp_path, monkeypatch):
        from phoenix import render as render_mod

        db_path = tmp_path / "r.db"
        adb = AppDatabase(db_path)
        adb.upsert("spotify_now_playing", enabled=True, skip_when_unhealthy=True)

        monkeypatch.setattr(render_mod, "app_type", lambda name: "star")
        monkeypatch.setattr(
            render_mod,
            "get_preprocessor",
            lambda name: lambda settings: PreprocessorResult(data=None, status=AppStatus.SKIP),
        )
        monkeypatch.setattr(render_mod, "output_path", lambda name: tmp_path / f"{name}.webp")
        monkeypatch.setattr(render_mod, "output_path_large", lambda name: tmp_path / f"{name}.large.webp")

        run_app("spotify_now_playing", Settings(_env_file=None), adb)
        state = adb.get("spotify_now_playing")
        assert state is not None
        assert state.health_status == "healthy"
        assert state.is_skipped_unhealthy is False

    def test_render_preview_updates_registered_panel_health(self, tmp_path, monkeypatch):
        import phoenix.db as db_mod
        from phoenix import render as render_mod

        db_path = tmp_path / "preview.db"
        monkeypatch.setattr(db_mod, "DB_PATH", db_path)
        adb = AppDatabase(db_path)
        adb.upsert("panel_amoura_costs", enabled=True, skip_when_unhealthy=True)
        monkeypatch.setattr(
            dp,
            "run_panel",
            lambda pid, settings, db_path=None: PreprocessorResult(
                data={"layout": "key_value", "items": []},
                healthy=False,
                health_reason="All mapped fields missing from payload",
            ),
        )
        monkeypatch.setattr(render_mod, "_render_dispatch", lambda app, settings: None)

        render_preview("panel_amoura_costs", Settings(_env_file=None))
        state = adb.get("panel_amoura_costs")
        assert state is not None
        assert state.health_status == "unhealthy"
        assert state.health_reason == "All mapped fields missing from payload"


class TestDisplaySkipWhenUnhealthy:
    def test_display_manager_skips_unhealthy_only_when_opt_in_enabled(self, tmp_path, monkeypatch):
        db = str(tmp_path / "disp.db")
        adb = AppDatabase(db)
        ddb = DeviceDatabase(db)
        ddb.create("apollo", "Apollo", "wled")

        adb.upsert("clock", enabled=True, health_status="healthy", skip_when_unhealthy=True)
        adb.upsert(
            "panel_amoura_costs",
            enabled=True,
            health_status="unhealthy",
            health_reason="All mapped fields missing from payload",
            skip_when_unhealthy=True,
        )
        adb.upsert(
            "panel_amoura_mrr",
            enabled=True,
            health_status="unhealthy",
            health_reason="HTTP 502",
            skip_when_unhealthy=False,
        )

        for idx, name in enumerate(("clock", "panel_amoura_costs", "panel_amoura_mrr")):
            ddb.set_app("apollo", name, enabled=True, sort_order=idx)

        # Device mode
        dm = DisplayManager(FakeBackend(), app_db=adb, device_id="apollo", device_db=ddb)
        assert [a.name for a in dm._collect_active()] == ["clock", "panel_amoura_mrr"]

        # Global mode
        global_dm = DisplayManager(FakeBackend(), app_db=adb, config_db=ConfigDatabase(db), device_db=ddb)
        assert {a.name for a in global_dm._collect_active()} == {"clock", "panel_amoura_mrr"}

        # Mid-cycle guard in _display_app skips unhealthy opt-in app
        outputs = tmp_path / "outputs"
        outputs.mkdir()
        (outputs / "panel_amoura_costs.webp").write_bytes(b"webp")
        monkeypatch.setattr(manager_mod, "output_path", lambda name: outputs / f"{name}.webp")

        backend = FakeBackend()
        dm = DisplayManager(backend, app_db=adb, device_id="apollo", device_db=ddb)
        dm._display_app(adb.get("panel_amoura_costs"), 10)  # type: ignore[arg-type]
        assert backend.shown == []

        # Explicit show_now can still preview an unhealthy app on demand
        show_file = tmp_path / "show_now__apollo.txt"
        show_file.write_text("panel_amoura_costs")
        monkeypatch.setattr(manager_mod, "show_now_file", lambda dev=None: show_file)
        shown = dm._check_show_now()
        assert shown is not None
        dm._display_app(shown, 10)
        assert len(backend.shown) == 1

        # Recovery immediately restores app to rotation
        adb.upsert("panel_amoura_costs", health_status="healthy", health_reason="")
        assert [a.name for a in dm._collect_active()] == ["clock", "panel_amoura_costs", "panel_amoura_mrr"]

    def test_paired_node_state_propagates_skip_without_timestamp_churn(self, tmp_path, monkeypatch):
        import phoenix.db as db_mod
        import phoenix.node as node_mod
        import phoenix.paths as paths_mod

        monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "central.db")
        monkeypatch.setattr(paths_mod, "DATA_DIR", tmp_path / "data")
        central_outputs = tmp_path / "central"
        central_outputs.mkdir()
        monkeypatch.setattr(node_mod, "output_path", lambda name: central_outputs / f"{name}.webp")
        monkeypatch.setattr(node_mod, "show_now_file", lambda _dev: central_outputs / "show_now.txt")

        ddb = DeviceDatabase()
        ddb.create("desk", "Desk", "serial")
        adb = AppDatabase()
        now = datetime.now()
        adb.upsert(
            "panel_amoura_mrr",
            skip_when_unhealthy=True,
            health_status="healthy",
            last_healthy=now,
            health_checked_at=now,
        )
        ddb.set_app("desk", "panel_amoura_mrr", enabled=True)
        Image.new("RGB", (64, 64), "green").save(central_outputs / "panel_amoura_mrr.webp")

        rev_healthy_1 = node_mod.build_state("desk").revision()
        # Updating volatile check timestamps should NOT churn node revision
        adb.upsert(
            "panel_amoura_mrr",
            last_healthy=now + timedelta(minutes=1),
            health_checked_at=now + timedelta(minutes=1),
        )
        assert node_mod.build_state("desk").revision() == rev_healthy_1

        # Flipping to unhealthy changes state revision and carries skip_when_unhealthy + health_status
        adb.upsert("panel_amoura_mrr", health_status="unhealthy", health_reason="HTTP 502")
        state = node_mod.build_state("desk")
        assert state.revision() != rev_healthy_1
        assert state.apps[0].skip_when_unhealthy is True
        assert state.apps[0].health_status == "unhealthy"
        assert state.apps[0].is_skipped_unhealthy is True


class TestDashboardApiAndWebSocket:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        import phoenix.db as db_mod
        import phoenix.paths as paths_mod
        from phoenix.server import dashboard

        monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "dash.db")
        data_dir = tmp_path / "data"
        (data_dir / "output").mkdir(parents=True)
        monkeypatch.setattr(paths_mod, "DATA_DIR", data_dir)
        monkeypatch.setattr(dashboard, "get_settings", lambda: Settings(_env_file=None, platform="web"))
        return TestClient(dashboard.create_app())

    def test_skip_when_unhealthy_endpoint_global_and_device_scoped(self, client):
        client.post("/api/devices", json={"id": "apollo", "name": "Apollo", "backend": "wled"})
        client.post("/api/apps/clock/add")
        client.post("/api/apps/clock/add", params={"device": "apollo"})
        client.put("/api/apps/clock/priority", params={"device": "apollo"}, json={"priority": 2})

        # Invalid payload -> 422
        assert client.put("/api/apps/clock/skip-when-unhealthy", json={"skip_when_unhealthy": "yes"}).status_code == 422

        # Device-scoped toggle updates global skip flag while returning device-scoped priority/enabled
        res = client.put(
            "/api/apps/clock/skip-when-unhealthy",
            params={"device": "apollo"},
            json={"skip_when_unhealthy": True},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["skip_when_unhealthy"] is True
        assert body["priority"] == 2

        assert client.get("/api/apps/clock").json()["skip_when_unhealthy"] is True

    def test_panels_api_and_status_surface_unhealthy_ingress(self, client, monkeypatch):
        from phoenix.db import AppDatabase
        from phoenix.service import PhoenixService

        monkeypatch.setattr(PhoenixService, "render_preview", lambda self, name: None)

        created = client.post(
            "/api/panels",
            json={
                "id": "amoura_mrr",
                "title": "Amoura MRR",
                "layout": "big_number",
                "config": {},
                "data_source": {
                    "type": "http",
                    "url": "https://api.amoura.app/mrr",
                    "stale_after": 900,
                    "timestamp_path": "updated_at",
                    "mappings": {"value": "mrr"},
                },
                "skip_when_unhealthy": True,
            },
        ).json()
        assert created["id"] == "amoura_mrr"
        assert created["skip_when_unhealthy"] is True
        assert created["data_source"]["stale_after"] == 900

        # Simulate unhealthy state on backing app
        adb = AppDatabase()
        last_ok = datetime.now() - timedelta(minutes=15)
        adb.upsert(
            "panel_amoura_mrr",
            health_status="unhealthy",
            health_reason="HTTP 502 from api.amoura.app/mrr",
            last_healthy=last_ok,
        )

        panels = client.get("/api/panels").json()
        panel = next(p for p in panels if p["id"] == "amoura_mrr")
        assert panel["health_status"] == "unhealthy"
        assert panel["health_reason"] == "HTTP 502 from api.amoura.app/mrr"
        assert panel["skipped_unhealthy"] is True
        assert panel["last_healthy"] is not None

        status = client.get("/api/status").json()
        assert status["status"] == "degraded"
        assert len(status["unhealthy_apps"]) == 1
        assert status["unhealthy_apps"][0]["name"] == "panel_amoura_mrr"
        assert status["unhealthy_apps"][0]["skipped_unhealthy"] is True
        assert any("panel_amoura_mrr" in issue for issue in status["issues"])

        # Disabled app should not degrade system status
        adb.upsert("panel_amoura_mrr", enabled=False)
        status_disabled = client.get("/api/status").json()
        assert status_disabled["unhealthy_apps"] == []

        # PUT /api/panels/{id} can toggle skip_when_unhealthy off
        updated = client.put(
            "/api/panels/amoura_mrr",
            json={"skip_when_unhealthy": False},
        ).json()
        assert updated["skip_when_unhealthy"] is False
        assert updated["skipped_unhealthy"] is False

    def test_ws_state_pushes_on_health_transition(self, client):
        from phoenix.db import AppDatabase

        client.post("/api/apps/clock/add")
        client.post("/api/apps/clock/add", params={"device": "main"})

        with client.websocket_connect("/ws/state?device=main") as ws:
            initial = ws.receive_json()
            clock = next(a for a in initial["apps"] if a["name"] == "clock")
            assert clock["health_status"] == "unknown"

            AppDatabase().upsert(
                "clock",
                skip_when_unhealthy=True,
                health_status="unhealthy",
                health_reason="Data stale",
            )
            pushed = ws.receive_json()
            clock2 = next(a for a in pushed["apps"] if a["name"] == "clock")
            assert clock2["health_status"] == "unhealthy"
            assert clock2["health_reason"] == "Data stale"
            assert clock2["skipped_unhealthy"] is True
