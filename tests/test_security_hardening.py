"""Security hardening tests covering proxy XSS/size-caps, panel auth masking,
path traversal, pixlet arg/env isolation, panel SSRF, CSRF/Origin middleware,
format-string safety, and Home Assistant entity_id validation.
"""

import socket
import subprocess
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from phoenix import cache as cache_mod
from phoenix import paths as paths_mod
from phoenix import render as render_mod
from phoenix import shop as shop_mod
from phoenix.apps import home_climate
from phoenix.db import PanelDatabase
from phoenix.models import AppConfig
from phoenix.net import is_valid_ha_entity_id, validate_panel_url
from phoenix.preprocessors import dashboard_panel as dp
from phoenix.server import dashboard
from phoenix.settings import Settings


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
    import phoenix.db as db_mod

    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "dash.db")
    monkeypatch.setattr(cache_mod, "CACHE_DB", tmp_path / "cache.db")
    monkeypatch.setattr(cache_mod, "_initialized", False)
    data_dir = tmp_path / "data"
    (data_dir / "output").mkdir(parents=True)
    monkeypatch.setattr(paths_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(dashboard, "DATA_DIR", data_dir)

    def make_client(**setting_overrides):
        settings = Settings(_env_file=None, platform="web", **setting_overrides)
        monkeypatch.setattr(dashboard, "get_settings", lambda: settings)
        return TestClient(dashboard.create_app())

    return make_client


# ---------------------------------------------------------------------------
# B1: /proxy XSS hardening + /api/panels auth secret masking & preservation
# ---------------------------------------------------------------------------


class TestProxyXssHardening:
    @pytest.mark.parametrize(
        ("upstream_ct", "expected_ct", "expect_attachment"),
        [
            ("application/json; charset=utf-8", "application/json", False),
            ("text/plain; charset=utf-8", "text/plain; charset=utf-8", False),
            ("image/png", "image/png", False),
            ("image/jpeg", "image/jpeg", False),
            ("image/webp", "image/webp", False),
            ("image/gif", "image/gif", False),
            ("text/html; charset=utf-8", "application/octet-stream", True),
            ("image/svg+xml", "application/octet-stream", True),
            ("application/javascript", "application/octet-stream", True),
            ("text/xml", "application/octet-stream", True),
        ],
    )
    def test_proxy_sets_security_headers_and_coerces_unsafe_media_types(
        self, client_factory, monkeypatch, upstream_ct, expected_ct, expect_attachment
    ):
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))],
        )

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, headers=None):
                return httpx.Response(200, content=b"<script>alert(1)</script>", headers={"content-type": upstream_ct})

        monkeypatch.setattr(cache_mod.httpx, "Client", FakeClient)
        client = client_factory()
        res = client.get("/proxy", params={"url": "https://example.com/resource", "ttl": 0})
        assert res.status_code == 200
        assert res.headers["content-security-policy"] == "default-src 'none'; sandbox"
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["content-type"] == expected_ct
        if expect_attachment:
            assert res.headers.get("content-disposition") == "attachment"
        else:
            assert "content-disposition" not in res.headers


