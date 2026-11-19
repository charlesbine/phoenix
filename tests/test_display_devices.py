"""Device-scoped DisplayManager — rotation resolution and cheap mirror follow.

Exercises the manager's per-device logic directly (no real backend/hardware):
_collect_active overlays device_apps membership on the global app defs, and
_mirror_tick shows whatever the target device last displayed.
"""

from pathlib import Path

import pytest

from phoenix.db import AppDatabase, ConfigDatabase, DeviceDatabase
from phoenix.display import manager as manager_mod
from phoenix.display.manager import MIRROR_SLICE, DisplayManager


class FakeBackend:
    """Records what it was asked to show."""

    def __init__(self) -> None:
        self.shown: list[tuple[Path, int]] = []
        self.cleared = 0

    def display_image(self, image_path: Path, duration: int) -> None:
        self.shown.append((image_path, duration))

    def clear(self) -> None:
        self.cleared += 1


def _seed_apps(db: str) -> AppDatabase:
    adb = AppDatabase(db)
    adb.upsert("clock", priority=0, sort_order=5, active=True)
    adb.upsert("weather", priority=0, sort_order=1, active=True)
    adb.upsert("spotify", priority=0, sort_order=2, active=True)
    adb.upsert("news", priority=0, sort_order=3, active=False)  # rendered-stale/inactive
    return adb


def test_collect_active_uses_device_membership_and_overrides(tmp_path):
    db = str(tmp_path / "t.db")
    adb = _seed_apps(db)
    ddb = DeviceDatabase(db)
    ddb.create("apollo", "Apollo", "wled")

    # apollo shows clock (bumped priority), spotify, and news (which is inactive
    # globally so must be filtered). weather is not a member → excluded.
    ddb.set_app("apollo", "clock", enabled=True, priority=2, sort_order=9)
    ddb.set_app("apollo", "spotify", enabled=True, priority=0, sort_order=0)
    ddb.set_app("apollo", "news", enabled=True)
    ddb.set_app("apollo", "weather", enabled=False)  # member but disabled here

    dm = DisplayManager(FakeBackend(), app_db=adb, device_id="apollo", device_db=ddb)
    active = dm._collect_active()

    names = {a.name for a in active}
    assert names == {"clock", "spotify"}  # weather disabled, news inactive, weather excluded
    clock = next(a for a in active if a.name == "clock")
    assert clock.priority == 2 and clock.sort_order == 9  # per-device overrides win


def test_collect_active_includes_db_backed_live_apps(tmp_path):
    db = str(tmp_path / "t.db")
    adb = _seed_apps(db)
    ddb = DeviceDatabase(db)
    ddb.create("apollo", "Apollo", "wled")
    ddb.set_app("apollo", "audio_vu", enabled=True, priority=1, sort_order=0)

    dm = DisplayManager(FakeBackend(), app_db=adb, device_id="apollo", device_db=ddb)
    active = dm._collect_active()

    assert [a.name for a in active] == ["audio_vu"]
    assert active[0].runtime == "live_audio"
    assert active[0].pixlet_config["mode"] == "vu"


@pytest.mark.parametrize(
    ("pin", "show_now", "expected"),
    [("weather", None, "weather"), ("news", None, "clock"), ("weather", "spotify", "spotify")],
)
def test_single_mode_uses_selected_app_with_fallback_and_show_now(
    tmp_path, monkeypatch, pin, show_now, expected,
):
    db = str(tmp_path / "t.db")
    adb = _seed_apps(db)
    ddb = DeviceDatabase(db)
    ddb.create("desk", "Desk", "web", layout_mode="single", single_app=pin)
    for idx, name in enumerate(("clock", "weather", "spotify", "news")):
        ddb.set_app("desk", name, enabled=True, sort_order=idx)

    dm = DisplayManager(FakeBackend(), app_db=adb, device_id="desk", device_db=ddb)
    monkeypatch.setattr(dm, "_check_show_now", lambda: adb.get(show_now) if show_now else None)
    monkeypatch.setattr(dm, "_check_notifications", lambda: None)
    monkeypatch.setattr(manager_mod, "PlaylistDatabase", lambda: type(
        "Playlist", (), {"get_active_playlist": lambda self: {"name": "Scheduled", "app_names": ["clock"]}},
    )())

    class Played(Exception):
        pass

    def display(app, interval):
        assert app.name == expected
        raise Played

    monkeypatch.setattr(dm, "_display_app", display)
    with pytest.raises(Played):
        dm.run()


def test_spectrogram_bar_width_controls_live_band_count():
    assert manager_mod._audio_band_count("spectrogram", {"bar_width": "2"}) == 32
    assert manager_mod._audio_band_count("spectrogram", {"bar_width": "1"}) == 64
    assert manager_mod._audio_band_count("spectrogram", {"bar_width": "3"}) == 32
    assert manager_mod._audio_band_count("bars", {"bar_width": "2", "bar_spacing": "solid"}) == 32
    assert manager_mod._audio_band_count("bars", {"bar_width": "2", "bar_spacing": "separated"}) == 21


