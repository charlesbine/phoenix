"""WLED display backend — streams RGB frames to an ESP32/WLED HUB75 panel over
DNRGB realtime UDP.

Ported from the Helios project's transport and shaped to mirror
SerialDisplayBackend, so the Matrix Portal M4 (serial) and the Apollo M-1 /
WLED panel (UDP) are two interchangeable sinks behind one DisplayManager.

Config (env, PHOENIX_ prefix):
  PHOENIX_PLATFORM=wled
  PHOENIX_WLED_IP=192.168.1.50   # or "auto" for mDNS discovery (needs zeroconf)
  PHOENIX_WLED_PORT=21324
"""

import logging
import shutil
import socket
import time
from pathlib import Path

import httpx
from PIL import Image, ImageSequence

from phoenix.db import ConfigDatabase
from phoenix.paths import DATA_DIR
from phoenix.settings import get_settings

logger = logging.getLogger(__name__)

# DNRGB realtime UDP protocol (WLED)
DNRGB_PROTOCOL = 0x04
DNRGB_TIMEOUT = 255  # seconds before WLED reverts to its own effects (max)
MAX_LEDS_PER_PACKET = 480  # 480*3+4 = 1444 bytes; 489 causes artifacts on ESP32
TOTAL_LEDS = 64 * 64
FRAME_SIZE = TOTAL_LEDS * 3
RECONNECT_DELAY = 2  # seconds


def send_dnrgb(sock: socket.socket, ip: str, port: int, rgb_bytes: bytes) -> None:
    """Send one full 64x64 frame as DNRGB UDP packets (<=480 LEDs each).

    sendto() syscall overhead plus WiFi radio serialization provide natural
    pacing; the whole 9-packet burst is well under a millisecond.
    """
    offset = 0
    while offset < TOTAL_LEDS:
        chunk = min(MAX_LEDS_PER_PACKET, TOTAL_LEDS - offset)
        header = bytes([DNRGB_PROTOCOL, DNRGB_TIMEOUT, (offset >> 8) & 0xFF, offset & 0xFF])
        sock.sendto(header + rgb_bytes[offset * 3 : (offset + chunk) * 3], (ip, port))
        offset += chunk


def discover_wled(timeout: float = 10.0) -> str | None:
    """mDNS-discover a WLED device (``_wled._tcp``). Returns an IP or None.

    Requires the optional ``zeroconf`` dependency (``uv sync --extra wled``).
    """
    try:
        from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf
    except ImportError:
        logger.warning("zeroconf not installed — set PHOENIX_WLED_IP to an explicit address")
        return None

    found: list[str] = []

    def on_change(zeroconf, service_type, name, state_change, **_):  # type: ignore[no-untyped-def]
        if state_change is not ServiceStateChange.Added:
            return
        info = zeroconf.get_service_info(service_type, name)
        if info and info.addresses:
            found.append(socket.inet_ntoa(info.addresses[0]))

    zc = Zeroconf()
    ServiceBrowser(zc, "_wled._tcp.local.", handlers=[on_change])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not found:
        time.sleep(0.2)
    zc.close()
    return found[0] if found else None