class TestPanelSecretMasking:
    def test_panel_auth_secrets_are_redacted_on_read_and_preserved_on_put(self, client_factory, monkeypatch):
        from phoenix.service import PhoenixService

        monkeypatch.setattr(PhoenixService, "render_preview", lambda self, name: None)
        client = client_factory()

        # Create bearer-token panel
        created = client.post(
            "/api/panels",
            json={
                "id": "acme_metrics",
                "title": "Acme Metrics",
                "layout": "big_number",
                "config": {},
                "data_source": {
                    "type": "http",
                    "url": "https://metrics.example.com/mrr",
                    "auth": {"type": "bearer", "token": "super-secret-token-123"},
                    "mappings": {"value": "mrr"},
                },
            },
        )
        assert created.status_code == 200
        body = created.json()
        assert body["data_source"]["auth"]["token"] == dashboard.REDACTED_SECRET
        assert body["data_source"]["auth"]["has_token"] is True
        assert "super-secret-token-123" not in created.text

        # GET /api/panels and GET /api/panels/{id} must also mask
        listed = client.get("/api/panels")
        assert "super-secret-token-123" not in listed.text
        assert listed.json()[0]["data_source"]["auth"]["token"] == dashboard.REDACTED_SECRET

        fetched = client.get("/api/panels/acme_metrics")
        assert "super-secret-token-123" not in fetched.text
        assert fetched.json()["data_source"]["auth"]["token"] == dashboard.REDACTED_SECRET

        # PUT with masked sentinel preserves the real stored secret and does not persist has_token
        updated = client.put(
            "/api/panels/acme_metrics",
            json={
                "title": "Acme Metrics v2",
                "data_source": {
                    "type": "http",
                    "url": "https://metrics.example.com/mrr",
                    "auth": {"type": "bearer", "token": dashboard.REDACTED_SECRET, "has_token": True},
                    "mappings": {"value": "mrr"},
                },
            },
        )
        assert updated.status_code == 200
        assert updated.json()["data_source"]["auth"]["token"] == dashboard.REDACTED_SECRET
        raw = PanelDatabase().get("acme_metrics")
        assert raw is not None
        assert raw["data_source"]["auth"]["token"] == "super-secret-token-123"
        assert "has_token" not in raw["data_source"]["auth"]

        # PUT with omitted/blank token also preserves the stored secret
        client.put(
            "/api/panels/acme_metrics",
            json={
                "data_source": {
                    "type": "http",
                    "url": "https://metrics.example.com/mrr",
                    "auth": {"type": "bearer"},
                    "mappings": {"value": "mrr"},
                },
            },
        )
        assert PanelDatabase().get("acme_metrics")["data_source"]["auth"]["token"] == "super-secret-token-123"

        # PUT with a new token replaces it
        client.put(
            "/api/panels/acme_metrics",
            json={
                "data_source": {
                    "type": "http",
                    "url": "https://metrics.example.com/mrr",
                    "auth": {"type": "bearer", "token": "rotated-secret-456"},
                    "mappings": {"value": "mrr"},
                },
            },
        )
        assert PanelDatabase().get("acme_metrics")["data_source"]["auth"]["token"] == "rotated-secret-456"

        # Basic auth password masking and preservation
        basic = client.post(
            "/api/panels",
            json={
                "id": "acme_basic",
                "title": "Basic",
                "layout": "big_number",
                "config": {},
                "data_source": {
                    "type": "http",
                    "url": "https://metrics.example.com/basic",
                    "auth": {"type": "basic", "username": "ops", "password": "pw-secret"},
                    "mappings": {"value": "v"},
                },
            },
        )
        assert basic.status_code == 200
        assert "pw-secret" not in basic.text
        assert basic.json()["data_source"]["auth"]["password"] == dashboard.REDACTED_SECRET
        assert basic.json()["data_source"]["auth"]["has_password"] is True

        client.put(
            "/api/panels/acme_basic",
            json={
                "data_source": {
                    "type": "http",
                    "url": "https://metrics.example.com/basic",
                    "auth": {"type": "basic", "username": "ops", "password": ""},
                    "mappings": {"value": "v"},
                },
            },
        )
        assert PanelDatabase().get("acme_basic")["data_source"]["auth"]["password"] == "pw-secret"

    def test_panel_preview_preserves_stored_secret_when_id_supplied(self, client_factory, monkeypatch):
        from phoenix.service import PhoenixService

        monkeypatch.setattr(PhoenixService, "render_preview", lambda self, name: None)
        monkeypatch.setattr(render_mod, "_run_pixlet", lambda *a, **kw: None)
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))],
        )

        seen_headers: list[dict[str, str]] = []

        def fake_fetch(source, settings=None, *, raise_on_blocked=False):
            seen_headers.append(dp._build_headers(source))
            return {"mrr": 999}

        monkeypatch.setattr(dp, "_fetch_http_source", fake_fetch)

        client = client_factory()
        client.post(
            "/api/panels",
            json={
                "id": "acme_preview",
                "title": "Acme Preview",
                "layout": "big_number",
                "config": {},
                "data_source": {
                    "type": "http",
                    "url": "https://metrics.example.com/mrr",
                    "auth": {"type": "bearer", "token": "preview-secret-xyz"},
                    "mappings": {"value": "mrr"},
                },
            },
        )

        res = client.post(
            "/api/panels/preview",
            json={
                "id": "acme_preview",
                "title": "Acme Preview",
                "layout": "big_number",
                "config": {},
                "data_source": {
                    "type": "http",
                    "url": "https://metrics.example.com/mrr",
                    "auth": {"type": "bearer", "token": dashboard.REDACTED_SECRET},
                    "mappings": {"value": "mrr"},
                },
            },
        )
        assert res.status_code == 200
        assert seen_headers == [{"Authorization": "Bearer preview-secret-xyz"}]


# ---------------------------------------------------------------------------
# B2: Path traversal hardening on all identifiers
# ---------------------------------------------------------------------------


