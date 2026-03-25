"""Serial display backend — streams raw RGB frames to a Matrix Portal M4 over USB serial."""

import logging
import shutil
import time
from pathlib import Path

import serial
from PIL import Image, ImageSequence

from phoenix.db import ConfigDatabase
from phoenix.paths import DATA_DIR
from phoenix.settings import get_settings

logger = logging.getLogger(__name__)

MAGIC_HEADER = b"\xDE\xAD\xBE\xEF"
FRAME_SIZE = 64 * 64 * 3  # 12,288 bytes RGB888
RECONNECT_DELAY = 2  # seconds between reconnection attempts


class SerialDisplayBackend:
    """DisplayBackend implementation that streams frames to a Matrix Portal M4."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._config_db = ConfigDatabase()
        self._port: serial.Serial | None = None
        self._web_output = DATA_DIR / "output"
        self._web_output.mkdir(parents=True, exist_ok=True)
        self._current_display = self._web_output / "current_display.webp"
        self._connect()

    def _connect(self) -> None:
        """Open the serial port, or silently retry later if unavailable."""
        if self._port is not None and self._port.is_open:
            return
        try:
            self._port = serial.Serial(
                self._settings.serial_port,
                baudrate=2_000_000,  # ignored for native USB CDC, but required by pyserial
                timeout=1,
            )
            logger.info("Connected to M4 on %s", self._settings.serial_port)
        except serial.SerialException:
            logger.warning("M4 not available on %s, will retry", self._settings.serial_port)
            self._port = None

    def _send_frame(self, rgb_bytes: bytes, brightness: int) -> bool:
        """Send a single frame. Returns True on success."""
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
            self._close()
            return False

    def _close(self) -> None:
        if self._port is not None:
            try:
                self._port.close()
            except Exception:
                pass
            self._port = None

    def display_image(self, image_path: Path, duration: int) -> None:
        # Copy large version for dashboard live preview
        large_path = image_path.with_suffix(".large.webp")
        src = large_path if large_path.exists() else image_path
        try:
            shutil.copy(src, self._current_display)
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
        """Send a blank (black) frame."""
        black = b"\x00" * FRAME_SIZE
        if not self._send_frame(black, 0):
            time.sleep(RECONNECT_DELAY)

    def _image_to_rgb_bytes(self, image: Image.Image) -> bytes:
        """Convert a PIL Image to raw 64x64 RGB888 bytes."""
        frame = image.convert("RGB").resize((64, 64), Image.Resampling.LANCZOS)
        return frame.tobytes()

    def _get_brightness(self) -> int:
        """Read brightness from DB config (live-updated via dashboard)."""
        try:
            return self._config_db.get().brightness
        except Exception:
            return 255

    def _display_still(self, image: Image.Image, duration: int) -> None:
        rgb = self._image_to_rgb_bytes(image)
        brightness = self._get_brightness()
        if not self._send_frame(rgb, brightness):
            time.sleep(RECONNECT_DELAY)
            return
        time.sleep(duration)

    def _display_animation(self, image: Image.Image, duration: int) -> None:
        # Pre-extract all frames and their durations
        frames: list[bytes] = []
        durations: list[float] = []
        for frame in ImageSequence.Iterator(image):
            frames.append(self._image_to_rgb_bytes(frame))
            durations.append(frame.info.get("duration", 100) / 1000)

        if not frames:
            return

        start = time.perf_counter()
        while time.perf_counter() - start < duration:
            brightness = self._get_brightness()
            for rgb, delay in zip(frames, durations):
                if time.perf_counter() - start >= duration:
                    return
                if not self._send_frame(rgb, brightness):
                    time.sleep(RECONNECT_DELAY)
                    return
                time.sleep(delay)
