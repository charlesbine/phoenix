"""Frame-streaming seam.

Backends that push raw RGB frames (serial M4, WLED UDP, Pi matrix) implement
``FrameSink``; the shared ``FramePlayer`` decodes a rendered webp and drives the
still/animation timing loop. That loop used to be copy-pasted into every
backend — now it lives in one place, and a new sink only has to say how to put
one 64x64 frame on the wire.

This is also the seam the live pipelines plug into: a visualizer / VU-meter /
spectrogram just produces frames and calls ``sink.send_frame`` at its own rate,
instead of going through the webp player.
"""

import gc
import logging
import time
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from PIL import Image, ImageSequence

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 2  # seconds to back off when a transport is down
MATRIX_SIZE = (64, 64)
FRAME_BYTES = MATRIX_SIZE[0] * MATRIX_SIZE[1] * 3


@runtime_checkable
class FrameSink(Protocol):
    """A transport that accepts one 64x64 RGB888 frame at a time.

    Sinks may carry a ``still_refresh`` float (seconds): lossy transports (UDP)
    re-send a static frame on that cadence to self-heal dropped packets;
    reliable ones leave it 0.
    """

    def send_frame(self, rgb: bytes) -> bool: ...  # False => transport down
    def set_brightness(self, level: int) -> None: ...  # apply/scale; may be a no-op
    def clear(self) -> None: ...
    def close(self) -> None: ...


def image_to_rgb(image: Image.Image) -> bytes:
    """A PIL image → raw 64x64 RGB888 bytes."""
    return image.convert("RGB").resize(MATRIX_SIZE, Image.Resampling.LANCZOS).tobytes()


class FramePlayer:
    """Streams a rendered webp to a FrameSink for ``duration`` seconds."""

    def __init__(self, sink: FrameSink):
        self.sink = sink
        self.still_refresh: float = float(getattr(sink, "still_refresh", 0.0))

    def play(
        self,
        image_path: Path,
        duration: int,
        get_brightness: Callable[[], int],
        should_interrupt: Callable[[], bool],
    ) -> None:
        try:
            with Image.open(image_path) as image:
                frames, durations = self._extract(image)
        except Exception:
            logger.exception("Error decoding %s", image_path)
            return
        if not frames:
            return
        # Pause GC for the streaming loop: a periodic gen-2 collection is exactly
        # the kind of ~tens-of-ms stall that reads as a brief freeze mid-animation.
        gc_was = gc.isenabled()
        gc.disable()
        try:
            if len(frames) == 1:
                self._play_still(frames[0], duration, get_brightness, should_interrupt)
            else:
                self._play_animation(frames, durations, duration, get_brightness, should_interrupt)
        finally:
            if gc_was:
                gc.enable()

    @staticmethod
    def _extract(image: Image.Image) -> tuple[list[bytes], list[float]]:
        """Pre-decode all frames to RGB bytes + per-frame delays (seconds)."""
        animated = getattr(image, "is_animated", False)
        if not animated:
            try:
                animated = len(ImageSequence.all_frames(image)) > 1
            except Exception:
                animated = False
        if not animated:
            return [image_to_rgb(image)], [0.0]

        frames: list[bytes] = []
        durations: list[float] = []
        # Repeated pictures share one RGB buffer while retaining their own timing.
        unique_frames: dict[bytes, bytes] = {}
        for frame in ImageSequence.Iterator(image):
            rgb = image_to_rgb(frame)
            frames.append(unique_frames.setdefault(rgb, rgb))
            durations.append(frame.info.get("duration", 100) / 1000)
        return frames, durations

    def _play_still(
        self,
        rgb: bytes,
        duration: int,
        get_brightness: Callable[[], int],
        should_interrupt: Callable[[], bool],
    ) -> None:
        brightness = get_brightness()
        if brightness == 0:
            return
        self.sink.set_brightness(brightness)
        if not self.sink.send_frame(rgb):
            time.sleep(RECONNECT_DELAY)
            return
        elapsed = 0.0
        while elapsed < duration:
            if should_interrupt():
                return
            time.sleep(min(0.5, duration - elapsed))
            elapsed += 0.5
            level = get_brightness()
            if level == 0:
                return
            if self.still_refresh or level != brightness:
                self.sink.set_brightness(level)
                self.sink.send_frame(rgb)  # idempotent refresh — self-heals UDP loss
                brightness = level

    def _play_animation(
        self,
        frames: list[bytes],
        durations: list[float],
        duration: int,
        get_brightness: Callable[[], int],
        should_interrupt: Callable[[], bool],
    ) -> None:
        start = time.perf_counter()
        next_t = start  # drift-free schedule: sleep until each frame's due time
        next_brightness_check = start
        last_brightness: int | None = None

        def keep_playing(held_frame: bytes | None = None) -> bool:
            nonlocal next_brightness_check, last_brightness
            now = time.perf_counter()
            if now - start >= duration or should_interrupt():
                return False
            if now >= next_brightness_check:
                brightness = get_brightness()
                if brightness == 0:
                    return False
                self.sink.set_brightness(brightness)
                if held_frame is not None and brightness != last_brightness:
                    if not self.sink.send_frame(held_frame):
                        time.sleep(RECONNECT_DELAY)
                        return False
                last_brightness = brightness
                next_brightness_check = now + 0.5
            return True

        while time.perf_counter() - start < duration:
            for rgb, delay in zip(frames, durations):
                if not keep_playing():
                    return
                if not self.sink.send_frame(rgb):
                    time.sleep(RECONNECT_DELAY)
                    return
                next_t += delay
                deadline = min(next_t, start + duration)
                slack = deadline - time.perf_counter()
                while slack > 0.5:
                    time.sleep(0.5)
                    if not keep_playing(rgb):
                        return
                    slack = deadline - time.perf_counter()
                if slack > 0:
                    time.sleep(slack)
                else:
                    next_t = time.perf_counter()  # fell behind — resync, don't burst to catch up