class WLEDDisplayBackend:
    """DisplayBackend that streams frames to a WLED HUB75 panel over DNRGB UDP.

    WLED applies master brightness itself, so we set it over HTTP when it
    changes and stream full-brightness RGB. Because UDP is best-effort, still
    frames are re-sent periodically so a dropped packet self-heals.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._config_db = ConfigDatabase()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._web_output = DATA_DIR / "output"
        self._web_output.mkdir(parents=True, exist_ok=True)
        self._current_display = self._web_output / "current_display.webp"
        self._last_brightness = -1
        self._ip = self._resolve_ip()

    def _resolve_ip(self) -> str | None:
        ip = (self._settings.wled_ip or "").strip()
        if ip and ip.lower() != "auto":
            logger.info("WLED at %s:%d", ip, self._settings.wled_port)
            return ip
        logger.info("Discovering WLED via mDNS…")
        found = discover_wled()
        logger.info("Discovered WLED at %s", found) if found else logger.warning(
            "No WLED device found — set PHOENIX_WLED_IP"
        )
        return found

    # -- transport --

    def _apply_brightness(self, brightness: int) -> None:
        """Set WLED master brightness over HTTP, only when it changes."""
        if brightness == self._last_brightness or not self._ip:
            return
        self._last_brightness = brightness
        try:
            httpx.post(
                f"http://{self._ip}/json/state",
                json={"on": brightness > 0, "bri": max(0, min(255, brightness))},
                timeout=2.0,
            )
        except Exception as e:  # noqa: BLE001 — best-effort control
            logger.debug("WLED brightness set failed: %s", e)

    def _send_frame(self, rgb_bytes: bytes) -> bool:
        if not self._ip:
            self._ip = self._resolve_ip()
        if not self._ip:
            return False
        try:
            send_dnrgb(self._sock, self._ip, self._settings.wled_port, rgb_bytes)
            return True
        except OSError as e:
            logger.warning("WLED send failed: %s", e)
            return False

    # -- DisplayBackend protocol --

    def display_image(self, image_path: Path, duration: int) -> None:
        large_path = image_path.with_suffix(".large.webp")
        src = large_path if large_path.exists() else image_path
        try:
            shutil.copy(src, self._current_display)
            (self._web_output / "current_app.txt").write_text(image_path.stem.removesuffix(".large"))
        except Exception:
            pass

        try:
            with Image.open(image_path) as image:
                is_animated = getattr(image, "is_animated", False)
                if not is_animated:
                    try:
                        is_animated = len(ImageSequence.all_frames(image)) > 1
                    except Exception:
                        is_animated = False
                if is_animated:
                    self._display_animation(image, duration)
                else:
                    self._display_still(image, duration)
        except Exception:
            logger.exception("Error displaying %s", image_path)

    def clear(self) -> None:
        self._send_frame(b"\x00" * FRAME_SIZE)

    # -- helpers (mirror SerialDisplayBackend) --

    def _image_to_rgb_bytes(self, image: Image.Image) -> bytes:
        return image.convert("RGB").resize((64, 64), Image.Resampling.LANCZOS).tobytes()

    def _get_brightness(self) -> int:
        try:
            return self._config_db.get().brightness
        except Exception:
            return 255

    def _has_pending_notification(self) -> bool:
        from phoenix.mqtt import _connect

        with _connect() as conn:
            row = conn.execute("SELECT 1 FROM notifications WHERE displayed = 0 LIMIT 1").fetchone()
            return row is not None

    def _display_still(self, image: Image.Image, duration: int) -> None:
        rgb = self._image_to_rgb_bytes(image)
        self._apply_brightness(self._get_brightness())
        if not self._send_frame(rgb):
            time.sleep(RECONNECT_DELAY)
            return
        elapsed = 0.0
        while elapsed < duration:
            if self._has_pending_notification():
                return
            time.sleep(min(0.5, duration - elapsed))
            elapsed += 0.5
            self._apply_brightness(self._get_brightness())
            self._send_frame(rgb)  # idempotent refresh — self-heals dropped UDP packets

    def _display_animation(self, image: Image.Image, duration: int) -> None:
        frames: list[bytes] = []
        durations: list[float] = []
        for frame in ImageSequence.Iterator(image):
            frames.append(self._image_to_rgb_bytes(frame))
            durations.append(frame.info.get("duration", 100) / 1000)
        if not frames:
            return

        start = time.perf_counter()
        while time.perf_counter() - start < duration:
            self._apply_brightness(self._get_brightness())
            for rgb, delay in zip(frames, durations):
                if time.perf_counter() - start >= duration:
                    return
                if self._has_pending_notification():
                    return
                if not self._send_frame(rgb):
                    time.sleep(RECONNECT_DELAY)
                    return
                time.sleep(delay)
