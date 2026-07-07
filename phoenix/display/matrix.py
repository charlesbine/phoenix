"""RGB LED matrix frame sink for Raspberry Pi (rpi-rgb-led-matrix)."""

import logging

from PIL import Image

from phoenix.settings import get_settings

logger = logging.getLogger(__name__)

# Lazy hardware init — only happens when MatrixDisplayBackend is instantiated
_matrix = None


def _get_matrix():
    global _matrix
    if _matrix is not None:
        return _matrix

    settings = get_settings()
    if settings.platform != "matrix":
        # Mock matrix for dev/testing
        _matrix = _MockMatrix()
        return _matrix

    try:
        import sys

        sys.path.append("/usr/local/lib/python3.9/dist-packages/")
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        options = RGBMatrixOptions()
        options.rows = 64
        options.cols = 64
        options.chain_length = 1
        options.parallel = 1
        options.hardware_mapping = "adafruit-hat"
        _matrix = RGBMatrix(options=options)
    except ImportError:
        logger.warning("rgbmatrix not available, using mock")
        _matrix = _MockMatrix()

    return _matrix


class _MockMatrix:
    def __init__(self):
        self.width = 64
        self.height = 64

    def Clear(self):
        logger.debug("Mock: Clear")

    def CreateFrameCanvas(self):
        return _MockCanvas()

    def SetImage(self, image):
        logger.debug("Mock: SetImage")

    def SwapOnVSync(self, canvas):
        logger.debug("Mock: SwapOnVSync")
        return canvas


class _MockCanvas:
    def SetImage(self, image):
        logger.debug("Mock: Canvas.SetImage")


class MatrixDisplayBackend:
    """FrameSink for a Pi-driven RGB LED matrix.

    The shared FramePlayer hands us decoded RGB frames; we push each onto the
    panel via SetImage. Brightness on rpi-rgb-led-matrix is set at construction,
    so per-frame set_brightness is a no-op here.
    """

    still_refresh = 0.0  # hardware holds the frame — no re-send needed

    def __init__(self, device_id: str | None = None):
        self._device_id = device_id
        self._matrix = _get_matrix()

    # -- FrameSink protocol --

    def set_brightness(self, level: int) -> None:
        pass  # library brightness is fixed at init; nothing live to set

    def send_frame(self, rgb: bytes) -> bool:
        try:
            self._matrix.SetImage(Image.frombytes("RGB", (64, 64), rgb))
            return True
        except Exception:
            logger.exception("Error sending frame to matrix")
            return False

    def clear(self) -> None:
        try:
            self._matrix.Clear()
        except Exception:
            logger.exception("Error clearing matrix")

    def close(self) -> None:
        pass
