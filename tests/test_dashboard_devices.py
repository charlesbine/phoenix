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
    from phoenix.server import dashboard
    from phoenix.settings import Settings

    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "dash.db")
    data_dir = tmp_path / "data"
    (data_dir / "output").mkdir(parents=True)
    monkeypatch.setattr(paths_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(dashboard, "get_settings", lambda: Settings(_env_file=None, platform="web"))

    return TestClient(dashboard.create_app())


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


def test_single_app_is_scoped_to_an_eligible_rotation_member(client):
    for device in ("aurora", "eos"):
        client.post("/api/devices", json={"id": device, "name": device})
    for name in ("clock", "pixel_planet"):
        client.post(f"/api/apps/{name}/add")
        client.post(f"/api/apps/{name}/add", params={"device": "aurora"})
    aurora = {"device": "aurora"}

    assert client.get("/api/config", params=aurora).json()["single_app"] is None
    assert client.put("/api/config", params=aurora, json={
        "layout_mode": "single", "single_app": "pixel_planet",
    }).json()["single_app"] == "pixel_planet"
    assert client.get("/api/config", params={"device": "eos"}).json()["single_app"] is None
    assert client.put("/api/devices/eos", json={"single_app": "pixel_planet"}).status_code == 422

    client.post("/api/apps/clock/disable", params=aurora)
    assert client.put("/api/config", params=aurora, json={"single_app": "clock"}).status_code == 422
    assert client.put("/api/config", params=aurora, json={"layout_mode": "cycle"}).json()[
        "single_app"
    ] == "pixel_planet"
    assert client.put("/api/devices/aurora", json={"single_app": None}).json()["single_app"] is None


def test_panel_brightness_schedule_persists_without_changing_fallback(client):
    from datetime import datetime, timezone

    from phoenix.models import BrightnessSchedule, DisplaySettings

    client.post("/api/devices", json={"id": "apollo", "name": "Apollo", "backend": "wled", "brightness": 64})
    schedule = {
        "enabled": True,
        "mode": "custom",
        "steps": [
            {"time": "23:00", "brightness": 0},
            {"time": "07:00", "brightness": 16},
            {"time": "09:00", "brightness": 64},
            {"time": "18:00", "brightness": 24},
        ],
    }
    default = client.get("/api/devices/apollo").json()["brightness_schedule"]
    assert default == {"mode": "night", "enabled": True, "steps": []}
    settings = {"timezone": "America/New_York", "latitude": 40.71, "longitude": -74.01}
    assert client.put("/api/settings/display", json=settings).json() == settings
    global_settings = client.get("/api/settings/display").json()
    assert global_settings["settings"] == settings
    assert "America/New_York" in global_settings["timezones"]
    assert client.put("/api/settings/display", json={"timezone": "Mars/Olympus"}).status_code == 422
    assert client.put("/api/settings/display", json={"latitude": 1}).status_code == 422
    endpoint = "/api/devices/apollo/brightness-schedule"
    assert client.put(endpoint, json=schedule).status_code == 200
    apollo = client.get("/api/devices/apollo").json()
    assert apollo["brightness"] == 64
    assert client.get("/api/devices/main").json()["brightness_schedule"] is None
    saved = BrightnessSchedule.model_validate(apollo["brightness_schedule"])
    assert [saved.level_at(DisplaySettings(**settings), 64, datetime(2026, 11, 17, hour, tzinfo=timezone.utc))
            for hour in (2, 4, 10, 12, 14, 23)] == [24, 0, 0, 16, 64, 24]

    assert client.put(endpoint, json={**schedule, "steps": schedule["steps"] * 2}).status_code == 422
    assert client.put(endpoint, json={**schedule, "steps": []}).status_code == 422
    assert client.put("/api/devices/main/brightness-schedule", json=schedule).status_code == 422
    assert client.put(endpoint, json={**schedule, "enabled": False}).status_code == 200
    assert not client.get("/api/devices/apollo").json()["brightness_schedule"]["enabled"]

    client.delete("/api/devices/apollo")
    assert client.put(endpoint, json=schedule).status_code == 404
    client.post("/api/devices", json={"id": "apollo", "name": "Apollo", "backend": "wled"})
    assert client.get("/api/devices/apollo").json()["brightness_schedule"] == default


def test_panel_controls_report_live_night_mode_phase(client, monkeypatch):
    from datetime import datetime, timezone

    from phoenix.models import DisplaySettings

    local = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(DisplaySettings, "local_time", lambda self, now=None: local)
    client.post("/api/devices", json={"id": "aurora", "name": "Aurora", "backend": "serial", "brightness": 200})
    path = "/api/config?device=aurora"
    key = "brightness_schedule_status"
    assert client.get(path).json()[key] == "daytime"
    with client.websocket_connect("/ws/state?device=aurora") as socket:
        assert socket.receive_json()["config"][key] == "daytime"
        local = local.replace(hour=20)
        assert socket.receive_json()["config"][key] == "dimmed"
        local = local.replace(hour=3)
        off = socket.receive_json()["config"]
        assert off[key] == "off"
        assert off["brightness"] == 200

    schedule = "/api/devices/aurora/brightness-schedule"
    client.put(schedule, json={"enabled": False, "mode": "night"})
    assert client.get(path).json()[key] is None
    client.put(schedule, json={"enabled": True, "mode": "custom", "steps": [{"time": "20:00", "brightness": 80}]})
    assert client.get(path).json()[key] == "custom"


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
    assert apps["audio_spectrogram"]["pixlet_config"]["noise_gate"] == "0.02"
    assert apps["nowplaying"]["enabled"] is False  # available, not globally rotating

    client.post("/api/devices", json={"id": "apollo", "name": "Apollo", "backend": "wled"})
    client.post("/api/apps/nowplaying/add", params={"device": "apollo"})
    client.post("/api/apps/audio_vu/add", params={"device": "apollo"})

    apollo = client.get("/api/apps", params={"device": "apollo"}).json()
    assert {a["name"] for a in apollo} == {"nowplaying", "audio_vu"}
    assert {a["name"]: a["enabled"] for a in apollo} == {"nowplaying": True, "audio_vu": True}


def test_live_spectrogram_schema_exposes_bar_width(client):
    schema = client.get("/api/apps/audio_spectrogram/schema").json()

    assert [field["id"] for field in schema] == [
        "bar_width",
        "palette",
        "contrast",
        "tilt_db",
        "gain_db",
        "onset_boost",
        "floor_db",
        "noise_gate",
    ]
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
    assert schema[1]["desc"] == "Color map for intensity. Frequency position never changes the color."
    assert schema[1]["options"] == [
        {"display": "Hue heat", "value": "hue"},
        {"display": "Fire", "value": "fire"},
        {"display": "Ice", "value": "ice"},
        {"display": "Aurora", "value": "aurora"},
        {"display": "Mono", "value": "mono"},
    ]
    assert schema[2]["default"] == "high"
    assert schema[3]["default"] == "4.5"
    assert schema[4]["default"] == "10"
    assert schema[5]["default"] == "1.4"
    assert schema[6]["default"] == "-66"
    assert schema[7]["default"] == "0.02"


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
                {"display": "-66 dB", "value": "-66"},
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
                {"display": "Very light", "value": "0.02"},
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

    status = client.get("/api/status")
    assert status.status_code == 200
    assert "status" in status.json()


def test_controller_health_reports_paired_player_instead_of_local_m4(client, monkeypatch):
    from phoenix.db import DeviceDatabase
    from phoenix.node import NodePublisher, NodeStatus
    from phoenix.server import dashboard
    from phoenix.settings import Settings

    settings = Settings(platform="web", node_device="aurora", node_url="https://aurora.local")
    publisher = NodePublisher(settings)
    publisher.report = NodeStatus(revision="test")
    publisher.pending = False
    DeviceDatabase().create("aurora", "Aurora", "serial")
    monkeypatch.setattr(dashboard, "get_settings", lambda: settings)
    monkeypatch.setattr(dashboard, "NodePublisher", lambda _: publisher)
    dashboard_client = TestClient(dashboard.create_app())

    health = dashboard_client.get("/api/status").json()
    assert health["player"] == {"name": "Aurora", "status": "synced"}
    assert "m4" not in health
    assert not any("M4" in issue for issue in health["issues"])

    publisher.pending = True
    health = dashboard_client.get("/api/status").json()
    assert health["player"]["status"] == "pending"
    assert "Aurora player offline" not in health["issues"]

    publisher.report = None
    health = dashboard_client.get("/api/status").json()
    assert health["player"]["status"] == "offline"
    assert health["status"] == "degraded"
    assert "Aurora player offline" in health["issues"]


def test_store_catalog_failure_returns_actionable_error(client, monkeypatch):
    from phoenix import shop

    def missing_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(shop, "ensure_repo", missing_git)
    for path in ("/api/store", "/api/store/categories"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json()["detail"] == "Community catalog is unavailable."
    response = client.post("/api/store/sync")
    assert response.status_code == 503
    assert response.json()["detail"] == "Community catalog sync failed."


def test_preview_uses_the_saved_app_config(client, monkeypatch):
    from phoenix import render

    seen = []
    monkeypatch.setattr(render, "_render_dispatch", lambda app, settings: seen.append(app.pixlet_config))
    client.post("/api/apps/procedural_planet/add")
    config = {"planet_type": "lava", "time_speed": "0.2", "n_frames": "1"}
    assert client.put("/api/apps/procedural_planet/config", json=config).json()["pixlet_config"] == config
    schema = client.get("/api/apps/procedural_planet/schema").json()
    planet_type = next(field for field in schema if field["id"] == "planet_type")
    assert "lava" in {option["value"] for option in planet_type["options"]}
    assert client.get("/api/apps/pixel_planet/schema").json() == []
    assert client.post("/api/apps/procedural_planet/preview").status_code == 200
    assert seen == [config]


def test_landscape_is_discovered_with_settings(client):
    response = client.post("/api/apps/procedural_landscape/add")
    assert response.status_code == 200
    fields = client.get("/api/apps/procedural_landscape/schema").json()
    assert {field["id"] for field in fields} == {"palette", "seed"}
    assert {option["value"] for option in fields[0]["options"]} == {"dusk", "alpine", "alien"}
