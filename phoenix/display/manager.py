"""Display manager — picks which apps to show and drives a backend.

The manager owns the *policy* (which app, for how long, per device) and the
per-app bookkeeping (sentinels, brightness, show-now/notification interrupts).
The *mechanics* of putting pixels on a panel live in the backend: streaming
sinks (serial/wled/matrix) go through the shared FramePlayer, while the web
backend just hands its file to the browser.
"""

import json
import logging
import random
import shutil
import time
from pathlib import Path
from threading import Event

from phoenix.db import AppDatabase, ConfigDatabase, DeviceDatabase, PlaylistDatabase
from phoenix.display.backend import DisplayBackend
from phoenix.display.sink import RECONNECT_DELAY, FramePlayer, FrameSink
from phoenix.models import AppConfig, device_brightness
from phoenix.mqtt import pop_notification
from phoenix.paths import (
    DATA_DIR,
    current_app_file,
    current_display_file,
    ensure_dirs,
    output_path,
    show_now_file,
)
from phoenix.procedural.matrix_rain import MatrixRain
from phoenix.settings import Settings, get_settings

logger = logging.getLogger(__name__)

ALL_APPS_STALE_WAIT = 1  # seconds to wait when all apps are stale
NO_APPS_WAIT = 5  # seconds to wait when no active apps found
MIRROR_SLICE = 2  # seconds a mirror shows one frame before re-checking its target

# Live-audio content-mode capture params
AUDIO_SR = 44100
AUDIO_BLOCK = 1024
AUDIO_SIZE = 64
AUDIO_BANDS = 24


def _is_live_runtime(app: AppConfig) -> bool:
    return app.runtime in {"live_audio", "live_nowplaying", "live_matrix"}


def _config_int(config: dict, key: str, default: int) -> int:
    try:
        return int(str(config.get(key, default)))
    except (TypeError, ValueError):
        return default


def _config_float(config: dict, key: str, default: float) -> float:
    try:
        return float(str(config.get(key, default)))
    except (TypeError, ValueError):
        return default


def _spectrogram_bar_width(config: dict, size: int = AUDIO_SIZE) -> int:
    width = _config_int(config, "bar_width", 2)
    return width if width in {1, 2} and size % width == 0 else 2


def _bar_width(config: dict) -> int:
    width = _config_int(config, "bar_width", 2)
    return width if width in {1, 2, 4} else 2


def _bar_gap(config: dict) -> int:
    spacing = str(config.get("bar_spacing") or "solid")
    return 1 if spacing == "separated" else 0


