"""Renderer renders the union of globally-enabled apps and per-device rotations.

An app that's off globally but enabled on a panel must still be rendered so
that panel has fresh output; an app off everywhere is skipped.
"""

import pytest

from phoenix.db import AppDatabase, DeviceDatabase
from phoenix.render import _device_enabled_names, run_app
from phoenix.settings import Settings


def test_enabled_app_names_only_counts_enabled_devices_and_members(tmp_path):
    db = str(tmp_path / "r.db")
    adb = AppDatabase(db)
    for n in ["clock", "weather", "spotify", "news"]:
        adb.upsert(n)

    ddb = DeviceDatabase(db)
    ddb.create("m4", "M4", "serial")
    ddb.create("apollo", "Apollo", "wled")
    ddb.create("spare", "Spare", "web", enabled=0)  # a device that isn't driven

    ddb.set_app("m4", "clock", enabled=True)
    ddb.set_app("m4", "weather", enabled=False)   # membership disabled
    ddb.set_app("apollo", "spotify", enabled=True)
    ddb.set_app("spare", "news", enabled=True)     # but the device is disabled

    # Only apps enabled on an *enabled* device count.
    assert ddb.enabled_app_names() == {"clock", "spotify"}
    assert _device_enabled_names(adb) == {"clock", "spotify"}


def test_run_app_renders_globally_disabled_but_panel_enabled(tmp_path):
    db = str(tmp_path / "r.db")
    adb = AppDatabase(db)
    ddb = DeviceDatabase(db)
    ddb.create("m4", "M4", "serial")

    adb.upsert("zztest_on_panel", enabled=False)   # off globally...
    ddb.set_app("m4", "zztest_on_panel", enabled=True)  # ...but on a panel
    adb.upsert("zztest_ghost", enabled=False)      # off everywhere

    # Off everywhere → silently skipped (returns None, no render attempt).
    assert run_app("zztest_ghost", Settings(), adb) is None

    # On a panel → guard passes; with no app file it raises rather than skipping.
    with pytest.raises(ValueError, match="No app file"):
        run_app("zztest_on_panel", Settings(), adb)
