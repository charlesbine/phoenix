"""RGB LED matrix display backend for Raspberry Pi."""

import logging
import time
from pathlib import Path

from PIL import Image, ImageSequence

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
    """DisplayBackend implementation for RGB LED matrix."""

    def __init__(self, device_id: str | None = None):
        # device_id accepted for a uniform backend constructor; the Pi matrix
        # has no per-device sentinel/brightness path of its own yet.
        self._device_id = device_id
        self._matrix = _get_matrix()

    def display_image(self, image_path: Path, duration: int) -> None:
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
            self.clear()

    def clear(self) -> None:
        try:
            self._matrix.Clear()
        except Exception:
            logger.exception("Error clearing matrix")

    def _display_still(self, image: Image.Image, duration: int) -> None:
        self._matrix.Clear()
        self._matrix.SetImage(image.convert("RGB"))
        time.sleep(duration)

    def _display_animation(self, image: Image.Image, duration: int) -> None:
        # Pre-process all frames into canvases
        canvases: list = []
        durations: list[float] = []
        for frame in ImageSequence.Iterator(image):
            canvas = self._matrix.CreateFrameCanvas()
            canvas.SetImage(frame.convert("RGB"))
            canvases.append(canvas)
            durations.append(frame.info.get("duration", 100) / 1000)

        image.close()

        if not canvases:
            return

        # Loop animation until duration elapsed
        start = time.perf_counter()
        while time.perf_counter() - start < duration:
            for canvas, delay in zip(canvases, durations):
                self._matrix.SwapOnVSync(canvas)
                time.sleep(delay)
