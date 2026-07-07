"""Visualizers — band levels → a 64x64 RGB frame (raw bytes for the FrameSink).

SpectrumBars draws the classic analyzer: one vertical bar per band, colored with
the Ember-CRT fire gradient (crimson embers at the base → gold/core at the tip),
with a bright peak-hold cap. Rendered straight into a numpy buffer so it's cheap
enough for ~45fps and deterministic for tests.
"""

from typing import Protocol

import numpy as np

SIZE = 64

# Ember-CRT fire ramp, base → tip.
_PALETTE = np.array(
    [
        (95, 12, 8),     # deep ember
        (179, 36, 26),   # crimson
        (255, 90, 42),   # ember
        (255, 158, 61),  # flame
        (255, 217, 138), # gold
        (255, 242, 207), # core
    ],
    dtype=np.float32,
)
_CAP = np.array((255, 242, 207), dtype=np.uint8)  # peak-hold cap = core white-gold


def _fire_gradient(height: int) -> np.ndarray:
    """(height, 3) uint8 ramp; row 0 = bar base, row height-1 = tip."""
    xs = np.linspace(0.0, len(_PALETTE) - 1, height)
    ramp = np.empty((height, 3), dtype=np.uint8)
    base = np.arange(len(_PALETTE))
    for c in range(3):
        ramp[:, c] = np.interp(xs, base, _PALETTE[:, c]).astype(np.uint8)
    return ramp


class Visualizer(Protocol):
    def render(self, levels: np.ndarray, peaks: np.ndarray) -> bytes: ...


class SpectrumBars:
    def __init__(self, bands: int = 24, size: int = SIZE, gap: int = 1):
        self.bands = bands
        self.size = size
        self.gap = gap
        self._grad = _fire_gradient(size)  # color per height-from-base
        # Even bar columns across the width.
        self._edges = np.round(np.linspace(0, size, bands + 1)).astype(int)

    def render(self, levels: np.ndarray, peaks: np.ndarray) -> bytes:
        size = self.size
        frame = np.zeros((size, size, 3), dtype=np.uint8)
        for b in range(self.bands):
            x0 = self._edges[b]
            x1 = max(x0 + 1, self._edges[b + 1] - self.gap)

            h = int(round(float(levels[b]) * size))
            if h > 0:
                h = min(h, size)
                # rows size-h .. size-1 (bottom-anchored); color by height-from-base
                frame[size - h : size, x0:x1] = self._grad[:h][::-1, None, :]

            ph = int(round(float(peaks[b]) * size))
            if ph > 0:
                y = size - min(ph, size)
                frame[y, x0:x1] = _CAP

        return frame.tobytes()