class TestIdentifierAndPathHardening:
    @pytest.mark.parametrize("bad_id", ["..hidden", "../etc", "a/b", "a\\b", "-leading", "", "has space", "foo.bar"])
    def test_paths_helpers_reject_invalid_identifiers(self, bad_id):
        for fn in (
            paths_mod.star_path,
            paths_mod.python_app_path,
            paths_mod.static_app_path,
            paths_mod.output_path,
            paths_mod.output_path_large,
            paths_mod.data_path,
            paths_mod.has_preprocessor,
        ):
            with pytest.raises(ValueError):
                fn(bad_id)
        if bad_id:
            for fn in (
                paths_mod.current_app_file,
                paths_mod.current_display_file,
                paths_mod.show_now_file,
            ):
                with pytest.raises(ValueError):
                    fn(bad_id)

    def test_api_endpoints_reject_invalid_identifiers_with_400(self, client_factory):
        client = client_factory()

        assert client.post("/api/panels", json={"id": "../evil", "title": "x"}).status_code == 400
        assert client.get("/api/panels/..evil").status_code == 400
        assert client.put("/api/panels/-bad", json={"title": "x"}).status_code == 400
        assert client.delete("/api/panels/bad.id").status_code == 400

        assert client.post("/api/apps/clock/show", params={"device": "../../etc"}).status_code == 400
        assert client.get("/api/apps", params={"device": "../bad"}).status_code == 400
        assert client.get("/api/apps/-evil").status_code == 400
        assert client.get("/api/apps/evil.star/schema").status_code == 400
        assert client.post("/api/apps/..evil/preview").status_code == 400

        assert client.post("/api/devices", json={"id": "../evil", "name": "Evil"}).status_code == 400
        assert client.get("/api/devices/-bad").status_code == 400
        assert client.put("/api/devices/bad.dev", json={"brightness": 100}).status_code == 400
        assert client.delete("/api/devices/bad.dev").status_code == 400

        assert client.post("/api/playlists", json={"id": "../evil", "name": "Bad"}).status_code == 400
        assert client.put("/api/playlists/-bad", json={"name": "Bad"}).status_code == 400
        assert client.delete("/api/playlists/bad.pl").status_code == 400

        assert client.post("/api/store/..evil/install").status_code == 400
        assert client.post("/api/store/-evil/preview").status_code == 400

    def test_shop_and_run_panel_reject_traversal_and_symlink_escape(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "apps").mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "pwn.star").write_text("load('render.star', 'render')\n")
        (repo / "apps" / "evil_link").symlink_to(outside)

        with pytest.raises(ValueError):
            shop_mod._resolve_app_dir(repo, "../outside")
        with pytest.raises(ValueError):
            shop_mod._resolve_app_dir(repo, "evil_link")
        with pytest.raises(ValueError):
            shop_mod.import_app(repo, "../outside", tmp_path / "dest")
        with pytest.raises(ValueError):
            dp.run_panel("../escape", Settings(_env_file=None), db_path=tmp_path / "p.db")


# ---------------------------------------------------------------------------
# B3: CLI argument injection & env isolation in pixlet render
# ---------------------------------------------------------------------------


class TestPixletHardening:
    @pytest.mark.parametrize("bad_key", ["-o", "--output", "-m", "bad key", "../x", ""])
    def test_api_app_config_rejects_flag_injection_keys(self, client_factory, bad_key):
        client = client_factory()
        client.post("/api/apps/clock/add")
        res = client.put("/api/apps/clock/config", json={bad_key: "/tmp/pwn.webp"})
        assert res.status_code == 400

    def test_api_app_config_accepts_valid_keys(self, client_factory):
        client = client_factory()
        client.post("/api/apps/clock/add")
        res = client.put("/api/apps/clock/config", json={"timezone": "UTC", "font.size": "large", "bg-color": "#000"})
        assert res.status_code == 200
        assert res.json()["pixlet_config"]["font.size"] == "large"

    def test_run_pixlet_validates_keys_sets_timeout_and_strips_secret_env(self, tmp_path, monkeypatch):
        star = tmp_path / "demo.star"
        star.write_text("def main(): pass\n")
        monkeypatch.setattr(render_mod, "APPS_DIR", tmp_path)
        monkeypatch.setattr(render_mod, "output_path", lambda name: tmp_path / f"{name}.webp")
        monkeypatch.setattr(render_mod, "output_path_large", lambda name: tmp_path / f"{name}.large.webp")

        # Leading dash key raises before spawning subprocess
        called = False

        def should_not_run(*args, **kwargs):
            nonlocal called
            called = True
            return subprocess.CompletedProcess(args[0], 0, "", "")

        monkeypatch.setattr(render_mod.subprocess, "run", should_not_run)
        with pytest.raises(ValueError, match="Invalid pixlet_config key"):
            render_mod._run_pixlet(AppConfig(name="demo", pixlet_config={"-o": "/tmp/evil.webp"}), Settings(_env_file=None))
        assert called is False

        # Valid config runs with timeout=60 and stripped env (no PHOENIX_* secrets)
        monkeypatch.setenv("PHOENIX_HA_TOKEN", "secret-ha-token")
        monkeypatch.setenv("PHOENIX_MQTT_PASSWORD", "secret-mqtt-pass")
        monkeypatch.setenv("TZ", "America/New_York")

        captured: dict[str, object] = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            captured["timeout"] = kwargs.get("timeout")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(render_mod.subprocess, "run", fake_run)
        render_mod._run_pixlet(AppConfig(name="demo", pixlet_config={"city": "NYC"}), Settings(_env_file=None))
        assert captured["timeout"] == 60
        env = captured["env"]
        assert isinstance(env, dict)
        assert "PHOENIX_HA_TOKEN" not in env
        assert "PHOENIX_MQTT_PASSWORD" not in env
        assert env.get("TZ") == "America/New_York"


