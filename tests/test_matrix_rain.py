from datetime import datetime, timedelta
from threading import Event
from zoneinfo import ZoneInfo

import pytest

from phoenix.db import AppDatabase, DeviceDatabase
from phoenix.display.manager import DisplayManager
from phoenix.procedural.matrix_rain import MatrixRain


def test_changed_digit_cycles_whole_glyphs_and_locks_on_the_minute():
    now = datetime(2026, 11, 28, 12, 35, tzinfo=ZoneInfo("America/New_York"))
    rain = MatrixRain()

    def face(seconds):
        return rain.frame(9.0, now + timedelta(seconds=seconds))

    before = face(-3)
    tick0, same_tick, tick1 = face(-2.2), face(-2.15), face(-2.12)
    after = face(0)
    for image in (tick0, same_tick, tick1, after):
        assert image.crop((4, 20, 47, 43)).tobytes() == before.crop((4, 20, 47, 43)).tobytes()
    slot = (48, 20, 60, 43)
    assert tick0.crop(slot).tobytes() == same_tick.crop(slot).tobytes()
    assert len({im.crop(slot).tobytes() for im in (before, tick0, tick1, after)}) == 4
    assert after.crop(slot).tobytes() == face(20).crop(slot).tobytes()
    # A decoding plate contains only the code glyph, with no numeral behind it.
    assert {color for count, color in tick0.crop(slot).getcolors()} == {(0, 0, 0), (199, 255, 207)}


def test_only_rain_streams_under_changing_digits_accelerate():
    rain = MatrixRain()
    start = datetime(2026, 11, 28, 12, 34, 57, tzinfo=ZoneInfo("UTC"))
    for step in range(31):
        t = step / 10
        clock = rain.frame(t, start + timedelta(seconds=t))
    plain = rain.frame(t)
    assert plain.tobytes() == MatrixRain().frame(t).tobytes()
    assert plain.tobytes() != rain.frame(t + 1).tobytes()
    assert plain.crop((0, 0, 48, 19)).tobytes() == clock.crop((0, 0, 48, 19)).tobytes()
    assert plain.crop((48, 0, 60, 19)).tobytes() != clock.crop((48, 0, 60, 19)).tobytes()


def test_decode_targets_the_actual_dst_jump():
    rain = MatrixRain()
    zone = ZoneInfo("America/New_York")
    just_before_jump = datetime(2026, 11, 1, 1, 59, 59, tzinfo=zone, fold=0)
    # In the repeated hour 01:59 becomes 01:00, so the hour stays still.
    hour = (4, 20, 29, 43)
    minutes = (35, 20, 60, 43)
    during = rain.frame(0, just_before_jump)
    at_jump = datetime.fromtimestamp(just_before_jump.timestamp() + 1, zone)
    settled = rain.frame(0, at_jump)
    assert during.crop(hour).tobytes() == settled.crop(hour).tobytes()
    assert (199, 255, 207) in {color for _, color in during.crop(minutes).getcolors()}


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
