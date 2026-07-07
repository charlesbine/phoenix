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


def _ramp(colors: np.ndarray, n: int) -> np.ndarray:
    """Interpolate a small palette to an (n, 3) uint8 ramp."""
    colors = np.asarray(colors, dtype=np.float32)
    xs = np.linspace(0.0, len(colors) - 1, n)
    base = np.arange(len(colors))
    out = np.empty((n, 3), dtype=np.uint8)
    for c in range(3):
        out[:, c] = np.interp(xs, base, colors[:, c]).astype(np.uint8)
    return out


def _fire_gradient(height: int) -> np.ndarray:
    """(height, 3) uint8 ramp; row 0 = bar base, row height-1 = tip."""
    return _ramp(_PALETTE, height)


# Heat colormap for the spectrogram: black (silent) → fire → core (loudest).
_HEAT = _ramp(
    np.array(
        [(0, 0, 0), (40, 10, 6), (179, 36, 26), (255, 90, 42),
         (255, 158, 61), (255, 217, 138), (255, 242, 207)],
        dtype=np.float32,
    ),
    256,
)
# VU ramp: amber when quiet → red-hot when slammed.
_VU = _ramp(
    np.array([(120, 62, 18), (255, 158, 61), (255, 217, 138), (255, 90, 42), (196, 28, 14)],
             dtype=np.float32),
    64,
)


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


class VUMeter:
    """A fat segmented loudness meter — overall level fills left→right, amber to
    red-hot, with a peak-hold segment. Reads the mean of the band levels."""

    def __init__(self, bands: int = 24, size: int = SIZE, segments: int = 32, gain: float = 1.3):
        self.size = size
        self.segments = segments
        self.gain = gain
        self._colors = _ramp(_VU, segments)

    def render(self, levels: np.ndarray, peaks: np.ndarray) -> bytes:
        size = self.size
        frame = np.zeros((size, size, 3), dtype=np.uint8)
        level = float(np.clip(levels.mean() * self.gain, 0.0, 1.0))
        pk = float(np.clip(peaks.mean() * self.gain, 0.0, 1.0))

        y0, y1 = size // 2 - 10, size // 2 + 10  # a 20px-tall bar
        lit = int(round(level * self.segments))
        seg_w = size / self.segments
        for s in range(lit):
            x0 = int(round(s * seg_w))
            x1 = max(x0 + 1, int(round((s + 1) * seg_w)) - 1)
            frame[y0:y1, x0:x1] = self._colors[s]

        ps = int(round(pk * self.segments)) - 1
        if 0 <= ps < self.segments:
            x0 = int(round(ps * seg_w))
            x1 = max(x0 + 1, int(round((ps + 1) * seg_w)) - 1)
            frame[y0:y1, x0:x1] = _CAP
        return frame.tobytes()


class Spectrogram:
    """Scrolling waterfall — each frame adds the current spectrum as the
    rightmost column (low freq at the bottom) and scrolls history left."""

    def __init__(self, bands: int = 24, size: int = SIZE):
        self.size = size
        self.bands = bands
        self._buf = np.zeros((size, size, 3), dtype=np.uint8)
        self._src = np.arange(bands)
        self._dst = np.linspace(0, bands - 1, size)  # stretch bands → panel rows

    def render(self, levels: np.ndarray, peaks: np.ndarray) -> bytes:
        col = np.clip(np.interp(self._dst, self._src, levels), 0.0, 1.0)
        rgb = _HEAT[(col * 255).astype(int)]     # (size, 3), index 0 = lowest freq
        self._buf[:, :-1] = self._buf[:, 1:]     # scroll left
        self._buf[:, -1] = rgb[::-1]             # newest column on the right, low freq at bottom
        return self._buf.tobytes()


def make_visualizer(mode: str, bands: int, size: int = SIZE) -> Visualizer:
    modes = {"bars": SpectrumBars, "vu": VUMeter, "spectrogram": Spectrogram}
    if mode not in modes:
        raise ValueError(f"unknown visualizer mode {mode!r} (choose {', '.join(modes)})")
    return modes[mode](bands=bands, size=size)
