from datetime import datetime, timedelta
from threading import Event
from zoneinfo import ZoneInfo

import pytest

from phoenix.db import AppDatabase, DeviceDatabase
from phoenix.display.manager import DisplayManager
from phoenix.procedural.matrix_rain import MatrixRain


def test_rain_animates_and_clock_keeps_unchanged_digits_stationary():
    rain = MatrixRain()
    now = datetime(2026, 11, 28, 12, 35, tzinfo=ZoneInfo("America/New_York"))
    before = rain.frame(8.5, now - timedelta(seconds=1))
    during = rain.frame(8.5, now.replace(microsecond=350000))
    after = rain.frame(8.5, now.replace(second=1))
    plain = rain.frame(8.5)
    assert plain.size == (64, 64)
    assert plain.tobytes() != rain.frame(9.5).tobytes()
    assert plain.crop((0, 0, 64, 18)).tobytes() == after.crop((0, 0, 64, 18)).tobytes()
    assert before.crop((0, 0, 48, 64)).tobytes() == during.crop((0, 0, 48, 64)).tobytes()
    assert len({im.crop((48, 20, 60, 43)).tobytes() for im in (before, during, after, plain)}) == 4


@pytest.mark.parametrize("name", ["matrix_clock", "matrix_rain"])
def test_player_streams_builtin_without_cached_artwork(tmp_path, monkeypatch, name):
    apps = AppDatabase(tmp_path / "test.db")
    devices = DeviceDatabase(apps.path)
    devices.create("desk", "Desk", "wled")
    devices.set_app("desk", name)
    wake = Event()
    frames = []

    class Sink:
        def send_frame(self, rgb):
            frames.append(rgb)
            wake.set()
            return True

        def set_brightness(self, level):
            assert level > 0

        def clear(self):
            pass

        def close(self):
            pass

    dm = DisplayManager(Sink(), app_db=apps, device_db=devices, device_id="desk", wake=wake)
    monkeypatch.setattr(dm, "_pending_notification", lambda: False)
    monkeypatch.setattr(dm, "_write_now_playing", lambda playing: None)
    previews = []
    monkeypatch.setattr(dm, "_save_preview", previews.append)
    app, = dm._collect_active()
    assert app.name == name and app.runtime == "live_matrix"
    dm._display_app(app, 30)
    assert previews == frames and len(frames) == 1 and len(frames[0]) == 64 * 64 * 3
