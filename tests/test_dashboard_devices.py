"""Device-scoped dashboard API — devices CRUD and ?device= routing.

Drives the FastAPI app with an isolated DB + data dir so we can exercise the
per-device endpoints the frontend switcher relies on.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import phoenix.db as db_mod
    import phoenix.paths as paths_mod

    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "dash.db")
    data_dir = tmp_path / "data"
    (data_dir / "output").mkdir(parents=True)
    monkeypatch.setattr(paths_mod, "DATA_DIR", data_dir)

    from phoenix.server.dashboard import create_app

    return TestClient(create_app())


def test_seed_exposes_main_device(client):
    devices = client.get("/api/devices").json()
    assert [d["id"] for d in devices] == ["main"]


def test_device_rotation_is_independent(client):
    # Register two global apps and a second panel.
    for name in ("clock", "weather"):
        assert client.post(f"/api/apps/{name}/add").status_code == 200
    client.post("/api/devices", json={"id": "apollo", "name": "Apollo", "backend": "wled"})

    # Add both to apollo's rotation; main stays empty.
    client.post("/api/apps/clock/add", params={"device": "apollo"})
    client.post("/api/apps/weather/add", params={"device": "apollo"})

    apollo = client.get("/api/apps", params={"device": "apollo"}).json()
    assert {a["name"] for a in apollo} == {"clock", "weather"}
    assert client.get("/api/apps", params={"device": "main"}).json() == []

    # Disable weather on apollo — global app definition untouched.
    client.post("/api/apps/weather/disable", params={"device": "apollo"})
    apollo = {a["name"]: a for a in client.get("/api/apps", params={"device": "apollo"}).json()}
    assert apollo["weather"]["enabled"] is False
    assert client.get("/api/apps/weather").json()["enabled"] is True  # global unchanged

    # Reorder apollo's rotation.
    client.put("/api/reorder", params={"device": "apollo"}, json={"order": ["weather", "clock"]})
    ordered = [a["name"] for a in client.get("/api/apps", params={"device": "apollo"}).json()]
    assert ordered == ["weather", "clock"]

    # Remove clock from apollo (app still exists globally).
    client.post("/api/apps/clock/remove", params={"device": "apollo"})
    assert [a["name"] for a in client.get("/api/apps", params={"device": "apollo"}).json()] == ["weather"]
    assert client.get("/api/apps/clock").json()["name"] == "clock"


def test_per_device_config_and_priority(client):
    client.post("/api/devices", json={"id": "apollo", "name": "Apollo", "backend": "wled"})

    # Brightness is per-device; changing apollo doesn't touch main/global.
    client.put("/api/config", params={"device": "apollo"}, json={"brightness": 42})
    assert client.get("/api/config", params={"device": "apollo"}).json()["brightness"] == 42
    assert client.get("/api/config").json()["brightness"] != 42

    # Priority writes to the device membership.
    client.post("/api/apps/clock/add")
    client.post("/api/apps/clock/add", params={"device": "apollo"})
    client.put("/api/apps/clock/priority", params={"device": "apollo"}, json={"priority": 3})
    row = client.get("/api/apps", params={"device": "apollo"}).json()[0]
    assert row["name"] == "clock" and row["priority"] == 3


def test_content_mode_toggle(client):
    # Seeded main defaults to the app rotation.
    main = client.get("/api/devices/main").json()
    assert main["content_mode"] == "apps" and main["audio_mode"] == "bars"

    client.post("/api/devices", json={"id": "apollo", "name": "Apollo", "backend": "wled"})
    client.put("/api/devices/apollo", json={"content_mode": "audio", "audio_mode": "spectrogram"})

    dev = client.get("/api/devices/apollo").json()
    assert dev["content_mode"] == "audio" and dev["audio_mode"] == "spectrogram"
    # other panels are unaffected
    assert client.get("/api/devices/main").json()["content_mode"] == "apps"


def test_now_playing_is_per_device(client):
    from phoenix.paths import current_app_file

    client.post("/api/devices", json={"id": "apollo", "name": "Apollo", "backend": "wled"})
    current_app_file("apollo").write_text("spotify")
    current_app_file("main").write_text("clock")

    assert client.get("/api/now-playing", params={"device": "apollo"}).json()["app"] == "spotify"
    assert client.get("/api/now-playing", params={"device": "main"}).json()["app"] == "clock"
