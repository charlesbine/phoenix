from datetime import datetime, timedelta

from phoenix.models import AppConfig, AppStatus, DisplayConfig, PreprocessorResult


def test_app_config_defaults():
    app = AppConfig(name="test")
    assert app.enabled is True
    assert app.active is True
    assert app.refresh_interval == timedelta(minutes=1)
    assert app.last_updated is None
    assert app.pixlet_config == {}
    assert app.priority == 0


def test_app_config_is_stale_when_never_updated():
    app = AppConfig(name="test")
    assert app.is_stale() is True


def test_app_config_is_stale_when_old():
    app = AppConfig(name="test", last_updated=datetime.now() - timedelta(hours=1))
    assert app.is_stale() is True


def test_app_config_is_not_stale_when_fresh():
    app = AppConfig(name="test", last_updated=datetime.now())
    assert app.is_stale() is False


def test_app_config_seconds_until_refresh():
    app = AppConfig(name="test", last_updated=datetime.now())
    assert app.seconds_until_refresh() > 0

    stale = AppConfig(name="test", last_updated=datetime.now() - timedelta(hours=1))
    assert stale.seconds_until_refresh() == 0.0


def test_display_config_defaults():
    cfg = DisplayConfig()
    assert cfg.layout_mode == "cycle"
    assert cfg.cycle_interval == 10


def test_preprocessor_result_defaults():
    r = PreprocessorResult(data={"key": "value"})
    assert r.status == AppStatus.NORMAL
    assert r.priority == 0


def test_app_status_values():
    assert AppStatus.NORMAL == "normal"
    assert AppStatus.SKIP == "skip"
    assert AppStatus.DISABLE == "disable"
    assert AppStatus.PRIORITIZE == "prioritize"
    assert AppStatus.ERROR == "error"


def test_app_config_serialization_roundtrip():
    app = AppConfig(
        name="clock",
        enabled=True,
        refresh_interval=timedelta(seconds=30),
        pixlet_config={"timezone": "America/New_York"},
        priority=5,
    )
    data = app.model_dump(mode="json")
    restored = AppConfig(**data)
    assert restored.name == app.name
    assert restored.pixlet_config == app.pixlet_config
    assert restored.priority == app.priority


def test_night_mode_uses_local_mornings_and_seasonal_daylight():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from phoenix.models import BrightnessSchedule, DisplaySettings

    settings = DisplaySettings(timezone="America/New_York", latitude=40.71, longitude=-74.01)
    schedule = BrightnessSchedule(enabled=True, mode="night")

    def brightness(month, day, hour, minute=0):
        return schedule.level_at(
            settings, 64, datetime(2026, month, day, hour, minute, tzinfo=ZoneInfo(settings.timezone)),
        )

    # Friday night stays dim through 1:59 Saturday; Monday follows the weekday window.
    assert brightness(11, 20, 23, 59) == 16
    assert brightness(11, 21, 1, 59) == 16
    assert brightness(11, 21, 2) == 0
    assert brightness(11, 21, 8, 59) == 0
    assert brightness(11, 21, 9) == 64
    assert brightness(11, 22, 2) == 0
    assert brightness(11, 23, 0) == 0
    assert brightness(11, 23, 7, 59) == 0
    assert brightness(11, 23, 8) == 64

    # At 7 p.m. in New York it is still light in July and dark in November.
    assert brightness(7, 15, 19) == 64
    assert brightness(11, 17, 19) == 16


def test_old_schedule_timezone_migrates_to_global_settings(tmp_path):
    import json
    import sqlite3

    from phoenix.db import DeviceDatabase, _initialized
    from phoenix.models import brightness_schedule_for

    path = tmp_path / "legacy.sqlite"
    db = DeviceDatabase(path)
    db.create("old", "Old", "wled")
    legacy = {"enabled": True, "timezone": "Europe/Paris", "steps": [{"time": "23:00", "brightness": 0}]}
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO device_brightness_schedules VALUES (?, ?)", ("old", json.dumps(legacy)))
    _initialized.discard(str(path))

    db = DeviceDatabase(path)
    saved = db.get("old")
    assert db.get_display_settings().timezone == "Europe/Paris"
    assert "timezone" not in json.loads(saved["brightness_schedule"])
    assert brightness_schedule_for(saved).mode == "custom"
    assert brightness_schedule_for(saved).steps[0].brightness == 0
