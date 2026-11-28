import shutil
from io import BytesIO
from threading import Event

from fastapi.testclient import TestClient
from PIL import Image

import phoenix.db as db_module
import phoenix.node as node_module
import phoenix.paths as paths
from phoenix.db import AppDatabase, DeviceDatabase
from phoenix.models import BrightnessSchedule, DisplaySettings
from phoenix.node import NODE_PATH, NodePublisher, build_state, write_text
from phoenix.server.nodes import create_receiver
from phoenix.settings import Settings


def test_publisher_pushes_valid_artwork_and_cached_controls_to_paired_player(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "central.db")
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    node_outputs = tmp_path / "receiver"
    node_outputs.mkdir()
    monkeypatch.setattr(paths, "OUTPUTS_DIR", node_outputs)
    central_outputs = tmp_path / "central"
    central_outputs.mkdir()
    monkeypatch.setattr(node_module, "output_path", lambda name: central_outputs / f"{name}.webp")
    monkeypatch.setattr(node_module, "show_now_file", lambda _device: central_outputs / "show-now.txt")

    central = DeviceDatabase()
    central.create("desk", "Desk", "serial", brightness=32)
    central.create("apollo", "Apollo", "wled")
    app_db = AppDatabase()
    app_db.upsert("planet", pixlet_config={"server_private": "value"})
    app_db.upsert("christmas")
    central.set_app("desk", "planet", sort_order=2)
    rain_config = {"rain_speed": "0.5", "rain_density": "dense"}
    app_db.upsert("matrix_clock", pixlet_config=rain_config)
    central.set_app("desk", "matrix_clock", sort_order=3)
    central.update("desk", layout_mode="single", single_app="planet")
    central.set_app("apollo", "christmas")
    Image.new("RGB", (64, 64), "green").save(central_outputs / "planet.webp")
    Image.new("RGB", (64, 64), "red").save(central_outputs / "christmas.webp")
    schedule = BrightnessSchedule(enabled=True,
                                  steps=[{"time": "23:00", "brightness": 0}])
    central.set_brightness_schedule("desk", schedule)
    display_settings = DisplaySettings(timezone="America/New_York", latitude=40.71, longitude=-74.01)
    central.set_display_settings(display_settings)
    write_text(central_outputs / "show-now.txt", "planet")

    local = DeviceDatabase(tmp_path / "local.db")
    local.create("desk", "Desk", "serial")
    token_file = tmp_path / "token"
    token_file.write_text("t" * 40)
    settings = Settings(_env_file=None, node_device="desk", node_peer="192.168.1.8", node_token_file=str(token_file))
    wake = Event()
    receiver = create_receiver(settings, local, wake)
    headers = {"Authorization": f"Bearer {token_file.read_text()}"}
    assert TestClient(receiver).get(f"{NODE_PATH}/status", headers=headers).status_code == 403
    client = TestClient(receiver, client=("192.168.1.8", 50000))
    assert client.get(f"{NODE_PATH}/status").status_code == 401
    assert client.put(f"{NODE_PATH}/state", content=build_state("desk").model_dump_json(),
                      headers=headers).status_code == 409
    assert client.put(f"{NODE_PATH}/frames/planet?version=f-c", content=b"bad",
                      headers=headers).status_code == 422
    oversized = BytesIO()
    Image.new("RGB", (128, 128)).save(oversized, "WEBP")
    data = oversized.getvalue()
    assert client.put(f"{NODE_PATH}/frames/planet?version=f-{len(data):x}", content=data,
                      headers=headers).status_code == 422

    client.headers.update(headers)
    publisher = NodePublisher(settings)
    publisher.sync_once(client)
    assert publisher.sync_status == "synced"
    assert wake.is_set()
    assert (node_outputs / "planet.webp").read_bytes() == (central_outputs / "planet.webp").read_bytes()
    assert not (node_outputs / "christmas.webp").exists()
    assert local.get("desk")["brightness"] == 32
    assert local.get("desk")["single_app"] == "planet"
    assert BrightnessSchedule.model_validate_json(local.get("desk")["brightness_schedule"]) == schedule
    assert local.get_display_settings() == display_settings
    assert [row["app_name"] for row in local.list_apps("desk")] == ["planet", "matrix_clock"]
    clock = AppDatabase(local._path).get("matrix_clock")
    assert clock.active and clock.runtime == "live_matrix"
    assert clock.pixlet_config == rain_config
    assert not (node_outputs / "matrix_clock.webp").exists()
    assert AppDatabase(local._path).get("planet").pixlet_config == {}

    wake.clear()
    publisher.sync_once(client)
    assert not wake.is_set()  # duplicate commands and unchanged state aren't applied twice
    write_text(paths.current_app_file("desk"), "planet")
    publisher.sync_once(client)
    assert publisher.report.now_playing == "planet"

    central.update("desk", single_app=None)
    assert "single_app" not in build_state("desk").payload()
    wake.clear()
    publisher.sync_once(client)
    assert wake.is_set()
    assert local.get("desk")["single_app"] is None

    # The player's authoritative state and files survive a controller outage.
    shutil.rmtree(central_outputs)
    assert DeviceDatabase(tmp_path / "local.db").get("desk")["brightness"] == 32
    with Image.open(node_outputs / "planet.webp") as cached:
        assert cached.size == (64, 64)
