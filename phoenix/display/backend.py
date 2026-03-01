"""Display backend protocol — any object with display_image() and clear() qualifies."""

from pathlib import Path
from typing import Protocol


class DisplayBackend(Protocol):
    def display_image(self, image_path: Path, duration: int) -> None: ...
    def clear(self) -> None: ...
