import pytest

from phoenix.db import AppDatabase, ConfigDatabase
from phoenix.service import PhoenixService
from phoenix.settings import Settings


@pytest.fixture
def svc(tmp_path):
    return PhoenixService(
        settings=Settings(),
        app_db=AppDatabase(tmp_path / "test.db"),
        config_db=ConfigDatabase(tmp_path / "test.db"),
    )


class TestAppManagement:
    def test_create_and_list(self, svc):
        svc.create_app("clock")
        apps = svc.list_apps()
        user_apps = [app for app in apps if app.source != "builtin"]
        assert len(user_apps) == 1
        assert user_apps[0].name == "clock"

    def test_get_app(self, svc):
        svc.create_app("clock")
        app = svc.get_app("clock")
        assert app.name == "clock"

    def test_get_nonexistent_raises(self, svc):
        with pytest.raises(ValueError):
            svc.get_app("nonexistent")

    def test_enable_disable(self, svc):
        svc.create_app("clock", enabled=True)
        svc.disable_app("clock")
        assert svc.get_app("clock").enabled is False
        svc.enable_app("clock")
        assert svc.get_app("clock").enabled is True

    def test_set_active(self, svc):
        svc.create_app("clock")
        svc.set_active("clock", False)
        assert svc.get_app("clock").active is False

    def test_create_with_pixlet_config(self, svc):
        svc.create_app("clock", pixlet_config={"timezone": "America/New_York"})
        app = svc.get_app("clock")
        assert app.pixlet_config == {"timezone": "America/New_York"}


class TestDisplayConfig:
    def test_get_default(self, svc):
        cfg = svc.get_display_config()
        assert cfg.layout_mode == "cycle"

    def test_update(self, svc):
        svc.update_display_config(layout_mode="random")
        cfg = svc.get_display_config()
        assert cfg.layout_mode == "random"