def test_audio_analyzer_kwargs_are_db_configurable_without_frequency_shift():
    bars = manager_mod._analyzer_kwargs("bars", {"floor_db": "-50", "noise_gate": "0.12"})
    spectrogram = manager_mod._analyzer_kwargs("spectrogram", {})

    assert bars["floor_db"] == -50.0
    assert bars["noise_gate"] == 0.12
    assert spectrogram["floor_db"] == -66.0
    assert spectrogram["noise_gate"] == 0.02
    assert spectrogram["tilt"] == 4.5
    assert spectrogram["gain_db"] == 10.0
    assert spectrogram["onset_boost"] == 1.4


def test_global_mode_ignores_devices(tmp_path):
    db = str(tmp_path / "t.db")
    adb = _seed_apps(db)
    adb.upsert("weather", enabled=False)  # globally disabled

    dm = DisplayManager(
        FakeBackend(),
        app_db=adb,
        config_db=ConfigDatabase(db),
        device_db=DeviceDatabase(db),
        device_id=None,
    )
    names = {a.name for a in dm._collect_active()}
    # global rotation = enabled AND active: clock + spotify (weather off, news inactive)
    assert names == {"clock", "spotify"}


def test_mirror_tick_follows_target_sentinel(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    adb = _seed_apps(db)
    ddb = DeviceDatabase(db)

    # Redirect the sentinel + output lookups into tmp so we touch no real files.
    sentinel = tmp_path / "current_app__main.txt"
    sentinel.write_text("clock")
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "clock.webp").write_bytes(b"webp")

    monkeypatch.setattr(manager_mod, "current_app_file", lambda dev=None: sentinel)
    monkeypatch.setattr(manager_mod, "output_path", lambda name: outputs / f"{name}.webp")

    backend = FakeBackend()
    dm = DisplayManager(backend, app_db=adb, device_id="mirror", device_db=ddb)
    dm._mirror_tick("main")

    assert backend.shown == [(outputs / "clock.webp", MIRROR_SLICE)]


def test_mirror_tick_waits_when_target_idle(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    adb = _seed_apps(db)
    missing = tmp_path / "nope.txt"  # target hasn't shown anything yet
    monkeypatch.setattr(manager_mod, "current_app_file", lambda dev=None: missing)
    monkeypatch.setattr(manager_mod, "time", type("T", (), {"sleep": staticmethod(lambda s: None)}))

    backend = FakeBackend()
    dm = DisplayManager(backend, app_db=adb, device_id="mirror", device_db=DeviceDatabase(db))
    dm._mirror_tick("main")

    assert backend.shown == []  # nothing to mirror yet


def test_empty_rotation_clears_per_device_display_state(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    adb = _seed_apps(db)
    ddb = DeviceDatabase(db)
    ddb.create("apollo", "Apollo", "wled")

    data_dir = tmp_path / "data"
    monkeypatch.setattr(manager_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(manager_mod, "current_app_file", lambda dev=None: data_dir / "output" / f"current_app__{dev}.txt")
    monkeypatch.setattr(manager_mod, "current_display_file", lambda dev=None: data_dir / "output" / f"current_display__{dev}.webp")

    backend = FakeBackend()
    dm = DisplayManager(backend, app_db=adb, device_id="apollo", device_db=ddb)
    dm._clear_display_state()

    assert backend.cleared == 1
    assert (data_dir / "output" / "current_app.txt").read_text() == ""
    assert (data_dir / "output" / "current_app__apollo.txt").read_text() == ""
    assert (data_dir / "output" / "current_display__apollo.webp").exists()


def test_legacy_content_mode_does_not_bypass_empty_rotation(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    adb = _seed_apps(db)
    ddb = DeviceDatabase(db)
    ddb.create("apollo", "Apollo", "wled", content_mode="nowplaying")

    data_dir = tmp_path / "data"
    monkeypatch.setattr(manager_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(manager_mod, "current_app_file", lambda dev=None: data_dir / "output" / f"current_app__{dev}.txt")
    monkeypatch.setattr(manager_mod, "current_display_file", lambda dev=None: data_dir / "output" / f"current_display__{dev}.webp")

    class StopLoop(Exception):
        pass

    monkeypatch.setattr(manager_mod.time, "sleep", lambda _seconds: (_ for _ in ()).throw(StopLoop()))

    backend = FakeBackend()
    dm = DisplayManager(backend, app_db=adb, device_id="apollo", device_db=ddb)
    with pytest.raises(StopLoop):
        dm.run()

    assert backend.cleared == 1
    assert (data_dir / "output" / "current_app__apollo.txt").read_text() == ""


def test_show_now_accepts_live_app_without_rendered_output(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    adb = _seed_apps(db)
    show_file = tmp_path / "show_now__apollo.txt"
    show_file.write_text("nowplaying")

    monkeypatch.setattr(manager_mod, "show_now_file", lambda dev=None: show_file)

    dm = DisplayManager(FakeBackend(), app_db=adb, device_id="apollo", device_db=DeviceDatabase(db))
    app = dm._check_show_now()

    assert app is not None
    assert app.name == "nowplaying"
    assert app.runtime == "live_nowplaying"
