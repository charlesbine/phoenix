"""WLED frame sink — streams RGB frames to an ESP32/WLED HUB75 panel over
DNRGB realtime UDP.

Ported from the Helios project's transport. A lossy, static-friendly transport:
brightness is set out-of-band over HTTP and static frames are re-sent so a
dropped UDP packet self-heals. The decode/animation timing lives in
phoenix.display.sink.FramePlayer; this only knows how to put a frame on the wire.

Config (env, PHOENIX_ prefix):
  PHOENIX_PLATFORM=wled
  PHOENIX_WLED_IP=192.168.1.50   # or "auto" for mDNS discovery (needs zeroconf)
  PHOENIX_WLED_PORT=21324
"""

import logging
import socket
import time

import httpx

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
    """FrameSink that streams frames to a WLED HUB75 panel over DNRGB UDP.

    WLED applies master brightness itself, so ``set_brightness`` pushes it over
    HTTP when it changes and we stream full-brightness RGB. UDP is best-effort,
    so ``still_refresh`` asks the player to re-send static frames periodically.
    """

    still_refresh = 0.5  # lossy link — re-send stills to self-heal dropped packets

    def __init__(self, device_id: str | None = None, ip: str | None = None) -> None:
        self._settings = get_settings()
        self._device_id = device_id
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._last_brightness = -1
        # An explicit ip skips settings/mDNS discovery (used by `phoenix visualize`).
        self._ip = ip.strip() if ip else self._resolve_ip()

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

    # -- FrameSink protocol --

    def set_brightness(self, level: int) -> None:
        """Set WLED master brightness over HTTP, only when it changes."""
        if level == self._last_brightness or not self._ip:
            return
        self._last_brightness = level
        try:
            httpx.post(
                f"http://{self._ip}/json/state",
                json={"on": level > 0, "bri": max(0, min(255, level))},
                timeout=2.0,
            )
        except Exception as e:  # noqa: BLE001 — best-effort control
            logger.debug("WLED brightness set failed: %s", e)

    def send_frame(self, rgb: bytes) -> bool:
        if not self._ip:
            self._ip = self._resolve_ip()
        if not self._ip:
            return False
        try:
            send_dnrgb(self._sock, self._ip, self._settings.wled_port, rgb)
            return True
        except OSError as e:
            logger.warning("WLED send failed: %s", e)
            return False

    def clear(self) -> None:
        # UDP is lossy — repeat the black frame so a dropped packet can't leave
        # a band of stale pixels painted on the panel.
        black = b"\x00" * FRAME_SIZE
        for _ in range(3):
            self.send_frame(black)
            time.sleep(0.02)

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass
