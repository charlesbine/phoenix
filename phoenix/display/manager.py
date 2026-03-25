"""Display manager — picks which apps to show and delegates to a backend."""

import logging
import random
import time

from phoenix.db import AppDatabase, ConfigDatabase
from phoenix.display.backend import DisplayBackend
from phoenix.models import AppConfig
from phoenix.paths import output_path

logger = logging.getLogger(__name__)

ALL_APPS_STALE_WAIT = 1  # seconds to wait when all apps are stale
NO_APPS_WAIT = 5  # seconds to wait when no active apps found


class DisplayManager:
    def __init__(
        self,
        backend: DisplayBackend,
        app_db: AppDatabase | None = None,
        config_db: ConfigDatabase | None = None,
        debug_mode: bool = False,
    ):
        self.backend = backend
        self.app_db = app_db or AppDatabase()
        self.config_db = config_db or ConfigDatabase()
        self.debug_mode = debug_mode

    def run(self) -> None:
        """Main display loop."""
        while True:
            apps = self.app_db.list_apps()
            active = [a for a in apps if a.enabled and a.active]

            if not active:
                logger.warning("No active apps, waiting %ds...", NO_APPS_WAIT)
                self.backend.clear()
                time.sleep(NO_APPS_WAIT)
                continue

            if all(a.is_stale() for a in active):
                logger.warning("All apps stale, waiting %ds...", ALL_APPS_STALE_WAIT)
                self.backend.clear()
                time.sleep(ALL_APPS_STALE_WAIT)
                continue

            config = self.config_db.get()
            logger.debug("Display mode: %s, active: %s", config.layout_mode, [a.name for a in active])

            if config.layout_mode == "cycle":
                self._display_cycle(active, config.cycle_interval)
            elif config.layout_mode == "random":
                shuffled = active.copy()
                random.shuffle(shuffled)
                self._display_cycle(shuffled, config.cycle_interval)
            elif config.layout_mode == "single":
                self._display_app(active[0], config.cycle_interval)
            else:
                logger.error("Unknown layout mode: %s", config.layout_mode)

    def _display_cycle(self, apps: list[AppConfig], duration: int) -> None:
        for app in apps:
            self._display_app(app, duration)

    def _display_app(self, app: AppConfig, duration: int) -> None:
        # Re-read from DB for fresh state
        fresh = self.app_db.get(app.name)
        if fresh is None:
            return

        path = output_path(fresh.name)
        if not path.exists():
            logger.warning("[%s] Output not found: %s", fresh.name, path)
            return

        if fresh.is_stale():
            logger.debug("[%s] Stale (last updated: %s), skipping", fresh.name, fresh.last_updated)
            return

        logger.info("Displaying %s for %ds", fresh.name, duration)
        self.backend.display_image(path, duration)
