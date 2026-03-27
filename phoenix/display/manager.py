"""Display manager — picks which apps to show and delegates to a backend."""

import json
import logging
import random
import time

from phoenix.db import AppDatabase, ConfigDatabase, PlaylistDatabase
from phoenix.display.backend import DisplayBackend
from phoenix.models import AppConfig
from phoenix.mqtt import pop_notification
from phoenix.paths import DATA_DIR, OUTPUTS_DIR, output_path, star_path, ensure_dirs
from phoenix.settings import Settings

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
            # Check for notifications before each cycle
            self._check_notifications()

            # If brightness is 0, display is "off" — skip rendering
            config = self.config_db.get()
            if config.brightness == 0:
                time.sleep(1)
                continue

            apps = self.app_db.list_apps()
            active = [a for a in apps if a.enabled and a.active]

            # Apply schedule: if a playlist is active, filter to its apps
            try:
                playlist_db = PlaylistDatabase()
                active_playlist = playlist_db.get_active_playlist()
                if active_playlist:
                    allowed = set(active_playlist["app_names"])
                    scheduled = [a for a in active if a.name in allowed]
                    if scheduled:
                        active = scheduled
                        logger.debug("Schedule active: %s (%s)", active_playlist["name"],
                                     [a.name for a in active])
            except Exception:
                pass  # Schedule is optional, don't break display if DB issue

            if not active:
                logger.warning("No active apps, waiting %ds...", NO_APPS_WAIT)
                self.backend.clear()
                time.sleep(NO_APPS_WAIT)
                continue

            # Don't skip stale apps — show them anyway. Better stale content than black screen.
            # The renderer will update them when it gets to them.

            config = self.config_db.get()
            logger.debug("Display mode: %s, active: %s", config.layout_mode, [a.name for a in active])

            if config.layout_mode == "cycle":
                active.sort(key=lambda a: a.sort_order)
                weighted = self._weighted_list(active)
                self._display_cycle(weighted, config.cycle_interval)
            elif config.layout_mode == "random":
                weighted = self._weighted_list(active)
                random.shuffle(weighted)
                self._display_cycle(weighted, config.cycle_interval)
            elif config.layout_mode == "single":
                self._display_app(active[0], config.cycle_interval)
            else:
                logger.error("Unknown layout mode: %s", config.layout_mode)

    @staticmethod
    def _weighted_list(apps: list[AppConfig]) -> list[AppConfig]:
        """Expand the app list based on priority. Priority 0 = 1 slot, 1 = 2 slots, etc.

        Interleaves high-priority apps evenly rather than bunching them together.
        E.g., [A(p=2), B(p=0), C(p=0)] → [A, B, A, C, A]
        """
        if not apps:
            return []

        max_priority = max(a.priority for a in apps)
        if max_priority <= 0:
            return list(apps)

        # Build slot counts: priority 0 = 1, priority 1 = 2, etc.
        slots: list[tuple[AppConfig, int]] = [(a, max(1, a.priority + 1)) for a in apps]

        # Interleave: round-robin through apps, each gets shown once per round,
        # high-priority apps get extra rounds
        result: list[AppConfig] = []
        remaining = {i: count for i, (_, count) in enumerate(slots)}
        while any(v > 0 for v in remaining.values()):
            for i, (app, _) in enumerate(slots):
                if remaining[i] > 0:
                    result.append(app)
                    remaining[i] -= 1

        return result

    def _display_cycle(self, apps: list[AppConfig], duration: int) -> None:
        for app in apps:
            # Check for notifications between each app
            self._check_notifications()
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

        logger.info("Displaying %s for %ds", fresh.name, duration)
        self.backend.display_image(path, duration)

    def _check_notifications(self) -> None:
        """Check for pending notifications and display them."""
        while True:
            notif = pop_notification()
            if notif is None:
                return
            self._display_notification(notif)

    def _display_notification(self, notif: dict) -> None:
        """Render and display a notification."""
        logger.info("[notify] Displaying: %s (duration=%ds)", notif["text"][:60], notif["duration"])

        # Write notification data as panel JSON
        ensure_dirs()
        panel_data = {
            "layout": notif.get("layout", "marquee"),
            "title": "",
            "text": notif["text"],
            "color": notif.get("color", "#FFFFFF"),
        }
        data_file = DATA_DIR / "dashboard_panel__notification.json"
        data_file.write_text(json.dumps(panel_data))

        # Render via pixlet using the dashboard_panel template
        try:
            from phoenix.render import _run_pixlet
            from phoenix.models import AppConfig as AC

            app = AC(name="panel__notification", pixlet_config={"instance_id": "_notification"})
            _run_pixlet(app, Settings(), large=False, star_override=star_path("dashboard_panel"))

            notif_output = output_path("panel__notification")
            if notif_output.exists():
                self.backend.display_image(notif_output, notif["duration"])
        except Exception:
            logger.exception("[notify] Failed to render notification")
