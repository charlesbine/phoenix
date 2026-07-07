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


def test_builtin_live_apps_are_regular_device_apps(client):
    apps = {a["name"]: a for a in client.get("/api/apps").json()}
    assert apps["nowplaying"]["app_type"] == "live_nowplaying"
    assert apps["nowplaying"]["is_live"] is True
    assert apps["audio_vu"]["app_type"] == "live_audio"
    assert apps["audio_vu"]["is_live"] is True
    assert apps["audio_bars"]["pixlet_config"]["bar_spacing"] == "solid"
    assert apps["audio_bars"]["pixlet_config"]["noise_gate"] == "0.08"
    assert apps["audio_spectrogram"]["pixlet_config"]["bar_width"] == "2"
    assert apps["audio_spectrogram"]["pixlet_config"]["noise_gate"] == "0.03"
    assert apps["nowplaying"]["enabled"] is False  # available, not globally rotating

    client.post("/api/devices", json={"id": "apollo", "name": "Apollo", "backend": "wled"})
    client.post("/api/apps/nowplaying/add", params={"device": "apollo"})
    client.post("/api/apps/audio_vu/add", params={"device": "apollo"})

    apollo = client.get("/api/apps", params={"device": "apollo"}).json()
    assert {a["name"] for a in apollo} == {"nowplaying", "audio_vu"}
    assert {a["name"]: a["enabled"] for a in apollo} == {"nowplaying": True, "audio_vu": True}


def test_live_spectrogram_schema_exposes_bar_width(client):
    schema = client.get("/api/apps/audio_spectrogram/schema").json()

    assert [field["id"] for field in schema] == ["bar_width", "palette", "contrast", "floor_db", "noise_gate"]
    assert schema[0] == {
        "type": "dropdown",
        "id": "bar_width",
        "name": "Spectrogram bar width",
        "desc": "Frequency rows map evenly to the 64px panel.",
        "default": "2",
        "options": [
            {"display": "1 px", "value": "1"},
            {"display": "2 px", "value": "2"},
        ],
    }
    assert schema[1]["default"] == "hue"
    assert schema[2]["default"] == "high"
    assert schema[3]["default"] == "-62"
    assert schema[4]["default"] == "0.03"


def test_live_bars_schema_exposes_uniform_spacing_controls(client):
    schema = client.get("/api/apps/audio_bars/schema").json()

    assert schema == [
        {
            "type": "dropdown",
            "id": "bar_width",
            "name": "Bar width",
            "desc": "Every analyzer bar uses the same pixel width.",
            "default": "2",
            "options": [
                {"display": "1 px", "value": "1"},
                {"display": "2 px", "value": "2"},
            ],
        },
        {
            "type": "dropdown",
            "id": "bar_spacing",
            "name": "Bar spacing",
            "desc": "Solid removes gaps between bars.",
            "default": "solid",
            "options": [
                {"display": "Solid", "value": "solid"},
                {"display": "Separated", "value": "separated"},
            ],
        },
        {
            "type": "dropdown",
            "id": "floor_db",
            "name": "Noise floor",
            "desc": "Raises silence cutoff without changing frequency range.",
            "default": "-55",
            "options": [
                {"display": "-50 dB", "value": "-50"},
                {"display": "-55 dB", "value": "-55"},
                {"display": "-62 dB", "value": "-62"},
                {"display": "-70 dB", "value": "-70"},
            ],
        },
        {
            "type": "dropdown",
            "id": "noise_gate",
            "name": "Noise gate",
            "desc": "Suppresses residual low-level energy after normalization.",
            "default": "0.08",
            "options": [
                {"display": "Off", "value": "0"},
                {"display": "Light", "value": "0.04"},
                {"display": "Medium", "value": "0.08"},
                {"display": "Strong", "value": "0.12"},
            ],
        },
    ]


def test_show_live_app_uses_normal_show_path_and_exits_legacy_mode(client):
    from phoenix.paths import show_now_file

    client.post("/api/devices", json={"id": "apollo", "name": "Apollo", "backend": "wled"})
    client.put("/api/devices/apollo", json={"content_mode": "audio", "audio_mode": "spectrogram"})

    res = client.post("/api/apps/nowplaying/show", params={"device": "apollo"}).json()
    assert res["showing"] == "nowplaying"
    assert show_now_file("apollo").read_text() == "nowplaying"
    assert client.get("/api/devices/apollo").json()["content_mode"] == "apps"


def test_now_playing_is_per_device(client):
    from phoenix.paths import current_app_file

    client.post("/api/devices", json={"id": "apollo", "name": "Apollo", "backend": "wled"})
    current_app_file("apollo").write_text("spotify")
    current_app_file("main").write_text("clock")

    assert client.get("/api/now-playing", params={"device": "apollo"}).json()["app"] == "spotify"
    assert client.get("/api/now-playing", params={"device": "main"}).json()["app"] == "clock"


def test_health_check_does_not_run_privileged_commands(client, monkeypatch):
    import subprocess

    def fail_run(*args, **kwargs):
        raise AssertionError(f"/api/health must not shell out: {args!r} {kwargs!r}")

    monkeypatch.setattr(subprocess, "run", fail_run)
    res = client.get("/api/health")

    assert res.status_code in {200, 503}
    assert "status" in res.json()
