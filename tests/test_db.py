from datetime import timedelta

import pytest

from phoenix.db import AppDatabase, ConfigDatabase


@pytest.fixture
def app_db(tmp_path):
    return AppDatabase(tmp_path / "test.db")


@pytest.fixture
def config_db(tmp_path):
    return ConfigDatabase(tmp_path / "test.db")


class TestAppDatabase:
    def test_create_and_get(self, app_db):
        app_db.create("clock")
        app = app_db.get("clock")
        assert app is not None
        assert app.name == "clock"
        assert app.enabled is True

    def test_create_duplicate_raises(self, app_db):
        app_db.create("clock")
        with pytest.raises(ValueError, match="already exists"):
            app_db.create("clock")

    def test_get_nonexistent_returns_none(self, app_db):
        assert app_db.get("nonexistent") is None

    def test_list_apps(self, app_db):
        app_db.create("clock")
        app_db.create("weather")
        apps = app_db.list_apps()
        names = {a.name for a in apps}
        assert {"clock", "weather"}.issubset(names)

    def test_update(self, app_db):
        app_db.create("clock", priority=0)
        app_db.update("clock", priority=10)
        app = app_db.get("clock")
        assert app.priority == 10

    def test_update_nonexistent_raises(self, app_db):
        with pytest.raises(ValueError, match="not found"):
            app_db.update("nonexistent", priority=5)

    def test_upsert_creates_if_new(self, app_db):
        app_db.upsert("clock", enabled=True)
        app = app_db.get("clock")
        assert app is not None
        assert app.name == "clock"

    def test_upsert_updates_if_exists(self, app_db):
        app_db.create("clock", priority=0)
        app_db.upsert("clock", priority=99)
        app = app_db.get("clock")
        assert app.priority == 99

    def test_delete(self, app_db):
        app_db.create("clock")
        app_db.delete("clock")
        assert app_db.get("clock") is None

    def test_refresh_interval_roundtrip(self, app_db):
        app_db.create("clock", refresh_interval=timedelta(seconds=30))
        app = app_db.get("clock")
        assert app.refresh_interval == timedelta(seconds=30)

    def test_builtin_spectrogram_config_is_seeded_and_preserved(self, tmp_path):
        import phoenix.db as db_mod

        path = tmp_path / "builtins.db"
        db = AppDatabase(path)
        bars = db.get("audio_bars")
        assert bars is not None
        assert bars.pixlet_config["bar_width"] == "2"
        assert bars.pixlet_config["bar_spacing"] == "solid"
        assert bars.pixlet_config["floor_db"] == "-55"
        assert bars.pixlet_config["noise_gate"] == "0.08"
        app = db.get("audio_spectrogram")
        assert app is not None
        assert app.pixlet_config["mode"] == "spectrogram"
        assert app.pixlet_config["bar_width"] == "2"
        assert app.pixlet_config["palette"] == "hue"
        assert app.pixlet_config["contrast"] == "high"
        assert app.pixlet_config["floor_db"] == "-62"
        assert app.pixlet_config["noise_gate"] == "0.03"

        db.upsert("audio_spectrogram", pixlet_config={"mode": "spectrogram", "bar_width": "1"})
        db_mod._initialized.discard(str(path))

        app = AppDatabase(path).get("audio_spectrogram")
        assert app is not None
        assert app.pixlet_config["bar_width"] == "1"
        assert app.pixlet_config["palette"] == "hue"


class TestConfigDatabase:
    def test_get_default(self, config_db):
        cfg = config_db.get()
        assert cfg.layout_mode == "cycle"
        assert cfg.cycle_interval == 10

    def test_update(self, config_db):
        config_db.update(layout_mode="random", cycle_interval=20)
        cfg = config_db.get()
        assert cfg.layout_mode == "random"
        assert cfg.cycle_interval == 20

    def test_partial_update(self, config_db):
        config_db.update(cycle_interval=30)
        cfg = config_db.get()
        assert cfg.layout_mode == "cycle"  # unchanged
        assert cfg.cycle_interval == 30
