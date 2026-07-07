"""Web display backend — copies rendered images to a served directory."""

import logging
import shutil
import time
from pathlib import Path

from PIL import Image

from phoenix.paths import DATA_DIR, current_app_file, current_display_file

logger = logging.getLogger(__name__)

WEB_OUTPUT_DIR = DATA_DIR / "output"


class WebDisplayBackend:
    """DisplayBackend implementation that copies images for web serving."""

    def __init__(self, device_id: str | None = None):
        WEB_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self._device_id = device_id
        self.current_display = WEB_OUTPUT_DIR / "current_display.webp"
        self.clear()

    def display_image(self, image_path: Path, duration: int) -> None:
        # Use the large version for web display
        large_path = image_path.with_suffix(".large.webp")
        src = large_path if large_path.exists() else image_path

        app_name = image_path.stem.removesuffix(".large")
        try:
            shutil.copy(src, self.current_display)
            (WEB_OUTPUT_DIR / "current_app.txt").write_text(app_name)
            if self._device_id:
                shutil.copy(src, current_display_file(self._device_id))
                current_app_file(self._device_id).write_text(app_name)
        except Exception:
            logger.exception("Error copying to web display")

        time.sleep(duration)

    def clear(self) -> None:
        try:
            img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
            img.save(self.current_display, "WEBP")
        except Exception:
            logger.exception("Error clearing web display")
