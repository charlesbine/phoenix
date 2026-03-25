"""Service layer — all business logic lives here. Both the CLI and dashboard call into this."""

from phoenix.db import AppDatabase, ConfigDatabase
from phoenix.models import AppConfig, DisplayConfig
from phoenix.settings import Settings


class PhoenixService:
    def __init__(
        self,
        settings: Settings | None = None,
        app_db: AppDatabase | None = None,
        config_db: ConfigDatabase | None = None,
    ):
        self.settings = settings or Settings()
        self.app_db = app_db or AppDatabase()
        self.config_db = config_db or ConfigDatabase()

    # -- App management --

    def list_apps(self) -> list[AppConfig]:
        return self.app_db.list_apps()

    def get_app(self, name: str) -> AppConfig:
        app = self.app_db.get(name)
        if app is None:
            raise ValueError(f"App '{name}' not found")
        return app

    def create_app(
        self,
        name: str,
        enabled: bool = True,
        pixlet_config: dict[str, str] | None = None,
        **kwargs: object,
    ) -> AppConfig:
        return self.app_db.create(name, enabled=enabled, pixlet_config=pixlet_config or {}, **kwargs)

    def enable_app(self, name: str) -> AppConfig:
        return self.app_db.upsert(name, enabled=True)

    def disable_app(self, name: str) -> AppConfig:
        return self.app_db.upsert(name, enabled=False)

    def set_active(self, name: str, active: bool) -> AppConfig:
        return self.app_db.upsert(name, active=active)

    # -- Display config --

    def get_display_config(self) -> DisplayConfig:
        return self.config_db.get()

    def update_display_config(self, **kwargs: object) -> DisplayConfig:
        return self.config_db.update(**kwargs)

    # -- Rendering (delegates to render module) --

    def render_app(self, name: str) -> None:
        from phoenix.render import run_app

        run_app(name, self.settings, self.app_db)

    def render_preview(self, name: str) -> None:
        from phoenix.render import render_preview

        render_preview(name, self.settings)

    def render_all(self) -> None:
        from phoenix.render import run_all_apps

        run_all_apps(self.settings, self.app_db)
