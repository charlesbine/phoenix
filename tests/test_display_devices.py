"""Device-scoped DisplayManager — rotation resolution and cheap mirror follow.

Exercises the manager's per-device logic directly (no real backend/hardware):
_collect_active overlays device_apps membership on the global app defs, and
_mirror_tick shows whatever the target device last displayed.
"""

from pathlib import Path

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
