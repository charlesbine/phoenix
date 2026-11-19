"""SSRF hardening tests for the dashboard /proxy endpoint."""

import socket

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def proxy_client(tmp_path, monkeypatch):
    import phoenix.cache as cache_mod
    import phoenix.db as db_mod
    import phoenix.paths as paths_mod
    from phoenix.server import dashboard
    from phoenix.settings import Settings

    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "dash.db")
    monkeypatch.setattr(cache_mod, "CACHE_DB", tmp_path / "cache.db")
    monkeypatch.setattr(cache_mod, "_initialized", False)
    data_dir = tmp_path / "data"
    (data_dir / "output").mkdir(parents=True)
    monkeypatch.setattr(paths_mod, "DATA_DIR", data_dir)

    def make_client(**setting_overrides):
        settings = Settings(_env_file=None, platform="web", **setting_overrides)
        monkeypatch.setattr(dashboard, "get_settings", lambda: settings)
        return TestClient(dashboard.create_app())

    return make_client


@pytest.mark.parametrize(
    "bad_url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "gopher://127.0.0.1:70/_",
        "http://user:pass@example.com/secret",
        "http://localhost:7002/api/devices",
        "http://homeassistant.local:8123/api/states",
        "http://127.0.0.1:7002/api/devices",
        "http://[::1]:7002/api/devices",
        "http://[::ffff:127.0.0.1]/api/devices",
        "http://169.254.169.254/latest/meta-data/",
        "http://192.168.1.100/json/state",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://0.0.0.0/",
    ],
)
def test_proxy_rejects_disallowed_schemes_and_private_targets(proxy_client, bad_url):
    client = proxy_client()
    res = client.get("/proxy", params={"url": bad_url})
    assert res.status_code == 400


def test_proxy_rejects_hostname_resolving_to_private_ip(proxy_client, monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.42", port))],
    )
    client = proxy_client()
    res = client.get("/proxy", params={"url": "https://rebind.example.com/data"})
    assert res.status_code == 400


def test_proxy_blocks_redirect_to_private_ip(proxy_client, monkeypatch):
    import phoenix.cache as cache_mod

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
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    monkeypatch.setattr(cache_mod.httpx, "Client", FakeClient)
    client = proxy_client()
    res = client.get("/proxy", params={"url": "https://public.example.com/start"})
    assert res.status_code == 400


def test_proxy_allows_public_url_and_respects_allowlist(proxy_client, monkeypatch):
    import phoenix.cache as cache_mod

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
            return httpx.Response(200, content=b"sunny", headers={"content-type": "text/plain"})

    monkeypatch.setattr(cache_mod.httpx, "Client", FakeClient)
    client = proxy_client(proxy_allowed_hosts="wttr.in, api.nasa.gov")
    assert client.get("/proxy", params={"url": "https://wttr.in/San+Francisco?m0qFAT"}).text == "sunny"
    assert client.get("/proxy", params={"url": "https://other.example.com/"}).status_code == 400