# ---------------------------------------------------------------------------
# B4: Panel HTTP SSRF, fail-safe bind default, and CSRF / Origin middleware
# ---------------------------------------------------------------------------


class TestPanelSsrfAndBindDefaults:
    def test_settings_defaults_are_fail_safe(self):
        settings = Settings(_env_file=None)
        assert settings.dashboard_host == "127.0.0.1"
        assert settings.allow_private_panel_urls is False

    @pytest.mark.parametrize(
        "always_blocked",
        [
            "file:///etc/passwd",
            "ftp://example.com/a",
            "http://user:pass@192.168.1.50/metrics",
            "http://localhost:7002/api/panels",
            "http://127.0.0.1:7002/api/panels",
            "http://[::1]:7002/api/panels",
            "http://[::ffff:127.0.0.1]/api/panels",
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.1.2/meta",
            "http://0.0.0.0/",
        ],
    )
    def test_panel_url_always_blocks_loopback_metadata_and_bad_schemes(self, always_blocked):
        with pytest.raises(ValueError):
            validate_panel_url(always_blocked, allow_private=False)
        with pytest.raises(ValueError):
            validate_panel_url(always_blocked, allow_private=True)

    def test_panel_url_private_lan_toggle(self):
        for lan_url in ("http://192.168.1.50:9090/metrics", "http://10.0.0.12:3000/api/health"):
            with pytest.raises(ValueError):
                validate_panel_url(lan_url, allow_private=False)
            validate_panel_url(lan_url, allow_private=True)

    def test_panel_preview_blocks_ssrf_with_400(self, client_factory):
        client = client_factory(allow_private_panel_urls=False)
        for url in ("http://169.254.169.254/latest/meta-data/", "http://192.168.1.10/secret", "http://127.0.0.1:7002/api/panels"):
            res = client.post(
                "/api/panels/preview",
                json={
                    "title": "SSRF",
                    "layout": "big_number",
                    "config": {},
                    "data_source": {"type": "http", "url": url, "mappings": {"value": "x"}},
                },
            )
            assert res.status_code == 400

        # With allow_private_panel_urls=True, metadata and loopback are STILL blocked
        private_client = client_factory(allow_private_panel_urls=True)
        for url in ("http://169.254.169.254/latest/meta-data/", "http://127.0.0.1:7002/api/panels"):
            res = private_client.post(
                "/api/panels/preview",
                json={
                    "title": "SSRF",
                    "layout": "big_number",
                    "config": {},
                    "data_source": {"type": "http", "url": url, "mappings": {"value": "x"}},
                },
            )
            assert res.status_code == 400


