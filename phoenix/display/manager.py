"""Display manager — picks which apps to show and delegates to a backend."""

import json
import logging
import random
import time

from phoenix.db import AppDatabase, ConfigDatabase, DeviceDatabase, PlaylistDatabase
from phoenix.display.backend import DisplayBackend
from phoenix.models import AppConfig
from phoenix.mqtt import pop_notification
from phoenix.paths import (
    DATA_DIR,
    current_app_file,
    ensure_dirs,
    output_path,
    star_path,
)
from phoenix.settings import Settings

logger = logging.getLogger(__name__)

ALL_APPS_STALE_WAIT = 1  # seconds to wait when all apps are stale
NO_APPS_WAIT = 5  # seconds to wait when no active apps found
MIRROR_SLICE = 2  # seconds a mirror shows one frame before re-checking its target


class DisplayManager:
    """Drives one panel.

    Global mode (device_id=None) preserves the original single-panel behavior:
    config + rotation come from the shared display_config / apps tables.

    Device mode (device_id set) scopes everything to one row of ``devices`` —
    its own brightness/layout/interval and its own ``device_apps`` rotation.
    A device with ``mirror_of`` set runs no rotation of its own; it just shows
    whatever its target is currently showing (cheap mirroring).
    """

    def __init__(
        self,
        backend: DisplayBackend,
        app_db: AppDatabase | None = None,
        config_db: ConfigDatabase | None = None,
        device_id: str | None = None,
        device_db: DeviceDatabase | None = None,
        primary: bool = True,
        debug_mode: bool = False,
    ):
        self.backend = backend
        self.app_db = app_db or AppDatabase()
        self.config_db = config_db or ConfigDatabase()
        self.device_id = device_id
        self.device_db = device_db or DeviceDatabase()
        # Only the primary loop consumes the shared notification queue, so a
        # notification isn't raced away onto a random panel.
        self.primary = primary
        self.debug_mode = debug_mode

    def run(self) -> None:
        """Main display loop."""
        while True:
            if self.primary:
                self._check_notifications()

            # Resolve this iteration's brightness / layout / interval, either
            # from the device row or the global config.
            if self.device_id:
                dev = self.device_db.get(self.device_id)
                if dev is None:
                    logger.warning("Device %r vanished, waiting…", self.device_id)
                    time.sleep(NO_APPS_WAIT)
                    continue
                if dev.get("mirror_of"):
                    self._mirror_tick(dev["mirror_of"])
                    continue
                brightness = dev["brightness"]
                layout_mode = dev["layout_mode"]
                cycle_interval = dev["cycle_interval"]
            else:
                config = self.config_db.get()
                brightness = config.brightness
                layout_mode = config.layout_mode
                cycle_interval = config.cycle_interval

            # If brightness is 0, display is "off" — skip rendering
            if brightness == 0:
                time.sleep(1)
                continue

            active = self._collect_active()

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

            logger.debug("Display mode: %s, active: %s", layout_mode, [a.name for a in active])

            if layout_mode == "cycle":
                active.sort(key=lambda a: a.sort_order)
                self._display_cycle(self._weighted_list(active), cycle_interval)
            elif layout_mode == "random":
                weighted = self._weighted_list(active)
                random.shuffle(weighted)
                self._display_cycle(weighted, cycle_interval)
            elif layout_mode == "single":
                self._display_app(active[0], cycle_interval)
            else:
                logger.error("Unknown layout mode: %s", layout_mode)

    def _collect_active(self) -> list[AppConfig]:
        """The apps eligible to show right now — global rotation, or this
        device's rotation membership overlaid on the global app definitions."""
        if not self.device_id:
            return [a for a in self.app_db.list_apps() if a.enabled and a.active]

        active: list[AppConfig] = []
        for member in self.device_db.list_apps(self.device_id):
            if not member["enabled"]:
                continue
            app = self.app_db.get(member["app_name"])
            if app is None or not app.active:
                continue
            # Per-device priority / order override the global values.
            active.append(app.model_copy(update={
                "priority": member["priority"],
                "sort_order": member["sort_order"],
            }))
        return active

    def _mirror_tick(self, target_id: str) -> None:
        """Show whatever the target device is currently showing, then return so
        the loop re-checks. Content follows within ~MIRROR_SLICE seconds."""
        sentinel = current_app_file(target_id)
        name = sentinel.read_text().strip() if sentinel.exists() else ""
        if name and output_path(name).exists():
            self.backend.display_image(output_path(name), MIRROR_SLICE)
        else:
            time.sleep(MIRROR_SLICE)

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
            # Check for "show now" override
            show_now = self._check_show_now()
            if show_now:
                self._display_app(show_now, duration)
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

    def _check_show_now(self) -> AppConfig | None:
        """Check if a 'show now' request is pending."""
        show_file = DATA_DIR / "output" / "show_now.txt"
        if not show_file.exists():
            return None
        try:
            name = show_file.read_text().strip()
            show_file.unlink()
            if name:
                app = self.app_db.get(name)
                if app and output_path(name).exists():
                    logger.info("[show_now] Jumping to %s", name)
                    return app
        except Exception:
            pass
        return None

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
