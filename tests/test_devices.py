"""Per-device data model — devices, rotation membership, and the safe seed."""

from phoenix.db import AppDatabase, ConfigDatabase, DeviceDatabase, seed_default_device


def test_device_crud_and_membership(tmp_path):
    db = str(tmp_path / "t.db")
    ddb = DeviceDatabase(db)
    assert ddb.list_devices() == []

    d = ddb.create("apollo", "Apollo Panel", "wled", brightness=200)
    assert d["id"] == "apollo" and d["backend"] == "wled" and d["brightness"] == 200

    ddb.update("apollo", brightness=64, mirror_of="main")
    dev = ddb.get("apollo")
    assert dev["brightness"] == 64 and dev["mirror_of"] == "main"

    # per-device rotation membership
    for i, name in enumerate(["clock", "weather", "spotify"]):
        ddb.set_app("apollo", name, enabled=(name != "weather"), sort_order=i)
    members = ddb.list_apps("apollo")
    assert [m["app_name"] for m in members] == ["clock", "weather", "spotify"]
    assert {m["app_name"]: m["enabled"] for m in members}["weather"] == 0

    ddb.reorder("apollo", ["spotify", "clock", "weather"])
    assert [m["app_name"] for m in ddb.list_apps("apollo")] == ["spotify", "clock", "weather"]

    ddb.set_app("apollo", "weather", enabled=True)  # toggle existing
    assert {m["app_name"]: m["enabled"] for m in ddb.list_apps("apollo")}["weather"] == 1

    ddb.remove_app("apollo", "clock")
    assert "clock" not in [m["app_name"] for m in ddb.list_apps("apollo")]

    ddb.delete("apollo")
    assert ddb.get("apollo") is None
    assert ddb.list_apps("apollo") == []


def test_seed_migrates_existing_single_device_state(tmp_path):
    db = str(tmp_path / "seed.db")
    adb = AppDatabase(db)
    adb.upsert("clock", priority=2, sort_order=0)
    adb.upsert("weather", enabled=False, sort_order=1)
    ConfigDatabase(db).update(brightness=77, layout_mode="random")

    seeded = seed_default_device("main", "Main", "serial", path=db)
    assert seeded == "main"

    ddb = DeviceDatabase(db)
    dev = ddb.get("main")
    assert dev["backend"] == "serial"
    assert dev["brightness"] == 77
    assert dev["layout_mode"] == "random"

    members = {m["app_name"]: m for m in ddb.list_apps("main")}
    assert set(members) == {"clock", "weather"}
    assert members["clock"]["priority"] == 2
    assert members["weather"]["enabled"] == 0

    # idempotent — running again is a no-op
    assert seed_default_device(path=db) is None


def test_seed_fresh_db_populates_curated_starter_apps(tmp_path):
    db = str(tmp_path / "fresh.db")
    seeded = seed_default_device("main", "Main", "web", path=db)
    assert seeded == "main"

    ddb = DeviceDatabase(db)
    members = [m["app_name"] for m in ddb.list_apps("main")]
    assert members == [
        "procedural_landscape",
        "procedural_planet",
        "gradient_clock",
        "day_night_map",
        "life",
        "aquarium",
    ]
    assert "nyan_cat" not in members