def _uniform_bar_count(config: dict, size: int = AUDIO_SIZE) -> int:
    width = _bar_width(config)
    gap = _bar_gap(config)
    return max(1, (size + gap) // (width + gap))


def _audio_band_count(mode: str, config: dict, size: int = AUDIO_SIZE) -> int:
    if mode == "spectrogram":
        return size // _spectrogram_bar_width(config, size)
    if mode == "bars":
        return _uniform_bar_count(config, size)
    return max(1, _config_int(config, "bands", AUDIO_BANDS))


def _analyzer_kwargs(mode: str, config: dict) -> dict[str, float]:
    if mode == "bars":
        tilt_default = 0.0
        gain_default = 8.0
        onset_default = 0.0
    elif mode == "spectrogram":
        tilt_default = 4.5
        gain_default = 10.0
        onset_default = 1.4
    else:
        tilt_default = 0.0
        gain_default = 6.0
        onset_default = 0.0
    return {
        "floor_db": _config_float(config, "floor_db", -55.0 if mode in {"bars", "vu"} else -66.0),
        "noise_gate": _config_float(config, "noise_gate", 0.08 if mode == "bars" else 0.02),
        "tilt": _config_float(config, "tilt_db", tilt_default),
        "gain_db": _config_float(config, "gain_db", gain_default),
        "onset_boost": _config_float(config, "onset_boost", onset_default),
    }


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
        backend: "DisplayBackend | FrameSink",
        app_db: AppDatabase | None = None,
        config_db: ConfigDatabase | None = None,
        device_id: str | None = None,
        device_db: DeviceDatabase | None = None,
        primary: bool = True,
        debug_mode: bool = False,
        wake: Event | None = None,
    ):
        self.backend = backend
        # Streaming backends (serial/wled/matrix) are driven frame-by-frame via
        # the shared player; file backends (web) use display_image directly.
        self.player = FramePlayer(backend) if isinstance(backend, FrameSink) else None
        self.app_db = app_db or AppDatabase()
        self.config_db = config_db or ConfigDatabase()
        self.device_id = device_id
        self.device_db = device_db or DeviceDatabase()
        # Only the primary loop consumes the shared notification queue, so a
        # notification isn't raced away onto a random panel.
        self.primary = primary
        self.debug_mode = debug_mode
        self.wake = wake
        self._forced_app: str | None = None
        self._matrix_rain: MatrixRain | None = None

    def _wait(self, seconds: float) -> None:
        if self.wake is not None:
            self.wake.wait(seconds)
        else:
            time.sleep(seconds)

    def _should_interrupt(self) -> bool:
        return (self.wake is not None and self.wake.is_set()) or self._pending_notification()

    def run(self) -> None:
        """Main display loop."""
        blanked = False
        while True:
            if self.wake is not None:
                self.wake.clear()
            single_app = None
            # Resolve this iteration's brightness / layout / interval, either
            # from the device row or the global config.
            if self.device_id:
                dev = self.device_db.get(self.device_id)
                if dev is None:
                    logger.warning("Device %r vanished, waiting…", self.device_id)
                    self._wait(NO_APPS_WAIT)
                    continue
                brightness = device_brightness(dev) if dev["enabled"] else 0
                layout_mode = dev["layout_mode"]
                cycle_interval = dev["cycle_interval"]
                single_app = dev["single_app"]
            else:
                config = self.config_db.get()
                brightness = config.brightness
                layout_mode = config.layout_mode
                cycle_interval = config.cycle_interval

            # If brightness is 0, display is "off" — skip rendering
            if brightness == 0:
                if not blanked:
                    self._clear_display_state()
                    blanked = True
                elif self.player is not None:
                    self.backend.set_brightness(0)
                self._wait(1)
                continue
            blanked = False

            if self.primary:
                self._check_notifications()
            if self.device_id and dev.get("mirror_of"):
                self._mirror_tick(dev["mirror_of"])
                continue

            active = self._collect_active()
            pinned = next((app for app in active if app.name == single_app), None) if (
                layout_mode == "single" and single_app
            ) else None

            # An explicit Single selection takes precedence over playlist rotation.
            try:
                active_playlist = PlaylistDatabase().get_active_playlist() if pinned is None else None
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
                self._clear_display_state()
                self._wait(NO_APPS_WAIT)
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
                self._display_app(self._check_show_now() or pinned or active[0], cycle_interval)
            else:
                logger.error("Unknown layout mode: %s", layout_mode)

    def _collect_active(self) -> list[AppConfig]:
        """The apps eligible to show right now — global rotation, or this
        device's rotation membership overlaid on the global app definitions."""
        if not self.device_id:
            return [
                a for a in self.app_db.list_apps()
                if a.enabled and a.active and not a.is_skipped_unhealthy
            ]

        active: list[AppConfig] = []
        for member in self.device_db.list_apps(self.device_id):
            if not member["enabled"]:
                continue
            app = self.app_db.get(member["app_name"])
            if app is None or not app.active or app.is_skipped_unhealthy:
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
            self._show(output_path(name), MIRROR_SLICE, name)
        elif name and current_display_file(target_id).exists():
            self._show(current_display_file(target_id), MIRROR_SLICE, name)
        else:
            time.sleep(MIRROR_SLICE)

    # -- live apps --

    def _display_live_app(self, app: AppConfig, duration: int | None) -> None:
        if app.runtime == "live_matrix":
            self._display_matrix_app(app, duration)
        elif app.runtime == "live_audio":
            self._display_audio_app(app.name, app.pixlet_config, duration)
        elif app.runtime == "live_nowplaying":
            self._display_nowplaying_app(app.name, duration)

    def _live_slot_active(self, name: str, start: float, duration: int | None) -> bool:
        if duration is not None and time.perf_counter() - start >= duration:
            return False
        if self._should_interrupt():
            return False
        return self._current_brightness() > 0

    def _display_matrix_app(self, app: AppConfig, duration: int | None) -> None:
        if self._matrix_rain is None:
            self._matrix_rain = MatrixRain()
        self._matrix_rain.configure(app.pixlet_config)
        clock = self.device_db.get_display_settings() if app.name == "matrix_clock" else None
        self._write_now_playing(app.name)
        start = time.perf_counter()
        next_preview = start
        # Streaming sinks receive the animation; the web backend reads the preview.
        while self.wake is None or not self.wake.is_set():
            now = time.perf_counter()
            if duration is not None and now - start >= duration:
                break
            if now >= next_preview:
                if self._pending_notification():
                    break
                brightness = self._current_brightness()
                if self.player is not None:
                    self.backend.set_brightness(brightness)
                if brightness == 0:
                    break
            frame = self._matrix_rain.frame(now, clock.local_time() if clock else None).tobytes()
            interval = 0.5
            if self.player is not None:
                interval = 0.08 if clock else 0.1
                if not self.backend.send_frame(frame):
                    interval = RECONNECT_DELAY
            if now >= next_preview:
                self._save_preview(frame)
                next_preview = now + 0.5
            deadline = now + interval
            if duration is not None:
                deadline = min(deadline, start + duration)
            self._wait(max(0, deadline - time.perf_counter()))

    def _display_audio_app(self, name: str, config: dict, duration: int | None) -> None:
        """Stream the live audio visualizer for one app slot."""
        mode = str(config.get("mode") or "bars")
        if self.player is None:  # not a streaming sink (e.g. web) — can't do live audio
            logger.warning("[%s] backend can't stream live audio; idling", self.device_id)
            self._write_now_playing(name)
            time.sleep(min(duration or NO_APPS_WAIT, NO_APPS_WAIT))
            return
        try:
            from phoenix.audio.analyzer import SpectrumAnalyzer
            from phoenix.audio.source import DeviceAudioSource
            from phoenix.audio.visualizer import make_visualizer
        except ImportError:
            logger.warning("audio extra not installed (uv sync --extra audio); can't visualize")
            time.sleep(NO_APPS_WAIT)
            return

        settings = get_settings()
        try:
            bands = _audio_band_count(mode, config)
            bar_width = _spectrogram_bar_width(config) if mode == "spectrogram" else None
            gap = _bar_gap(config) if mode == "bars" else 0
            if mode == "bars":
                bar_width = _bar_width(config)
            source = DeviceAudioSource(
                device=settings.audio_device or None, samplerate=AUDIO_SR, blocksize=AUDIO_BLOCK
            )
            analyzer = SpectrumAnalyzer(
                samplerate=AUDIO_SR,
                fft_size=AUDIO_BLOCK,
                bands=bands,
                **_analyzer_kwargs(mode, config),
            )
            viz = make_visualizer(
                mode,
                bands=bands,
                size=AUDIO_SIZE,
                bar_width=bar_width,
                gap=gap,
                palette=str(config.get("palette") or "hue"),
                contrast=str(config.get("contrast") or "high"),
            )
        except Exception:
            logger.exception("[%s] audio setup failed", self.device_id)
            time.sleep(min(duration or NO_APPS_WAIT, NO_APPS_WAIT))
            return

        logger.info("[%s] Live audio visualizer (%s)", self.device_id, mode)
        self._write_now_playing(name)
        start = time.perf_counter()
        try:
            for i, samples in enumerate(source.blocks()):
                if i % 10 == 0:
                    if not self._live_slot_active(name, start, duration):
                        break
                    self.backend.set_brightness(self._current_brightness())
                frame = viz.render(*analyzer.process(samples))
                self.backend.send_frame(frame)
                if i % 20 == 0:  # ~2x/sec live preview for the dashboard
                    self._save_preview(frame)
        except Exception:
            logger.exception("[%s] audio loop error", self.device_id)
        finally:
            source.close()

    def _display_nowplaying_app(self, name: str, duration: int | None) -> None:
        """Stream the live now-playing card for one app slot."""
        if self.player is None:
            logger.warning("[%s] backend can't stream live frames; idling", self.device_id)
            self._write_now_playing(name)
            time.sleep(min(duration or NO_APPS_WAIT, NO_APPS_WAIT))
            return
        try:
            from phoenix.nowplaying.render import NowPlayingRenderer
            from phoenix.nowplaying.source import HANowPlayingSource
        except ImportError:
            logger.warning("nowplaying deps missing")
            time.sleep(NO_APPS_WAIT)
            return

        source = HANowPlayingSource(get_settings())
        renderer = NowPlayingRenderer()
        logger.info("[%s] Live now-playing", self.device_id)
        self._write_now_playing(name)
        last = time.perf_counter()
        start = last
        i = 0
        try:
            while True:
                if i % 10 == 0:
                    if not self._live_slot_active(name, start, duration):
                        break
                    self.backend.set_brightness(self._current_brightness())
                now = time.perf_counter()
                dt, last = now - last, now
                track = source.get()
                frame = renderer.render(track, dt) if track else renderer.render_idle()
                self.backend.send_frame(frame)
                if i % 20 == 0:
                    self._save_preview(frame)
                i += 1
                time.sleep(1 / 20)
        except Exception:
            logger.exception("[%s] nowplaying loop error", self.device_id)

    def _write_now_playing(self, name: str) -> None:
        """Text-only now-playing sentinel for live-frame modes."""
        out = DATA_DIR / "output"
        try:
            out.mkdir(parents=True, exist_ok=True)
            (out / "current_app.txt").write_text(name)
            if self.device_id:
                current_app_file(self.device_id).write_text(name)
        except Exception:
            pass

    def _save_preview(self, frame: bytes) -> None:
        """Encode a live frame to webp so the dashboard preview stays current."""
        try:
            from PIL import Image

            img = Image.frombytes("RGB", (64, 64), frame)
            out = DATA_DIR / "output"
            out.mkdir(parents=True, exist_ok=True)
            img.save(out / "current_display.webp", "WEBP")
            if self.device_id:
                img.save(current_display_file(self.device_id), "WEBP")
        except Exception:
            pass

    def _clear_display_state(self) -> None:
        """Clear the physical output and the dashboard's current-frame sentinels."""
        if self.player is not None:
            self.backend.set_brightness(0)
        self.backend.clear()
        try:
            from PIL import Image

            out = DATA_DIR / "output"
            out.mkdir(parents=True, exist_ok=True)
            img = Image.new("RGB", (64, 64), (0, 0, 0))
            img.save(out / "current_display.webp", "WEBP")
            (out / "current_app.txt").write_text("")
            if self.device_id:
                img.save(current_display_file(self.device_id), "WEBP")
                current_app_file(self.device_id).write_text("")
        except Exception:
            pass

    # -- putting an app on the panel --

    def _show(self, path: Path, duration: int, app_name: str) -> None:
        """Display one app's rendered frame(s) for ``duration`` seconds.

        Streaming sinks go through the shared FramePlayer (which owns the
        still/animation timing); file backends get the path directly. Either
        way the manager records the now-playing sentinels so the dashboard and
        any mirror can follow.
        """
        if self.player is not None:
            self._write_sentinels(app_name, path)
            self.player.play(path, duration, self._current_brightness, self._should_interrupt)
        else:
            # web backend writes its own sentinels as it copies the frame
            self.backend.display_image(path, duration)

    def _write_sentinels(self, app_name: str, path: Path) -> None:
        """Record what this panel is showing (legacy + per-device) and copy the
        frame for the dashboard's live preview."""
        large = path.with_suffix(".large.webp")
        src = large if large.exists() else path
        out = DATA_DIR / "output"
        try:
            out.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, out / "current_display.webp")
            (out / "current_app.txt").write_text(app_name)
            if self.device_id:
                shutil.copy(src, current_display_file(self.device_id))
                current_app_file(self.device_id).write_text(app_name)
        except Exception:
            pass

    def _current_brightness(self) -> int:
        """Live brightness for the player — per-device, else global config."""
        try:
            if self.device_id:
                dev = self.device_db.get(self.device_id)
                return device_brightness(dev) if dev is not None and dev["enabled"] else 0
            return self.config_db.get().brightness
        except Exception:
            return 255

    def _pending_notification(self) -> bool:
        """Non-consuming peek so the player can break out for a notification."""
        try:
            from phoenix.mqtt import _connect

            with _connect() as conn:
                return (
                    conn.execute("SELECT 1 FROM notifications WHERE displayed = 0 LIMIT 1").fetchone()
                    is not None
                )
        except Exception:
            return False

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
            if self.wake is not None and self.wake.is_set():
                return
            if self._current_brightness() == 0:
                return
            # Check for notifications between each app
            self._check_notifications()
            # Check for "show now" override
            show_now = self._check_show_now()
            if show_now:
                self._display_app(show_now, duration)
                if self.wake is not None and self.wake.is_set():
                    return
            self._display_app(app, duration)

    def _display_app(self, app: AppConfig, duration: int) -> None:
        # Re-read from DB for fresh state
        fresh = self.app_db.get(app.name)
        if fresh is None:
            return

        forced = self._forced_app == fresh.name
        if forced:
            self._forced_app = None

        if not forced and fresh.is_skipped_unhealthy:
            logger.info("[%s] Skipping unhealthy app (%s)", fresh.name, fresh.health_reason or "data down")
            return

        if _is_live_runtime(fresh):
            self._display_live_app(fresh, duration)
            return

        path = output_path(fresh.name)
        if not path.exists():
            logger.warning("[%s] Output not found: %s", fresh.name, path)
            return

        logger.info("Displaying %s for %ds", fresh.name, duration)
        self._show(path, duration, fresh.name)

    def _check_show_now(self) -> AppConfig | None:
        """Check if a 'show now' request is pending for this device."""
        show_file = show_now_file(self.device_id)
        if not show_file.exists():
            return None
        try:
            name = show_file.read_text().strip()
            show_file.unlink()
            if name:
                app = self.app_db.get(name)
                if app and (_is_live_runtime(app) or output_path(name).exists()):
                    logger.info("[show_now] Jumping to %s", name)
                    self._forced_app = name
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

        # Render directly with the pure-Python panel renderer
        try:
            from phoenix.panel_render import render_panel_to_files

            notif_settings = Settings()
            notif_output = output_path("panel__notification")
            render_panel_to_files(
                panel_data,
                notif_output,
                None,
                width=notif_settings.render_width,
                height=notif_settings.render_height,
                magnification=notif_settings.magnification,
            )
            if notif_output.exists():
                self._show(notif_output, notif["duration"], "panel__notification")
        except Exception:
            logger.exception("[notify] Failed to render notification")