class TestCsrfOriginMiddleware:
    def test_mutating_api_requests_blocked_on_cross_origin_and_allowed_same_origin_or_cli(self, client_factory):
        client = client_factory()

        # Non-browser / CLI / HA requests without Origin or Sec-Fetch-Site succeed
        assert client.post("/api/apps/clock/add").status_code == 200

        # Same-origin browser headers succeed (case-insensitive Host match)
        assert (
            client.post(
                "/api/apps/clock/enable",
                headers={"Origin": "http://testserver", "Host": "TESTSERVER", "Sec-Fetch-Site": "same-origin"},
            ).status_code
            == 200
        )

        # Cross-site / same-site Sec-Fetch-Site rejected with 403
        assert (
            client.post("/api/apps/clock/disable", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        )
        assert (
            client.put("/api/config", json={"brightness": 100}, headers={"Sec-Fetch-Site": "same-site"}).status_code
            == 403
        )

        # Origin: null and mismatched Origin rejected with 403
        assert client.post("/api/apps/clock/disable", headers={"Origin": "null"}).status_code == 403
        assert client.delete("/api/apps/clock", headers={"Origin": "https://evil.example"}).status_code == 403

        # GET requests remain readable
        assert client.get("/api/apps", headers={"Origin": "https://evil.example"}).status_code == 200

    def test_ws_state_rejects_cross_origin_and_allows_same_origin(self, client_factory):
        client = client_factory()

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/state", headers={"Origin": "https://evil.example"}):
                pass

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/state", headers={"Origin": "null"}):
                pass

        with client.websocket_connect("/ws/state", headers={"Origin": "http://testserver"}) as ws:
            msg = ws.receive_json()
            assert "apps" in msg


# ---------------------------------------------------------------------------
# B5: Response size cap, format-string guard, HA entity_id validation
# ---------------------------------------------------------------------------


class TestCacheSizeCapAndGuards:
    def test_cache_rejects_oversized_streaming_response_without_caching(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_mod, "CACHE_DB", tmp_path / "cache.db")
        monkeypatch.setattr(cache_mod, "_initialized", False)

        class FakeStreamResponse:
            status_code = 200
            is_redirect = False
            headers = {"content-type": "application/octet-stream"}

            def iter_bytes(self):
                yield b"a" * 600
                yield b"b" * 600

        class FakeStreamingClient:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            @contextmanager
            def stream(self, method, url, headers=None):
                yield FakeStreamResponse()

        monkeypatch.setattr(cache_mod.httpx, "Client", FakeStreamingClient)

        with pytest.raises(cache_mod.ResponseTooLargeError):
            cache_mod.cache_get_meta("https://example.com/huge", ttl=300, max_bytes=1024)

        # Ensure nothing was written to SQLite cache
        with cache_mod._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM http_cache").fetchone()[0]
        assert count == 0

    def test_proxy_returns_413_on_oversized_response(self, client_factory, monkeypatch):
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))],
        )
        monkeypatch.setattr(cache_mod, "MAX_RESPONSE_BYTES", 128)

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, headers=None):
                return httpx.Response(200, content=b"x" * 256, headers={"content-type": "text/plain"})

        monkeypatch.setattr(cache_mod.httpx, "Client", FakeClient)
        client = client_factory()
        res = client.get("/proxy", params={"url": "https://example.com/big", "ttl": 0})
        assert res.status_code == 413

    def test_panel_format_string_guard_allows_safe_and_blocks_dangerous(self):
        assert dp._apply_transform(12345, "/ 100 | format $%.2f") == "$123.45"
        assert dp._apply_transform(42, "format $%d") == "$42"
        assert dp._apply_transform(87.5, "format %.1f%%") == "87.5%"
        assert dp._apply_transform(21.4, "format %+.1f°C") == "+21.4°C"

        # Width DoS, precision DoS, multiple placeholders, mapping syntax safely fall back
        assert dp._apply_transform(42, "format %999999999f") == "42.0"
        assert dp._apply_transform(42, "format %.999999f") == "42.0"
        assert dp._apply_transform(42, "format %s %s") == "42.0"
        assert dp._apply_transform(42, "format %(secret)s") == "42.0"

    def test_ha_entity_id_validation(self, monkeypatch):
        assert is_valid_ha_entity_id("sensor.living_room_temperature") is True
        assert is_valid_ha_entity_id("binary_sensor.front_door_1") is True
        for bad in ("../config", "sensor.temp?foo=1", "sensor/temp", "SENSOR.UPPER", "nodot", "a.b.c", ""):
            assert is_valid_ha_entity_id(bad) is False

        fetched = False

        def fail_if_called(*args, **kwargs):
            nonlocal fetched
            fetched = True
            raise AssertionError("cache_get must not be called for invalid entity_id")

        monkeypatch.setattr(dp, "cache_get_meta", fail_if_called)
        monkeypatch.setattr(home_climate, "cache_get", fail_if_called)

        settings = Settings(_env_file=None, ha_url="http://ha.local:8123", ha_token="tok")
        res = dp._fetch_ha_source_checked({"entity_id": "../config"}, settings)
        assert res.healthy is False
        assert "Invalid Home Assistant entity ID" in res.reason
        assert home_climate._fetch_entity("../config", settings) == {}
        assert fetched is False
