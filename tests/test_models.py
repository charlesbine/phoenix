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
