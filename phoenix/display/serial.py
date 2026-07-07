"""Serial frame sink — streams raw RGB frames to a Matrix Portal M4 over USB serial.

Reliable, high-fps transport: brightness rides in-band in each frame header and
there's no need to re-send stills. The decode/animation timing lives in
phoenix.display.sink.FramePlayer; this only knows how to put a frame on the wire.
"""

import logging
import time

import serial

from phoenix.settings import get_settings

logger = logging.getLogger(__name__)

MAGIC_HEADER = b"\xDE\xAD\xBE\xEF"
FRAME_SIZE = 64 * 64 * 3  # 12,288 bytes RGB888
RECONNECT_DELAY = 2  # seconds between reconnection attempts


class SerialDisplayBackend:
    """FrameSink that streams frames to a Matrix Portal M4."""

    still_refresh = 0.0  # reliable link — no self-heal re-sends needed

    def __init__(self, device_id: str | None = None, port: str | None = None) -> None:
        self._settings = get_settings()
        self._device_id = device_id
        self._port_name = port or self._settings.serial_port  # per-device override else env
        self._brightness = 255
        self._port: serial.Serial | None = None
        self._connect()

    def _connect(self) -> None:
        """Open the serial port, or silently retry later if unavailable."""
        if self._port is not None and self._port.is_open:
            return
        try:
            self._port = serial.Serial(
                self._port_name,
                baudrate=2_000_000,  # ignored for native USB CDC, but required by pyserial
                timeout=1,
            )
            logger.info("Connected to M4 on %s", self._port_name)
        except serial.SerialException:
            logger.warning("M4 not available on %s, will retry", self._port_name)
            self._port = None

    def _write(self, brightness: int, rgb_bytes: bytes) -> bool:
        if self._port is None or not self._port.is_open:
            self._connect()
        if self._port is None:
            return False
        try:
            self._port.write(MAGIC_HEADER)
            self._port.write(bytes([brightness & 0xFF]))
            self._port.write(rgb_bytes)
            self._port.flush()
            return True
        except serial.SerialException:
            logger.warning("Serial write failed, closing connection")
            self.close()
            return False

    # -- FrameSink protocol --

    def set_brightness(self, level: int) -> None:
        self._brightness = max(0, min(255, level))

    def send_frame(self, rgb: bytes) -> bool:
        return self._write(self._brightness, rgb)

    def clear(self) -> None:
        """Send a blank (black) frame at zero brightness."""
        if not self._write(0, b"\x00" * FRAME_SIZE):
            time.sleep(RECONNECT_DELAY)

    def close(self) -> None:
        if self._port is not None:
            try:
                self._port.close()
            except Exception:
                pass
            self._port = None
